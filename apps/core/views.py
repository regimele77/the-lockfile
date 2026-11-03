from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views.generic import TemplateView


def healthcheck(_request):
    return JsonResponse({"status": "ok", "service": "the-lockfile"})


class LandingView(TemplateView):
    template_name = "core/landing.html"


class PrivacyView(TemplateView):
    template_name = "core/privacy.html"


class TermsView(TemplateView):
    template_name = "core/terms.html"


class HealthPageView(TemplateView):
    """Human-readable instance health page. Machine JSON remains at /health/."""

    template_name = "core/health.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        db_ok = False
        db_error = ""
        try:
            connection.ensure_connection()
            db_ok = connection.is_usable()
        except Exception as exc:  # noqa: BLE001 - surface status, don't crash the page
            db_error = str(exc)

        context.update(
            {
                "checked_at": timezone.now(),
                "app_ok": True,
                "db_ok": db_ok,
                "db_error": db_error,
                "overall_ok": db_ok,
            }
        )
        return context
