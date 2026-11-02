from django.db import models

from apps.scans.models import Scan


class Finding(models.Model):
    class Severity(models.TextChoices):
        CRITICAL = "critical", "Critical"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        INFO = "info", "Info"

    class Category(models.TextChoices):
        DEPENDENCY = "dependency", "Dependency"
        SECRET = "secret", "Secret"
        CONFIG = "config", "Configuration"
        WORKFLOW = "workflow", "Workflow"
        PRACTICE = "practice", "Practice"
        OTHER = "other", "Other"

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="findings")
    title = models.CharField(max_length=512)
    severity = models.CharField(max_length=20, choices=Severity.choices, db_index=True)
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    summary = models.TextField()
    recommendation = models.TextField()
    file_path = models.CharField(max_length=1024, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"
