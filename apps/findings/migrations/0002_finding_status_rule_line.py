from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("findings", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="finding",
            name="line_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="finding",
            name="rule_id",
            field=models.CharField(
                blank=True, db_index=True, default="", max_length=128
            ),
        ),
        migrations.AddField(
            model_name="finding",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("resolved", "Resolved"),
                    ("ignored", "Ignored"),
                ],
                db_index=True,
                default="open",
                max_length=20,
            ),
        ),
    ]
