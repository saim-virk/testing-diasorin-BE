"""Sign-in access decision (REQUIREMENTS §2)."""

import re
from dataclasses import dataclass

from apps.platform_config.models import AccessMode, SiteConfig

from ..models import AllowedDomain, AllowedEmail, BlockedEmail, User

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True)
class Decision:
    ok: bool
    code: str  # format | blocked | notlisted | domain | allowlist
    message: str


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1]


def holds_role(email: str) -> bool:
    """True if the address belongs to a user with any role beyond requester (incl. approver mapping)."""
    from .roles import roles_for

    user = User.objects.filter(email__iexact=email).first()
    return bool(user) and len(roles_for(user)) > 1


def access_decision(email: str) -> Decision:
    e = normalize_email(email)
    if not EMAIL_RE.match(e):
        return Decision(False, "format", "That does not look like an email address.")

    blocked = BlockedEmail.objects.filter(email__iexact=e).first()
    if blocked:
        why = f" — {blocked.reason}" if blocked.reason else ""
        return Decision(False, "blocked", f"This address has been blocked by the administrator{why}.")

    cfg = SiteConfig.load()
    listed = AllowedEmail.objects.filter(email__iexact=e).exists()

    if cfg.access_mode == AccessMode.ALLOWLIST:
        if listed or holds_role(e):
            return Decision(True, "allowlist", "Address is on the allow-list or holds a role.")
        return Decision(
            False,
            "notlisted",
            "Access is restricted to addresses on the allow-list. Ask the administrator to add you.",
        )

    domain = domain_of(e)
    if AllowedDomain.objects.filter(domain__iexact=domain).exists():
        return Decision(True, "domain", f"Domain “{domain}” is allowed.")
    if listed or holds_role(e):
        return Decision(True, "allowlist", "Address is explicitly allowed by the administrator.")
    domains = ", ".join(AllowedDomain.objects.values_list("domain", flat=True)) or "—"
    return Decision(
        False, "domain", f"“{domain}” is not an allowed domain. Access is restricted to {domains}."
    )
