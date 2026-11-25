from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.platform_config.services.snapshot import take_snapshot


class Command(BaseCommand):
    help = "Store a snapshot of the current configuration (used by the go-live reset)."

    def add_arguments(self, parser):
        parser.add_argument("--label", default="go-live")
        parser.add_argument("--by", help="Email of the administrator taking the snapshot.")

    def handle(self, *args, **opts):
        by = User.objects.filter(email__iexact=opts["by"]).first() if opts["by"] else None
        snap = take_snapshot(opts["label"], by)
        sections = ", ".join(snap.data)
        self.stdout.write(self.style.SUCCESS(f"Snapshot #{snap.pk} '{snap.label}' saved: {sections}"))
