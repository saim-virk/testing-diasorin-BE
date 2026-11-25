from django.db import migrations

from apps.notifications.seed_templates import TEMPLATES


def load(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    for key, name, recipients, trigger, subject, body in TEMPLATES:
        EmailTemplate.objects.update_or_create(
            key=key,
            defaults=dict(
                name=name,
                recipients_description=recipients,
                trigger_description=trigger,
                subject_template=subject,
                body_template=body,
            ),
        )


class Migration(migrations.Migration):
    dependencies = [("notifications", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
