from django import forms

from apps.core.models import TechnicalConfiguration


class TechnicalConfigurationForm(forms.ModelForm):
    confirm_password = forms.CharField(
        label="Confirm with your password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "field",
                "autocomplete": "current-password",
            }
        ),
        help_text=(
            "Re-enter your Django superuser password to apply host-wide changes."
        ),
    )

    class Meta:
        model = TechnicalConfiguration
        fields = [
            "clone_timeout_seconds",
            "clone_depth",
            "max_repo_size_mb",
            "reschedule_hours",
            "schedule_check_hours",
            "scanner_timeout_seconds",
            "max_findings_per_scanner",
            "max_file_bytes",
            "max_files",
            "osv_timeout_seconds",
            "osv_max_packages",
            "github_timeout_seconds",
        ]
        widgets = {
            field: forms.NumberInput(attrs={"class": "field", "min": 1})
            for field in [
                "clone_timeout_seconds",
                "clone_depth",
                "max_repo_size_mb",
                "reschedule_hours",
                "schedule_check_hours",
                "scanner_timeout_seconds",
                "max_findings_per_scanner",
                "max_file_bytes",
                "max_files",
                "osv_timeout_seconds",
                "osv_max_packages",
                "github_timeout_seconds",
            ]
        }
        labels = {
            "clone_timeout_seconds": "Clone timeout (seconds)",
            "clone_depth": "Clone depth",
            "max_repo_size_mb": "Max repository size (MB)",
            "reschedule_hours": "Reschedule after (hours)",
            "schedule_check_hours": "Schedule check interval (hours)",
            "scanner_timeout_seconds": "Scanner timeout (seconds)",
            "max_findings_per_scanner": "Max findings per scanner",
            "max_file_bytes": "Max file size (bytes)",
            "max_files": "Max files per scan",
            "osv_timeout_seconds": "OSV lookup timeout (seconds)",
            "osv_max_packages": "OSV max packages",
            "github_timeout_seconds": "GitHub API timeout (seconds)",
        }
        help_texts = {
            "clone_timeout_seconds": "Abort a clone that exceeds this duration.",
            "clone_depth": "Shallow clone depth. Use 1 for tip-only.",
            "max_repo_size_mb": "Refuse clones larger than this size.",
            "reschedule_hours": (
                "Enqueue a scheduled scan when the last finished scan is older "
                "than this many hours."
            ),
            "schedule_check_hours": (
                "How often Celery beat looks for due repos. Restart the beat "
                "process after changing this."
            ),
            "scanner_timeout_seconds": "Soft time budget for each scanner.",
            "max_findings_per_scanner": "Cap findings from a single scanner run.",
            "max_file_bytes": "Skip individual files above this size.",
            "max_files": "Stop walking the workspace after this many files.",
            "osv_timeout_seconds": "HTTP timeout for OSV.dev advisory lookups.",
            "osv_max_packages": "Max packages queried against OSV per scan.",
            "github_timeout_seconds": (
                "HTTP timeout for GitHub API calls made by scanners "
                "(for example branch protection)."
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_confirm_password(self):
        password = self.cleaned_data.get("confirm_password") or ""
        user = self.user
        if user is None or not user.is_superuser:
            raise forms.ValidationError(
                "Only a superuser can change technical configurations."
            )
        if not user.has_usable_password():
            raise forms.ValidationError(
                "This account has no password. Set one with "
                "`createsuperuser` or `changepassword` before editing "
                "host-wide settings."
            )
        if not user.check_password(password):
            raise forms.ValidationError("Incorrect password.")
        return password

    def clean_clone_timeout_seconds(self):
        return max(30, int(self.cleaned_data["clone_timeout_seconds"]))

    def clean_clone_depth(self):
        return max(1, int(self.cleaned_data["clone_depth"]))

    def clean_max_repo_size_mb(self):
        return max(1, int(self.cleaned_data["max_repo_size_mb"]))

    def clean_reschedule_hours(self):
        return max(1, int(self.cleaned_data["reschedule_hours"]))

    def clean_schedule_check_hours(self):
        return max(1, int(self.cleaned_data["schedule_check_hours"]))

    def clean_scanner_timeout_seconds(self):
        return max(5, int(self.cleaned_data["scanner_timeout_seconds"]))

    def clean_max_findings_per_scanner(self):
        return max(1, int(self.cleaned_data["max_findings_per_scanner"]))

    def clean_max_file_bytes(self):
        return max(1, int(self.cleaned_data["max_file_bytes"]))

    def clean_max_files(self):
        return max(1, int(self.cleaned_data["max_files"]))

    def clean_osv_timeout_seconds(self):
        return max(1, int(self.cleaned_data["osv_timeout_seconds"]))

    def clean_osv_max_packages(self):
        return max(1, int(self.cleaned_data["osv_max_packages"]))

    def clean_github_timeout_seconds(self):
        return max(1, int(self.cleaned_data["github_timeout_seconds"]))
