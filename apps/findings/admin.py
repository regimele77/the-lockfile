from django.contrib import admin

from apps.findings.models import Finding


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "severity",
        "status",
        "category",
        "scan",
        "file_path",
        "rule_id",
        "created_at",
    )
    list_filter = ("severity", "status", "category")
    search_fields = ("title", "summary", "file_path", "rule_id")
    readonly_fields = ("created_at",)
    autocomplete_fields = ("scan",)
