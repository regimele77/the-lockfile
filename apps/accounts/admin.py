from django.contrib import admin

from apps.accounts.models import GitHubAccount, GitHubInstallation, WebhookDeliveryLog


@admin.register(GitHubAccount)
class GitHubAccountAdmin(admin.ModelAdmin):
    list_display = ("login", "github_id", "user", "updated_at")
    search_fields = ("login", "user__username", "user__email")
    readonly_fields = ("github_id", "created_at", "updated_at")
    # Never expose decrypted or ciphertext OAuth tokens in the admin UI.
    exclude = ("access_token",)


@admin.register(GitHubInstallation)
class GitHubInstallationAdmin(admin.ModelAdmin):
    list_display = (
        "account_login",
        "installation_id",
        "account_type",
        "user",
        "created_at",
    )
    search_fields = ("account_login", "user__username")
    list_filter = ("account_type",)
    readonly_fields = ("installation_id", "created_at", "updated_at")


@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "delivery_id",
        "event",
        "action",
        "ok",
        "status",
    )
    list_filter = ("ok", "event")
    search_fields = ("delivery_id", "event", "action", "status", "error")
    readonly_fields = (
        "delivery_id",
        "event",
        "action",
        "ok",
        "status",
        "error",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
