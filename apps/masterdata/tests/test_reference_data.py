import pytest
from django.db import IntegrityError, transaction

from apps.masterdata.enums import Currency
from apps.masterdata.models import (
    Carrier,
    Country,
    PackagingType,
    PVARICode,
    ReasonCode,
    ShipsFromSite,
)
from apps.notifications.models import EmailTemplate

pytestmark = pytest.mark.django_db


def test_reference_counts():
    assert PVARICode.objects.count() == 11
    assert ReasonCode.objects.count() == 22
    assert ReasonCode.objects.filter(scope_group="ITALY").count() == 11
    assert ReasonCode.objects.filter(scope_group="EU_EXTRA").count() == 11
    assert PackagingType.objects.count() == 13
    # Prototype COUNTRIES holds 46 rows (the ticket text says 43 — see docs/progress/day-1.md).
    assert Country.objects.count() == 46
    assert len(Currency) == 14
    assert Carrier.objects.count() == 5
    assert EmailTemplate.objects.count() == 17
    assert ShipsFromSite.objects.count() == 3


def test_pvari_content():
    p = PVARICode.objects.get(code="P9996")
    assert p.un_number == "UN 2814"
    assert p.hazard == "INFECTIOUS"
    assert p.default_temperature == "DRY_ICE"
    assert p.description_it and p.description_en


def test_saluggia_calendar_mon_to_thu_allowed():
    site = ShipsFromSite.objects.get(code="SALUGGIA")
    assert site.applies_calendar
    assert site.allowed_weekdays == [0, 1, 2, 3]
    assert not ShipsFromSite.objects.get(code="GERENZANO").applies_calendar


def test_reason_code_unique_per_group_and_10_10a_coexist():
    assert ReasonCode.objects.filter(code="10", scope_group="ITALY").exists()
    assert ReasonCode.objects.filter(code="10A", scope_group="EU_EXTRA").exists()
    with pytest.raises(IntegrityError), transaction.atomic():
        ReasonCode.objects.create(scope_group="ITALY", code="10", description_it="x", description_en="x")
    # same code in the other group is fine
    ReasonCode.objects.create(scope_group="EU_EXTRA", code="10", description_it="x", description_en="x")


def test_reason_print_language():
    assert ReasonCode.objects.get(scope_group="ITALY", code="10").print_language == "it"
    assert ReasonCode.objects.get(scope_group="EU_EXTRA", code="01").print_language == "en"
