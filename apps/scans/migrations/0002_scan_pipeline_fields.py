from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scans", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="scan",
            name="celery_task_id",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="scan",
            name="commit_sha",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="scan",
            name="default_branch",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="scan",
            name="error_message",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="scan",
            name="trigger",
            field=models.CharField(
                choices=[("manual", "Manual"), ("scheduled", "Scheduled")],
                db_index=True,
                default="manual",
                max_length=20,
            ),
        ),
    ]
