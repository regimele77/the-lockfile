from django.contrib import admin

from apps.scans.models import Scan


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "repository",
        "status",
        "trigger",
        "started_at",
        "finished_at",
        "created_at",
    )
    list_filter = ("status", "trigger")
    search_fields = ("repository__full_name", "id", "commit_sha", "celery_task_id")
    readonly_fields = (
        "created_at",
        "started_at",
        "finished_at",
        "celery_task_id",
        "commit_sha",
        "default_branch",
        "error_message",
    )
    autocomplete_fields = ("repository",)
