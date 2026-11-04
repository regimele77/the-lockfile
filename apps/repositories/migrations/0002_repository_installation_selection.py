import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def purge_unscoped_repositories(apps, schema_editor):
    """Scaffold repos have no installation link; clear before requiring scope."""
    Repository = apps.get_model("repositories", "Repository")
    Repository.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0001_initial"),
        ("repositories", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(purge_unscoped_repositories, migrations.RunPython.noop),
        migrations.AddField(
            model_name="repository",
            name="installation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="repositories",
                to="accounts.githubinstallation",
            ),
        ),
        migrations.AddField(
            model_name="repository",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="repositories",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="repository",
            name="is_selected",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="repository",
            name="tracked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="repository",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="repository",
            name="github_id",
            field=models.BigIntegerField(unique=True),
        ),
    ]
