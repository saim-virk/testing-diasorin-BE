from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("masterdata", "0004_copy_calendar_to_weekdays")]

    operations = [
        migrations.DeleteModel(name="ShippingCalendarDay"),
        migrations.DeleteModel(name="Currency"),
    ]
