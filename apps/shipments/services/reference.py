"""DSF-YYYY-NNNN reference numbers, reset every year."""

from django.db import IntegrityError, transaction

from ..models import ReferenceCounter
from .validation import today_rome


def next_reference(year: int | None = None) -> str:
    """Next free reference for `year`. Must run inside a transaction: the counter row is locked until commit,
    so two concurrent creates get different numbers."""
    year = year or today_rome().year
    try:
        with transaction.atomic():
            ReferenceCounter.objects.get_or_create(year=year)
    except IntegrityError:  # another transaction created the row first
        pass
    counter = ReferenceCounter.objects.select_for_update().get(year=year)
    counter.last_number += 1
    counter.save(update_fields=["last_number"])
    return f"DSF-{year}-{counter.last_number:04d}"
