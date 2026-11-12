import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import GitHubInstallation
from apps.accounts.services.access_errors import (
    classify_exception,
    classify_message,
    connection_health,
)
from apps.accounts.services.auth import (
    record_installation,
    sync_installations_for_user,
    upsert_user_from_github,
)
from apps.accounts.services.github import GitHubAppError, GitHubOAuthClient
from apps.accounts.services.installation_tokens import app_credentials_configured
from apps.accounts.services.secrets import TokenEncryptionError
from apps.core.forms import TechnicalConfigurationForm
from apps.core.models import TechnicalConfiguration
from apps.repositories.services.sync import sync_repositories_for_user
from apps.scans.services.sanitize import sanitize_error_message

logger = logging.getLogger(__name__)


def _flash_access_failure(request, exc_or_text, *, level="warning") -> None:
    """Flash a classified recovery message without leaking secrets."""
    if isinstance(exc_or_text, BaseException):
        guidance = classify_exception(exc_or_text)
    else:
        guidance = classify_message(sanitize_error_message(str(exc_or_text)))
    text = guidance.message
    if guidance.primary_label and guidance.primary_url:
        text = f"{text} Next: {guidance.primary_label}."
    getattr(messages, level)(request, text)


def _try_sync_repositories(request, user) -> None:
    """Best-effort repo sync after login/setup. Failures become flash messages."""
    if not app_credentials_configured():
        return
    if not GitHubInstallation.objects.filter(user=user).exists():
        return
    try:
        result = sync_repositories_for_user(user)
    except (GitHubAppError, TokenEncryptionError) as exc:
        _flash_access_failure(request, exc, level="warning")
        return
    if result.errors:
        for err in result.errors:
            _flash_access_failure(request, err, level="warning")
    elif result.upserted:
        messages.info(
            request,
            f"Synced {result.upserted} repositories from GitHub. "
            "Choose which to track on Connect repositories.",
        )


OAUTH_STATE_SESSION_KEY = "github_oauth_state"
INSTALL_STATE_SESSION_KEY = "github_install_state"


class GithubConnectView(View):
    """Entry point for GitHub App login (LOGIN_URL)."""

    template_name = "accounts/github.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect(settings.LOGIN_REDIRECT_URL)

        client = GitHubOAuthClient()
        return render(
            request,
            self.template_name,
            {
                "github_configured": client.is_configured(),
                "github_app_name": settings.GITHUB_APP_NAME,
            },
        )


class GithubOAuthStartView(View):
    """Begin user-to-server OAuth with a CSRF-safe state parameter."""

    def get(self, request):
        client = GitHubOAuthClient()
        if not client.is_configured():
            messages.error(
                request,
                "GitHub App login is not configured. Set GITHUB_APP_CLIENT_ID, "
                "GITHUB_APP_CLIENT_SECRET, and GITHUB_OAUTH_CALLBACK_URL in .env.",
            )
            return redirect("accounts:github")

        state = secrets.token_urlsafe(32)
        request.session[OAUTH_STATE_SESSION_KEY] = state
        try:
            return redirect(client.authorize_url(state))
        except GitHubAppError:
            messages.error(request, "Could not start GitHub login. Check App settings.")
            return redirect("accounts:github")


class GithubOAuthCallbackView(View):
    """Exchange the OAuth code, create/update the user, and establish a session."""

    def get(self, request):
        client = GitHubOAuthClient()

        if request.GET.get("error"):
            messages.error(
                request,
                "GitHub authorization was cancelled or denied. Try again when ready.",
            )
            return redirect("accounts:github")

        if not client.callback_host_allowed(request.get_host()):
            messages.error(request, "OAuth callback host is not allowed.")
            return redirect("accounts:github")

        state = request.GET.get("state", "")
        expected = request.session.pop(OAUTH_STATE_SESSION_KEY, None)
        if not expected or not state or not secrets.compare_digest(state, expected):
            messages.error(request, "Invalid OAuth state. Please try connecting again.")
            return redirect("accounts:github")

        code = request.GET.get("code", "")
        if not code:
            messages.error(request, "GitHub did not return an authorization code.")
            return redirect("accounts:github")

        try:
            token = client.exchange_code(code)
            profile = client.fetch_user(token.access_token)
            user = upsert_user_from_github(profile, token)
            installations = client.list_installations(token.access_token)
            sync_installations_for_user(user, installations)
        except TokenEncryptionError:
            logger.warning("GitHub OAuth token encryption failed", exc_info=False)
            messages.error(
                request,
                "Could not store GitHub credentials. Set GITHUB_TOKEN_FERNET_KEY "
                "in .env (see README), restart Compose, and try again.",
            )
            return redirect("accounts:github")
        except GitHubAppError:
            logger.warning("GitHub OAuth callback failed", exc_info=False)
            messages.error(
                request,
                "Could not complete GitHub login. Check App credentials and try again.",
            )
            return redirect("accounts:github")

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        # Prompt install when the user has no installations for this app yet.
        if not installations and settings.GITHUB_APP_NAME:
            install_state = secrets.token_urlsafe(32)
            request.session[INSTALL_STATE_SESSION_KEY] = install_state
            try:
                return redirect(client.install_url(install_state))
            except GitHubAppError:
                pass

        messages.success(request, f"Signed in as {profile.login}.")
        _try_sync_repositories(request, user)
        return redirect(settings.LOGIN_REDIRECT_URL)


class GithubSetupCallbackView(View):
    """
    GitHub App setup URL handler.

    Configure the App's "Setup URL" to:
    http://localhost:8000/accounts/github/setup/
    """

    def get(self, request):
        installation_id = request.GET.get("installation_id")
        setup_action = request.GET.get("setup_action", "")

        if not installation_id:
            messages.warning(request, "No GitHub App installation was returned.")
            if request.user.is_authenticated:
                return redirect("repositories:connect")
            return redirect("accounts:github")

        try:
            installation_id_int = int(installation_id)
        except (TypeError, ValueError):
            messages.error(request, "Invalid installation id from GitHub.")
            return redirect("accounts:github")

        # Optional state check when we initiated install from OAuth callback.
        state = request.GET.get("state", "")
        expected = request.session.pop(INSTALL_STATE_SESSION_KEY, None)
        if expected and state and not secrets.compare_digest(state, expected):
            messages.error(request, "Invalid install state. Please try again.")
            return redirect("accounts:github")

        user = request.user if request.user.is_authenticated else None
        record_installation(
            installation_id=installation_id_int,
            user=user,
        )

        if setup_action == "request":
            messages.info(
                request,
                "GitHub App installation was requested and is pending approval.",
            )
        else:
            messages.success(request, "GitHub App installation connected.")

        if user is not None:
            _try_sync_repositories(request, user)
            return redirect("repositories:connect")
        return redirect("accounts:github")


class LockfileLogoutView(LogoutView):
    next_page = reverse_lazy("core:landing")


class GithubInstallStartView(LoginRequiredMixin, View):
    """Send an authenticated user to the GitHub App install page."""

    def get(self, request):
        client = GitHubOAuthClient()
        if not settings.GITHUB_APP_NAME:
            messages.error(
                request,
                "GITHUB_APP_NAME is not set. An operator must configure the App slug.",
            )
            return redirect("repositories:connect")
        install_state = secrets.token_urlsafe(32)
        request.session[INSTALL_STATE_SESSION_KEY] = install_state
        try:
            return redirect(client.install_url(install_state))
        except GitHubAppError:
            messages.error(request, "Could not start GitHub App installation.")
            return redirect("repositories:connect")


class ProfileView(LoginRequiredMixin, TemplateView):
    """Account / GitHub connection health (settings-lite)."""

    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        health = connection_health(self.request.user)
        context.update(health)
        context["page_title"] = "Account"
        context["show_technical_config"] = self.request.user.is_superuser
        if self.request.user.is_superuser and "technical_form" not in context:
            context["technical_form"] = TechnicalConfigurationForm(
                instance=TechnicalConfiguration.load(),
                user=self.request.user,
            )
        context["technical_section_open"] = context.get(
            "technical_section_open", False
        )
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(
                request,
                "Only a superuser can change software technical configurations.",
            )
            return redirect("accounts:profile")

        form = TechnicalConfigurationForm(
            request.POST,
            instance=TechnicalConfiguration.load(),
            user=request.user,
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Software technical configurations saved. "
                "Schedule check interval changes need a Celery beat restart.",
            )
            return redirect("accounts:profile")

        messages.error(request, "Could not save technical configurations.")
        context = self.get_context_data(
            technical_form=form,
            technical_section_open=True,
        )
        return self.render_to_response(context)
