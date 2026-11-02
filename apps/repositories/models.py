from django.db import models


class Repository(models.Model):
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=512, unique=True)
    github_id = models.BigIntegerField(null=True, blank=True, unique=True)
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name_plural = "repositories"

    def __str__(self) -> str:
        return self.full_name
