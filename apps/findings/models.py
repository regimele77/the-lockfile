from pathlib import PurePosixPath
from urllib.parse import quote

from django.db import models

from apps.scans.models import Scan

# Extensionless paths that are still files on GitHub (use /blob/, not /tree/).
_EXTENSIONLESS_FILES = frozenset(
    {
        "Dockerfile",
        "dockerfile",
        "Makefile",
        "makefile",
        "Gemfile",
        "Procfile",
        "Jenkinsfile",
        "Vagrantfile",
        "LICENSE",
        "LICENCE",
        "COPYING",
        "AUTHORS",
        "CONTRIBUTORS",
        "CHANGELOG",
        "CHANGES",
        "NEWS",
        "NOTICE",
        "README",
        "TODO",
        "go.mod",
        "go.sum",
        "Pipfile",
    }
)

# Dot-directories (not files like `.env` / `.gitignore`).
_DOT_DIRECTORIES = frozenset(
    {
        ".github",
        ".gitlab",
        ".circleci",
        ".vscode",
        ".idea",
        ".tox",
        ".venv",
        ".devcontainer",
    }
)

# Paths that are almost never present on GitHub even when a scanner saw them
# locally (gitignored secrets, local DBs). Used as a safety net for older rows.
_GITHUB_UNLINKABLE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.development",
        ".env.production",
        ".env.test",
        ".env.development.local",
        ".env.production.local",
        ".env.test.local",
        ".ds_store",
        "thumbs.db",
    }
)
_GITHUB_UNLINKABLE_SUFFIXES = (
    ".sqlite3",
    ".sqlite",
    ".db",
    ".pyc",
    ".pyo",
)


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

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        IGNORED = "ignored", "Ignored"

    scan = models.ForeignKey(Scan, on_delete=models.CASCADE, related_name="findings")
    title = models.CharField(max_length=512)
    severity = models.CharField(max_length=20, choices=Severity.choices, db_index=True)
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        db_default=Status.OPEN,
        db_index=True,
    )
    summary = models.TextField()
    recommendation = models.TextField()
    file_path = models.CharField(max_length=1024, blank=True, default="")
    rule_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        db_default="",
        db_index=True,
    )
    line_number = models.PositiveIntegerField(null=True, blank=True)
    # False when the path is not in the scanned commit (gitignored / local-only).
    github_linkable = models.BooleanField(default=False, db_default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"

    @property
    def display_path(self) -> str:
        path = (self.file_path or "").strip()
        if not path:
            return ""
        if self.line_number:
            return f"{path}:{self.line_number}"
        return path

    @property
    def github_blob_url(self) -> str:
        """GitHub deep link for this finding's path, or empty when not linkable."""
        if not self.github_linkable:
            return ""
        path = (self.file_path or "").strip().lstrip("/")
        if not path or path_never_on_github(path):
            return ""
        scan = self.scan
        ref = (scan.commit_sha or scan.default_branch or "").strip()
        if not ref:
            return ""
        repo = (scan.repository.full_name or "").strip()
        if not repo or "/" not in repo:
            return ""

        posix = PurePosixPath(path)
        # Directories must use /tree/; files use /blob/.
        is_directory = path.endswith("/") or path_looks_like_directory(posix)
        kind = "tree" if is_directory else "blob"
        encoded_path = "/".join(quote(part, safe="") for part in posix.parts)
        url = f"https://github.com/{repo}/{kind}/{quote(ref, safe='/')}/{encoded_path}"
        if not is_directory and self.line_number:
            url += f"#L{self.line_number}"
        return url


def path_never_on_github(path: str) -> bool:
    """Heuristic deny-list for paths that should not get a GitHub deep link."""
    name = PurePosixPath(path).name
    lowered = name.lower()
    if lowered in _GITHUB_UNLINKABLE_NAMES:
        return True
    if lowered.startswith(".env.") and not lowered.endswith(
        (".example", ".sample", ".template", ".dist")
    ):
        return True
    if lowered.endswith(_GITHUB_UNLINKABLE_SUFFIXES):
        return True
    return False


def path_looks_like_directory(path: PurePosixPath) -> bool:
    name = path.name
    if not name:
        return True
    if name in _DOT_DIRECTORIES:
        return True
    # Dotfiles such as `.env` / `.gitignore` are files, not directories.
    if name.startswith("."):
        return False
    if name in _EXTENSIONLESS_FILES:
        return False
    # A suffix (e.g. `.txt`, `.yml`) usually means a file.
    if path.suffix:
        return False
    return True
