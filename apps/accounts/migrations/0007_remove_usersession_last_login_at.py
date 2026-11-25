from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_copy_last_login")]

    operations = [
        migrations.DeleteModel(name="UserSession"),
        migrations.RemoveField(model_name="user", name="last_login_at"),
    ]
