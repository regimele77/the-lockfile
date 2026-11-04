"""User-facing scan labels (ordered numbers, not database ids)."""

from django.contrib.auth.models import AbstractBaseUser
from django.db.models import Q

from apps.repositories.models import Repository
from apps.scans.models import Scan


def user_scans_qs(user: AbstractBaseUser):
    """Scans visible to the user, newest first (stable tie-break on pk)."""
    repos = Repository.objects.selected_for_user(user)
    return (
        Scan.objects.filter(repository__in=repos)
        .select_related("repository")
        .order_by("-created_at", "-pk")
    )


def scan_ordinal(user: AbstractBaseUser, scan: Scan) -> int:
    """
    1-based position among the user's scans (1 = newest).

    Matches the Scans list order so the same scan keeps the same number.
    """
    qs = Scan.objects.filter(
        repository__in=Repository.objects.selected_for_user(user)
    )
    newer = qs.filter(
        Q(created_at__gt=scan.created_at)
        | Q(created_at=scan.created_at, pk__gt=scan.pk)
    ).count()
    return newer + 1
