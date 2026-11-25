"""Submit must not wait for SMTP (the day-4 "emails make submit slow" fix)."""

import time

import pytest

from apps.notifications.models import EmailOutbox, OutboxStatus
from apps.notifications.services import dispatcher
from apps.notifications.tests.fake_backends import SlowSession


@pytest.mark.django_db(transaction=True)
def test_submit_returns_without_waiting_on_a_slow_smtp_server(settings, marco_api, complete_draft):
    d = complete_draft()  # fixtures ran with the in-request sender; now switch to the background worker
    settings.EMAIL_BACKEND = "apps.notifications.tests.fake_backends.SlowSession"
    settings.EMAIL_WORKER_SYNC = False
    SlowSession.reset(delay=2.0)  # opening a session (SSL + login) takes 2 s

    started = time.monotonic()
    r = marco_api.post(f"/api/requests/{d['reference']}/submit", {"declaration": True}, format="json")
    elapsed = time.monotonic() - started

    assert r.status_code == 200, r.content
    assert elapsed < 0.5, f"submit took {elapsed:.2f}s"
    assert dispatcher.wait_idle(20)
    assert SlowSession.opened == 1  # all of this request's emails over one session
    assert len(SlowSession.sent) >= 2  # submitted + approvalRequired
    assert not EmailOutbox.objects.filter(status=OutboxStatus.PENDING, request__reference=d["reference"])
