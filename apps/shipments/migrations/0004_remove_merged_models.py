from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("shipments", "0003_move_data")]

    operations = [
        migrations.DeleteModel(name="RawMaterialDetail"),
        migrations.DeleteModel(name="USRequirements"),
        migrations.DeleteModel(name="Comment"),
        migrations.RemoveField(model_name="shipmentrequest", name="has_infectious"),
        migrations.RemoveField(model_name="approvalround", name="decision_comment"),
    ]
