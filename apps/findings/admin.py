from django.contrib import admin

from apps.findings.models import Finding


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("title", "severity", "category", "scan", "file_path", "created_at")
    list_filter = ("severity", "category")
    search_fields = ("title", "summary", "file_path")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("scan",)
