from django.db import migrations

from apps.masterdata import seed_reference as seed


def load(apps, schema_editor):
    PVARICode = apps.get_model("masterdata", "PVARICode")
    ReasonCode = apps.get_model("masterdata", "ReasonCode")
    PackagingType = apps.get_model("masterdata", "PackagingType")
    Country = apps.get_model("masterdata", "Country")
    Currency = apps.get_model("masterdata", "Currency")
    Carrier = apps.get_model("masterdata", "Carrier")
    ShipsFromSite = apps.get_model("masterdata", "ShipsFromSite")
    ShippingCalendarDay = apps.get_model("masterdata", "ShippingCalendarDay")

    for code, it, en, un, hazard, temp in seed.PVARI:
        PVARICode.objects.update_or_create(
            code=code,
            defaults=dict(
                description_it=it, description_en=en, un_number=un, hazard=hazard, default_temperature=temp
            ),
        )
    for group, code, it, en in seed.REASON_CODES:
        ReasonCode.objects.update_or_create(
            scope_group=group, code=code, defaults=dict(description_it=it, description_en=en)
        )
    for code, dims, desc in seed.PACKAGING:
        PackagingType.objects.update_or_create(code=code, defaults=dict(dimensions=dims, description=desc))
    for iso2, name, scope in seed.COUNTRIES:
        Country.objects.update_or_create(iso2=iso2, defaults=dict(name=name, scope=scope))
    for code in seed.CURRENCIES:
        Currency.objects.get_or_create(code=code)
    for name in seed.CARRIERS:
        Carrier.objects.get_or_create(name=name)
    for code, name, applies in seed.SHIPS_FROM:
        site, _ = ShipsFromSite.objects.update_or_create(
            code=code, defaults=dict(name=name, applies_calendar=applies)
        )
        if code == "SALUGGIA":
            for weekday in range(7):
                ShippingCalendarDay.objects.update_or_create(
                    site=site,
                    weekday=weekday,
                    defaults=dict(allowed=weekday in seed.SALUGGIA_ALLOWED_WEEKDAYS),
                )


class Migration(migrations.Migration):
    dependencies = [("masterdata", "0001_initial")]
    operations = [migrations.RunPython(load, migrations.RunPython.noop)]
