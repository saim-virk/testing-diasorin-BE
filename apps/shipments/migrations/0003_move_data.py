from django.db import migrations

RM_FIELDS = [
    "description",
    "kind",
    "protein",
    "lot_number",
    "quantity",
    "number_of_vials",
    "leftover_stock",
    "article_number",
    "date_of_shipment",
]
US_FIELDS = [
    "usda_guideline",
    "usda_guideline_number",
    "usda_permit",
    "attach_000614",
    "cdc_permit",
    "importer_certification_statement",
]
DECISION_KINDS = {"APPROVED", "REJECTED", "RETURNED", "RESUBMITTED"}


def move(apps, schema_editor):
    ShipmentRequest = apps.get_model("shipments", "ShipmentRequest")
    RawMaterialDetail = apps.get_model("shipments", "RawMaterialDetail")
    USRequirements = apps.get_model("shipments", "USRequirements")
    Comment = apps.get_model("shipments", "Comment")
    RequestEvent = apps.get_model("shipments", "RequestEvent")

    for rm in RawMaterialDetail.objects.all():
        ShipmentRequest.objects.filter(pk=rm.request_id).update(
            **{f"rm_{f}": getattr(rm, f) for f in RM_FIELDS}
        )
    for us in USRequirements.objects.all():
        ShipmentRequest.objects.filter(pk=us.request_id).update(
            **{f"us_{f}": getattr(us, f) for f in US_FIELDS}
        )
    for c in Comment.objects.all():
        decision = c.kind in DECISION_KINDS
        RequestEvent.objects.create(
            request_id=c.request_id,
            at=c.at,
            actor_id=c.author_id,
            actor_role=c.author_role,
            kind="EVENT" if decision else c.kind,
            in_conversation=True,
            action=c.kind.lower() if decision else "comment",
            note=c.text,
        )


class Migration(migrations.Migration):
    dependencies = [("shipments", "0002_v2_schema_add")]
    operations = [migrations.RunPython(move, migrations.RunPython.noop)]
