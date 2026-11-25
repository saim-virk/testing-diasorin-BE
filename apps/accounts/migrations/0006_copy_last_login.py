from django.db import migrations
from django.db.models import F


def copy_last_login(apps, schema_editor):
    """User.last_login_at is replaced by Django's own last_login."""
    User = apps.get_model("accounts", "User")
    User.objects.filter(last_login__isnull=True, last_login_at__isnull=False).update(
        last_login=F("last_login_at")
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_user_v2_fields")]
    operations = [migrations.RunPython(copy_last_login, migrations.RunPython.noop)]
