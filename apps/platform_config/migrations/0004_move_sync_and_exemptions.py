from django.db import migrations

SYNC_FIELDS = {
    "host": "sync_host",
    "path": "sync_path",
    "pattern": "sync_pattern",
    "archive_path": "sync_archive_path",
    "every_minutes": "sync_every_minutes",
    "alert_hours": "sync_alert_hours",
    "on_missing": "sync_on_missing",
    "notify_admins": "sync_notify_admins",
}


def move(apps, schema_editor):
    SiteConfig = apps.get_model("platform_config", "SiteConfig")
    SyncConfig = apps.get_model("platform_config", "SyncConfig")
    ApprovalExemption = apps.get_model("platform_config", "ApprovalExemption")
    User = apps.get_model("accounts", "User")

    site, _ = SiteConfig.objects.get_or_create(pk=1)
    sync = SyncConfig.objects.filter(pk=1).first()
    if sync is not None:
        for old, new in SYNC_FIELDS.items():
            setattr(site, new, getattr(sync, old))
        site.save()

    user_ids = list(ApprovalExemption.objects.values_list("user_id", flat=True))
    User.objects.filter(pk__in=user_ids).update(approval_exempt=True)


class Migration(migrations.Migration):
    dependencies = [
        ("platform_config", "0003_siteconfig_sync_snapshot"),
        ("accounts", "0005_user_v2_fields"),
    ]
    operations = [migrations.RunPython(move, migrations.RunPython.noop)]
