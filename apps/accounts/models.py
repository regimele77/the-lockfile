from django.conf import settings
from django.db import models


class GitHubAccount(models.Model):
    """Links a Django user to their GitHub identity (user-to-server OAuth)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="github_account",
    )
    github_id = models.BigIntegerField(unique=True)
    login = models.CharField(max_length=255)
    avatar_url = models.URLField(blank=True, default="")
    # User-to-server access token. Never render in templates; rotate via re-auth.
    access_token = models.TextField(blank=True, default="")
    token_type = models.CharField(max_length=32, blank=True, default="bearer")
    scope = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["login"]

    def __str__(self) -> str:
        return self.login


class GitHubInstallation(models.Model):
    """
    A GitHub App installation linked to a Lockfile user.

    installation_id is required later to mint installation access tokens
    for repository APIs. Tokens are short-lived (~1h); mint on demand —
    do not treat a stored installation token as permanent.
    """

    installation_id = models.BigIntegerField(unique=True)
    account_login = models.CharField(max_length=255)
    account_type = models.CharField(max_length=32, blank=True, default="User")
    account_id = models.BigIntegerField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="github_installations",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["account_login"]

    def __str__(self) -> str:
        return f"{self.account_login} ({self.installation_id})"
