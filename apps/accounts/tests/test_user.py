import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_email_lowercased_and_unique_case_insensitively():
    u = User.objects.create_user("A@x.com", first_name="A", last_name="B")
    assert u.email == "a@x.com"
    assert not u.has_usable_password()
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("a@X.com")


def test_db_constraint_catches_case_variants_even_without_save_normalisation():
    User.objects.create_user("b@x.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="B@x.com")])
