import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from rest_framework.test import APIClient

from apps.accounts.enums import AppRole
from apps.accounts.models import User
from apps.accounts.services.roles import assign_role

CODE = "123456"


@pytest.fixture(autouse=True)
def fixed_otp_code(monkeypatch):
    """Make generated one-time codes predictable (codes are hashed, so tests cannot read them back)."""
    monkeypatch.setattr("apps.accounts.services.otp.secrets.randbelow", lambda n: int(CODE))
    return CODE


@pytest.fixture(autouse=True)
def no_email_redirect(settings):
    """The developer .env may set EMAIL_REDIRECT_TO; tests must not depend on it."""
    settings.EMAIL_REDIRECT_TO = ""


@pytest.fixture(autouse=True)
def email_worker_in_request(settings):
    """Emails are sent in the calling thread so tests stay deterministic (the thread has its own tests)."""
    settings.EMAIL_WORKER_SYNC = True


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_user(db):
    def _make(email="m.rossi@diasorin.com", *, admin=False, customer_management=False, **kw):
        user = User.objects.create_user(email, first_name=kw.pop("first_name", "Test"), **kw)
        if admin:
            assign_role(user, AppRole.ADMIN)
        if customer_management:
            assign_role(user, AppRole.CUSTOMER_MANAGEMENT)
        return user

    return _make


@pytest.fixture
def sign_in(api):
    """Real OTP sign-in through the API; returns the client."""

    def _sign_in(email, client=None):
        c = client or api
        assert c.post("/api/auth/request-code", {"email": email}, format="json").status_code == 200
        r = c.post("/api/auth/verify", {"email": email, "code": CODE}, format="json")
        assert r.status_code == 200, r.content
        return c

    return _sign_in


def _is_transactional(item) -> bool:
    marker = item.get_closest_marker("django_db")
    return bool(marker and (marker.kwargs.get("transaction") or (marker.args and marker.args[0])))


@pytest.fixture(autouse=True)
def _keep_seed_data_across_transactional_tests(request, django_db_blocker):
    """A transaction=True test truncates every table when it ends, taking the master data the migrations
    seeded with it. Snapshot it before such a test; `pytest_runtest_teardown` below puts it back."""
    if _is_transactional(request.node):
        with django_db_blocker.unblock():
            request.node._seed_snapshot = connection.creation.serialize_db_to_string()
    yield


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_teardown(item, nextitem):
    yield  # fixtures (including the table flush) are torn down now
    snapshot = getattr(item, "_seed_snapshot", None)
    blocker = item.funcargs.get("django_db_blocker") if snapshot else None
    if blocker is not None:
        with blocker.unblock():
            ContentType.objects.all().delete()  # post_migrate re-created them; the snapshot brings the originals
            connection.creation.deserialize_db_from_string(snapshot)
