from django.db import migrations


def copy_calendar(apps, schema_editor):
    """ShippingCalendarDay rows become ShipsFromSite.allowed_weekdays (Saluggia Mon-Thu, others [])."""
    ShipsFromSite = apps.get_model("masterdata", "ShipsFromSite")
    ShippingCalendarDay = apps.get_model("masterdata", "ShippingCalendarDay")
    for site in ShipsFromSite.objects.all():
        days = sorted(
            ShippingCalendarDay.objects.filter(site=site, allowed=True).values_list("weekday", flat=True)
        )
        if site.code == "SALUGGIA" and not days:
            days = [0, 1, 2, 3]
        site.allowed_weekdays = days
        site.save(update_fields=["allowed_weekdays"])


class Migration(migrations.Migration):
    dependencies = [("masterdata", "0003_shipsfromsite_allowed_weekdays")]
    operations = [migrations.RunPython(copy_calendar, migrations.RunPython.noop)]
