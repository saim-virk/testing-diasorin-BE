import threading

import pytest
from django.db import connection, transaction

from apps.shipments.models import ReferenceCounter
from apps.shipments.services.reference import next_reference


@pytest.mark.django_db
def test_sequential_and_formatted():
    with transaction.atomic():
        assert next_reference(2026) == "DSF-2026-0001"
        assert next_reference(2026) == "DSF-2026-0002"


@pytest.mark.django_db
def test_resets_every_year():
    with transaction.atomic():
        assert next_reference(2026) == "DSF-2026-0001"
        assert next_reference(2026) == "DSF-2026-0002"
        assert next_reference(2027) == "DSF-2027-0001"
        assert next_reference(2026) == "DSF-2026-0003"


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_creates_get_different_numbers():
    results, errors = [], []
    barrier = threading.Barrier(2)

    def worker():
        try:
            barrier.wait()
            with transaction.atomic():
                results.append(next_reference(2030))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert sorted(results) == ["DSF-2030-0001", "DSF-2030-0002"]
    assert ReferenceCounter.objects.get(year=2030).last_number == 2
