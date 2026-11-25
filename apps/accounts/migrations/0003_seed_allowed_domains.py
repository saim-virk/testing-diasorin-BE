from django.db import migrations

DOMAINS = ["diasorin.com", "diasorin.it", "diasorin-inc.com"]


def load(apps, schema_editor):
    AllowedDomain = apps.get_model("accounts", "AllowedDomain")
    for d in DOMAINS:
        AllowedDomain.objects.get_or_create(domain=d)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
