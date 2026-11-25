"""Email backends for tests: count SMTP sessions and simulate a slow server (SSL + login takes seconds)."""

import threading
import time

from django.core.mail.backends.base import BaseEmailBackend


class SlowSession(BaseEmailBackend):
    delay = 0.0
    opened = 0
    sent: list = []
    lock = threading.Lock()

    @classmethod
    def reset(cls, delay=0.0):
        cls.delay, cls.opened, cls.sent = delay, 0, []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._is_open = False

    def open(self):
        if self._is_open:
            return False
        time.sleep(self.delay)
        with self.lock:
            type(self).opened += 1
        self._is_open = True
        return True

    def close(self):
        self._is_open = False

    def send_messages(self, messages):
        opened_here = self.open()
        try:
            with self.lock:
                type(self).sent.extend(m.subject for m in messages)
            return len(messages)
        finally:
            if opened_here:
                self.close()
