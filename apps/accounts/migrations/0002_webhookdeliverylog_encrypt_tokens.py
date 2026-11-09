# Generated manually for GitHub App hardening (webhook log + token encryption).

from django.db import migrations, models


def encrypt_existing_access_tokens(apps, schema_editor):
    """Encrypt plaintext GitHubAccount.access_token rows when a Fernet key is set."""
    from django.conf import settings

    key = (getattr(settings, "GITHUB_TOKEN_FERNET_KEY", "") or "").strip()
    if not key:
        return

    from apps.accounts.services.secrets import (
        encrypt_secret,
        looks_like_ciphertext,
    )

    GitHubAccount = apps.get_model("accounts", "GitHubAccount")
    for account in GitHubAccount.objects.exclude(access_token="").iterator():
        stored = account.access_token or ""
        if not stored or looks_like_ciphertext(stored):
            continue
        account.access_token = encrypt_secret(stored)
        account.save(update_fields=["access_token"])


def noop_reverse(apps, schema_editor):
    # Cannot safely decrypt back to plaintext in a reverse migration.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WebhookDeliveryLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("delivery_id", models.CharField(db_index=True, max_length=64)),
                ("event", models.CharField(max_length=64)),
                ("action", models.CharField(blank=True, default="", max_length=64)),
                ("ok", models.BooleanField(default=True)),
                ("status", models.CharField(blank=True, default="", max_length=64)),
                ("error", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="webhookdeliverylog",
            index=models.Index(fields=["-created_at"], name="accounts_wh_created_idx"),
        ),
        migrations.RunPython(encrypt_existing_access_tokens, noop_reverse),
    ]
