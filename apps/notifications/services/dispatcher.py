"""Send freshly queued outbox rows without making the HTTP request wait for SMTP.

After a transaction commits, the ids of its new rows go to one daemon worker thread (started once per
process). The thread sends everything waiting for it over a single SMTP connection. The outbox stays the
source of truth: if the thread dies or the server restarts, `send_outbox` still sends the PENDING rows, and
the claim lease in `sender._claim` keeps the two from sending the same row twice.

With `EMAIL_WORKER_SYNC = True` (tests) the ids are sent in the calling thread instead.
"""

import logging
import queue
import threading

from django.conf import settings
from django.db import connections, transaction

logger = logging.getLogger(__name__)

_queue: queue.Queue = queue.Queue()
_lock = threading.Lock()
_thread: threading.Thread | None = None


def after_commit(ids: list[int]) -> None:
    """Hand these outbox ids to the sender once the surrounding transaction has committed."""
    ids = list(ids)
    if ids:
        transaction.on_commit(lambda: dispatch(ids))


def dispatch(ids: list[int]) -> None:
    if getattr(settings, "EMAIL_WORKER_SYNC", False):
        _send(ids)
        return
    _ensure_thread()
    _queue.put(ids)


def wait_idle(timeout: float = 10.0) -> bool:
    """Block until the worker has sent everything handed to it (used by tests and shutdown)."""
    done = threading.Event()
    threading.Thread(target=lambda: (_queue.join(), done.set()), daemon=True).start()
    return done.wait(timeout)


def _send(ids: list[int]) -> None:
    from .sender import send_pending

    try:
        send_pending(limit=max(len(ids), 1), ids=ids)
    except Exception:  # noqa: BLE001 - rows stay PENDING; send_outbox retries once their lease runs out
        logger.exception("Background email send failed")


def _ensure_thread() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_run, name="email-sender", daemon=True)
            _thread.start()


def _run() -> None:
    while True:
        ids = list(_queue.get())
        taken = 1
        while True:  # whatever else is waiting goes out on the same connection
            try:
                ids += _queue.get_nowait()
                taken += 1
            except queue.Empty:
                break
        try:
            _send(ids)
        finally:
            connections.close_all()  # this thread's own database connection
            for _ in range(taken):
                _queue.task_done()
