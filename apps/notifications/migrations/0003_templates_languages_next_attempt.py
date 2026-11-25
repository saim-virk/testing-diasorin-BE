from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("notifications", "0002_seed_email_templates")]

    operations = [
        migrations.RenameField("emailtemplate", "subject_template", "subject_en"),
        migrations.RenameField("emailtemplate", "body_template", "body_en"),
        migrations.AddField(
            model_name="emailtemplate",
            name="subject_it",
            field=models.CharField(blank=True, default="", max_length=300),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="body_it",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailoutbox",
            name="next_attempt_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
