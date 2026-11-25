from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("platform_config", "0004_move_sync_and_exemptions")]

    operations = [
        migrations.DeleteModel(name="SyncConfig"),
        migrations.DeleteModel(name="ApprovalExemption"),
        migrations.RemoveField(model_name="siteconfig", name="config_dirty_count"),
    ]
