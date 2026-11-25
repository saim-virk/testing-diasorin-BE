from django.db import migrations


def load(apps, schema_editor):
    apps.get_model("platform_config", "SiteConfig").objects.get_or_create(pk=1)
    apps.get_model("platform_config", "SyncConfig").objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("platform_config", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
