from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete expired Django sessions (run daily from Task Scheduler)."

    def handle(self, *args, **opts):
        call_command("clearsessions")
        self.stdout.write("Expired sessions removed.")
