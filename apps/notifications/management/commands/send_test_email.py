from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.services.mailconfig import build_message
from apps.platform_config.models import SiteConfig


class Command(BaseCommand):
    help = "Send one test message through the full sender path (redirect + From override)."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Recipient (required unless EMAIL_REDIRECT_TO is set).")

    def handle(self, *args, **opts):
        sender = SiteConfig.load().sender_email or settings.DEFAULT_FROM_EMAIL
        to = opts["to"] or settings.EMAIL_REDIRECT_TO
        if not to:
            raise CommandError(
                "Pass --to <address> (or set EMAIL_REDIRECT_TO): a test must never go to a real mailbox by default."
            )
        msg = build_message(
            "Diasorin shipment form: test email",
            "If you can read this, outgoing email works.",
            sender,
            [to],
        )
        self.stdout.write(
            f"backend={settings.EMAIL_BACKEND} host={settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
            f"tls={settings.EMAIL_USE_TLS} ssl={settings.EMAIL_USE_SSL}\n"
            f"from={msg.from_email} to={msg.to} subject={msg.subject!r}"
        )
        try:
            msg.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - show the SMTP error as is
            self.stderr.write(self.style.ERROR(f"FAILED: {type(exc).__name__}: {exc}"))
            raise SystemExit(1) from exc
        self.stdout.write(self.style.SUCCESS("Sent."))
