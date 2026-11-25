from django.db import migrations

from apps.notifications.seed_templates_it import TEMPLATES_IT


def load(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailOutbox = apps.get_model("notifications", "EmailOutbox")
    for key, (subject, body) in TEMPLATES_IT.items():
        EmailTemplate.objects.filter(key=key).update(subject_it=subject, body_it=body)
    # The lease used to live in sent_at on PENDING rows; it moves to next_attempt_at.
    EmailOutbox.objects.filter(status="PENDING", sent_at__isnull=False).update(sent_at=None)


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_templates_languages_next_attempt")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
