from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.masterdata.models import ShipsFromSite

pytestmark = pytest.mark.django_db

SATURDAY, MONDAY = date(2026, 11, 21), date(2026, 11, 23)


def test_saluggia_saturday_refused_monday_accepted():
    saluggia = ShipsFromSite.objects.get(code="SALUGGIA")
    assert saluggia.allowed_weekdays == [0, 1, 2, 3]
    assert not saluggia.allows_ship_day(SATURDAY)
    assert saluggia.allows_ship_day(MONDAY)


def test_gerenzano_saturday_accepted():
    gerenzano = ShipsFromSite.objects.get(code="GERENZANO")
    assert gerenzano.allowed_weekdays == [] and not gerenzano.applies_calendar
    assert gerenzano.allows_ship_day(SATURDAY)


def test_changing_allowed_weekdays_changes_the_result_immediately():
    assert not ShipsFromSite.objects.get(code="SALUGGIA").allows_ship_day(SATURDAY)
    ShipsFromSite.objects.filter(code="SALUGGIA").update(allowed_weekdays=[0, 1, 2, 3, 5])
    assert ShipsFromSite.objects.get(code="SALUGGIA").allows_ship_day(SATURDAY)  # read fresh, never cached


def test_weekdays_are_validated_0_to_6_without_duplicates():
    site = ShipsFromSite.objects.get(code="SALUGGIA")
    site.allowed_weekdays = [0, 0]
    with pytest.raises(ValidationError):
        site.full_clean()
    site.allowed_weekdays = [7]
    with pytest.raises(ValidationError):
        site.full_clean()
    site.allowed_weekdays = [0, 6]
    site.full_clean()
