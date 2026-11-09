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
    # User-to-server OAuth token, stored encrypted when GITHUB_TOKEN_FERNET_KEY
    # is set. Never render in templates; rotate via re-auth. Admin excludes this.
    access_token = models.TextField(blank=True, default="")
    token_type = models.CharField(max_length=32, blank=True, default="bearer")
    scope = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["login"]

    def __str__(self) -> str:
        return self.login

    def set_access_token(self, plaintext: str) -> None:
        """Encrypt and assign the OAuth token for storage. Never log plaintext."""
        from apps.accounts.services.secrets import encrypt_for_storage

        self.access_token = encrypt_for_storage(plaintext or "")

    def get_access_token(self) -> str:
        """
        Decrypt the stored OAuth token for server-side use only.

        Legacy plaintext rows are returned as-is. Prefer re-saving after read
        so they upgrade to ciphertext when a Fernet key is configured.
        """
        from apps.accounts.services.secrets import (
            decrypt_secret,
            encrypt_for_storage,
            fernet_key_configured,
            looks_like_ciphertext,
        )

        stored = self.access_token or ""
        if not stored:
            return ""
        plaintext = decrypt_secret(stored)
        if (
            plaintext
            and fernet_key_configured()
            and not looks_like_ciphertext(stored)
        ):
            # Upgrade-on-read for pre-encryption rows.
            self.access_token = encrypt_for_storage(plaintext)
            self.save(update_fields=["access_token", "updated_at"])
        return plaintext


class GitHubInstallation(models.Model):
    """
    A GitHub App installation linked to a Lockfile user.

    installation_id is required to mint installation access tokens for
    repository APIs. Tokens are short-lived (~1h); mint on demand.
    Do not treat a stored installation token as permanent.
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


class WebhookDeliveryLog(models.Model):
    """
    Minimal GitHub webhook delivery record (no payload bodies).

    Used for correlation and light admin/status inspection.
    """

    delivery_id = models.CharField(max_length=64, db_index=True)
    event = models.CharField(max_length=64)
    action = models.CharField(max_length=64, blank=True, default="")
    ok = models.BooleanField(default=True)
    status = models.CharField(max_length=64, blank=True, default="")
    error = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self) -> str:
        state = "ok" if self.ok else "error"
        return f"{self.event}:{self.action or '-'} {self.delivery_id} ({state})"
