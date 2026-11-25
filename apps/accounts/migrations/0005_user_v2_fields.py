import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0004_user_language")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="sessions_revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="approval_exempt",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="deactivated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="deactivated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="roleassignment",
            name="role",
            field=models.CharField(
                choices=[("customer_management", "Customer Management"), ("admin", "Administrator")],
                max_length=20,
            ),
        ),
    ]
