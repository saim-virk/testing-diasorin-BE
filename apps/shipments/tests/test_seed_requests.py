import pytest
from django.core.management import call_command

from apps.shipments.models import ReferenceCounter, ShipmentRequest

pytestmark = pytest.mark.django_db


def test_seed_demo_with_requests_loads_the_prototype_requests_and_is_idempotent():
    call_command("seed_demo", "--with-requests")
    assert ShipmentRequest.objects.count() == 14
    call_command("seed_demo", "--with-requests")
    assert ShipmentRequest.objects.count() == 14
    r = ShipmentRequest.objects.get(reference="DSF-2026-0185")
    assert (r.status, r.destination, r.requester.email) == ("PENDING_APPROVAL", "USA", "m.rossi@diasorin.com")
    assert r.lines.count() == 2 and r.consignee_country_name == "United States"
    assert r.approval_rounds.get().state == "PENDING"
    delivered = ShipmentRequest.objects.get(reference="DSF-2026-0171")
    assert (
        delivered.delivered_at
        and delivered.carrier_name == "World Courier"
        and delivered.dangerous_features == "INFECTIOUS"
    )
    assert delivered.events.filter(action="Approved", note__contains="approved").exists()
    assert ShipmentRequest.objects.filter(status="DRAFT").get().submitted_at is None
    assert ReferenceCounter.objects.get(year=2026).last_number == 186
