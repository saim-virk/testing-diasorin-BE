import time

from django.core.management.base import BaseCommand

from apps.notifications.services.sender import send_pending


class Command(BaseCommand):
    help = "Deliver queued emails (EmailOutbox PENDING rows). Use --watch to keep polling."

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true", help="Poll every --interval seconds.")
        parser.add_argument("--interval", type=int, default=5)

    def handle(self, *args, **opts):
        while True:
            counts = send_pending()
            if any(counts.values()) or not opts["watch"]:
                self.stdout.write(
                    f"sent={counts['sent']} failed={counts['failed']} skipped={counts['skipped']}"
                )
            if not opts["watch"]:
                return
            time.sleep(opts["interval"])
