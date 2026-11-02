from django.contrib import admin

from apps.scans.models import Scan


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "repository", "status", "started_at", "finished_at", "created_at")
    list_filter = ("status",)
    search_fields = ("repository__full_name", "id")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("repository",)
