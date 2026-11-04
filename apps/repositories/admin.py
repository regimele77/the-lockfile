from django.contrib import admin

from apps.repositories.models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "is_private",
        "is_selected",
        "installation",
        "owner",
        "github_id",
        "tracked_at",
        "created_at",
    )
    list_filter = ("is_private", "is_selected", "installation")
    search_fields = ("name", "full_name", "owner__username")
    readonly_fields = ("created_at", "updated_at", "tracked_at")
    raw_id_fields = ("installation", "owner")
