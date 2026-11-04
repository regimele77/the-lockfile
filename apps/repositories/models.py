from django.conf import settings
from django.db import models
from django.utils import timezone


class RepositoryQuerySet(models.QuerySet):
    def for_user(self, user):
        """Repos belonging to installations owned by this user."""
        return self.filter(installation__user=user)

    def selected(self):
        return self.filter(is_selected=True)

    def selected_for_user(self, user):
        return self.for_user(user).selected()


class Repository(models.Model):
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=512, unique=True)
    github_id = models.BigIntegerField(unique=True)
    is_private = models.BooleanField(default=False)
    installation = models.ForeignKey(
        "accounts.GitHubInstallation",
        on_delete=models.CASCADE,
        related_name="repositories",
    )
    # Denormalized owner for simple scoping and admin filters.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="repositories",
        null=True,
        blank=True,
    )
    is_selected = models.BooleanField(default=False)
    tracked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = RepositoryQuerySet.as_manager()

    class Meta:
        ordering = ["full_name"]
        verbose_name_plural = "repositories"

    def __str__(self) -> str:
        return self.full_name

    def mark_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self.tracked_at = timezone.now() if selected else None
