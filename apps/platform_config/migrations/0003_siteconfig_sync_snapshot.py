import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_config", "0002_seed_singletons"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="sync_host",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_path",
            field=models.CharField(default="/inventory/outbound/", max_length=300),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_pattern",
            field=models.CharField(default="inventory_*.csv", max_length=100),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_archive_path",
            field=models.CharField(default="/inventory/processed/", max_length=300),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_every_minutes",
            field=models.PositiveSmallIntegerField(default=15),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_alert_hours",
            field=models.PositiveSmallIntegerField(default=24),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_on_missing",
            field=models.CharField(
                choices=[("deactivate", "Deactivate"), ("keep", "Keep")],
                default="deactivate",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="sync_notify_admins",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="ConfigSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=100)),
                ("taken_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("data", models.JSONField()),
                (
                    "taken_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-taken_at"]},
        ),
    ]
