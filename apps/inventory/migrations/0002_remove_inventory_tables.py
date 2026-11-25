from django.db import migrations


class Migration(migrations.Migration):
    """Inventory tables are deferred until the SAP file layout is known (PLAN W4)."""

    dependencies = [
        ("inventory", "0001_initial"),
        ("shipments", "0002_v2_schema_add"),  # RequestLine.inventory_item is gone
    ]

    operations = [
        migrations.DeleteModel(name="SyncRejectedRow"),
        migrations.DeleteModel(name="InventoryItem"),
        migrations.DeleteModel(name="SyncRun"),
    ]
