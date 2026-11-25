from django.db import migrations

FOOTER_EN = "\n\n— Diasorin Digital Shipment Form"
FOOTER_IT = "\n\n— Diasorin Modulo di Spedizione Digitale"


def load(apps, schema_editor):
    EmailTemplate = apps.get_model("notifications", "EmailTemplate")
    EmailTemplate.objects.update_or_create(
        key="approvalHeld",
        defaults=dict(
            name="Request on hold — no approver",
            recipients_description="Administrators",
            trigger_description="A request needs approval but its cost centre has no approver and the fallback is HOLD.",
            subject_en="Action needed: {{ request.reference }} is on hold — no approver for {{ request.cost_centre_code }}",
            body_en=(
                "{{ request.reference }} from {{ request.applicant_name }} needs approval, but cost centre "
                "{{ request.cost_centre_code }} has no approver. The request is on hold until you assign one.\n"
                "Open it here: {{ url }}" + FOOTER_EN
            ),
            subject_it="Azione richiesta: {{ request.reference }} è in attesa — nessun approvatore per {{ request.cost_centre_code }}",
            body_it=(
                "{{ request.reference }} di {{ request.applicant_name }} richiede approvazione, ma il centro di costo "
                "{{ request.cost_centre_code }} non ha approvatori. La richiesta resta in attesa finché non ne assegni uno.\n"
                "Aprila qui: {{ url }}" + FOOTER_IT
            ),
        ),
    )


class Migration(migrations.Migration):
    dependencies = [("notifications", "0004_seed_italian_templates")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
