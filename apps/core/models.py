from django.conf import settings
from django.db import models


class TechnicalConfiguration(models.Model):
    """
    Singleton host-level scan/scanner knobs, editable from Account settings.

    Values seed from Django settings (env) on first load. Runtime code should
    read through apps.core.services.technical_config helpers so UI changes apply
    without editing .env.
    """

    singleton_id = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)

    clone_timeout_seconds = models.PositiveIntegerField(
        default=300,
        help_text="Max seconds allowed for a git clone.",
    )
    clone_depth = models.PositiveIntegerField(
        default=1,
        help_text="Shallow clone depth (1 = tip commit only).",
    )
    max_repo_size_mb = models.PositiveIntegerField(
        default=500,
        help_text="Refuse clones larger than this many megabytes.",
    )
    reschedule_hours = models.PositiveIntegerField(
        default=24,
        help_text="Re-scan a tracked repo when its last finished scan is older than this.",
    )
    schedule_check_hours = models.PositiveIntegerField(
        default=1,
        help_text=(
            "How often Celery beat checks for due repos. Changing this requires "
            "restarting the beat process."
        ),
    )
    scanner_timeout_seconds = models.PositiveIntegerField(
        default=120,
        help_text="Soft time budget per scanner run.",
    )
    max_findings_per_scanner = models.PositiveIntegerField(
        default=50,
        help_text="Cap findings emitted by a single scanner.",
    )
    max_file_bytes = models.PositiveIntegerField(
        default=512_000,
        help_text="Skip files larger than this many bytes when scanning.",
    )
    max_files = models.PositiveIntegerField(
        default=8_000,
        help_text="Max files walked per scan workspace.",
    )
    osv_timeout_seconds = models.PositiveIntegerField(
        default=30,
        help_text="HTTP timeout for OSV.dev advisory lookups.",
    )
    osv_max_packages = models.PositiveIntegerField(
        default=200,
        help_text="Max packages queried against OSV per scan.",
    )
    github_timeout_seconds = models.PositiveIntegerField(
        default=20,
        help_text="HTTP timeout for GitHub API calls made by scanners.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Technical configuration"
        verbose_name_plural = "Technical configuration"

    def __str__(self) -> str:
        return "Software technical configuration"

    def save(self, *args, **kwargs):
        self.singleton_id = 1
        super().save(*args, **kwargs)

    @classmethod
    def defaults_from_settings(cls) -> dict:
        return {
            "clone_timeout_seconds": int(
                getattr(settings, "SCAN_CLONE_TIMEOUT_SECONDS", 300)
            ),
            "clone_depth": int(getattr(settings, "SCAN_CLONE_DEPTH", 1)),
            "max_repo_size_mb": int(getattr(settings, "SCAN_MAX_REPO_SIZE_MB", 500)),
            "reschedule_hours": int(getattr(settings, "SCAN_RESCHEDULE_HOURS", 24)),
            "schedule_check_hours": int(
                getattr(settings, "SCAN_SCHEDULE_CHECK_HOURS", 1)
            ),
            "scanner_timeout_seconds": int(
                getattr(settings, "SCANNER_TIMEOUT_SECONDS", 120)
            ),
            "max_findings_per_scanner": int(
                getattr(settings, "SCANNER_MAX_FINDINGS_PER_SCANNER", 50)
            ),
            "max_file_bytes": int(getattr(settings, "SCANNER_MAX_FILE_BYTES", 512_000)),
            "max_files": int(getattr(settings, "SCANNER_MAX_FILES", 8_000)),
            "osv_timeout_seconds": int(
                getattr(settings, "SCANNER_OSV_TIMEOUT_SECONDS", 30)
            ),
            "osv_max_packages": int(
                getattr(settings, "SCANNER_OSV_MAX_PACKAGES", 200)
            ),
            "github_timeout_seconds": int(
                getattr(settings, "SCANNER_GITHUB_TIMEOUT_SECONDS", 20)
            ),
        }

    @classmethod
    def load(cls) -> "TechnicalConfiguration":
        obj = cls.objects.filter(singleton_id=1).first()
        if obj is not None:
            return obj
        return cls.objects.create(singleton_id=1, **cls.defaults_from_settings())
