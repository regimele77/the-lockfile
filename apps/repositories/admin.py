from django.contrib import admin

from apps.repositories.models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("full_name", "is_private", "github_id", "created_at")
    list_filter = ("is_private",)
    search_fields = ("name", "full_name")
    readonly_fields = ("created_at",)
