"""Load the prototype's sample people, branches, cost centres and access lists. Idempotent. Dev only."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.enums import AppRole
from apps.accounts.models import AllowedEmail, BlockedEmail, User
from apps.accounts.services.roles import assign_role
from apps.masterdata.models import Branch, CostCentre, CostCentreApprover, Country
from apps.platform_config.models import SiteConfig

# email, first, last, department, job title, phone, default cost centre
DIRECTORY = [
    (
        "m.rossi@diasorin.com",
        "Marco",
        "Rossi",
        "Warehouse & Distribution",
        "Warehouse coordinator",
        "+39 335 118 4402",
        "CC-4410",
    ),
    (
        "g.ferrari@diasorin.com",
        "Giulia",
        "Ferrari",
        "Finance & Controlling",
        "Cost centre manager",
        "+39 335 771 2208",
        "CC-4410",
    ),
    (
        "l.conti@diasorin.com",
        "Luca",
        "Conti",
        "Commercial Operations",
        "Cost centre manager",
        "+39 335 660 9014",
        "CC-3300",
    ),
    (
        "p.moretti@diasorin.com",
        "Paolo",
        "Moretti",
        "Customer Management",
        "Customer management specialist",
        "+39 335 442 1180",
        "CC-4410",
    ),
    (
        "logistica@diasorin.com",
        "Logistics",
        "Mailbox",
        "Procurement & Logistics",
        "Shared mailbox",
        "+39 0161 487 100",
        "CC-4410",
    ),
    (
        "admin@diasorin.com",
        "Sara",
        "Bianchi",
        "IT & Digital",
        "Platform administrator",
        "+39 335 220 5567",
        "CC-6200",
    ),
    (
        "a.greco@diasorin.com",
        "Anna",
        "Greco",
        "Quality Assurance",
        "QA specialist",
        "+39 335 908 3321",
        "CC-6200",
    ),
    (
        "e.bruni@diasorin.com",
        "Elena",
        "Bruni",
        "Molecular Diagnostics",
        "Field application specialist",
        "+39 335 902 7711",
        "CC-7300",
    ),
    (
        "f.russo@diasorin.com",
        "Franco",
        "Russo",
        "Field Service",
        "Service engineer",
        "+39 335 512 6690",
        "CC-5100",
    ),
    ("ex.employee@diasorin.com", "Former", "Employee", "—", "Left the company", "", "CC-4410"),
]

# code, name, approval_required, approvers
COST_CENTRES = [
    ("CC-4410", "Warehouse & Distribution — Saluggia", True, ["g.ferrari@diasorin.com"]),
    ("CC-2210", "R&D Clinical Affairs — Gerenzano", True, ["g.ferrari@diasorin.com", "l.conti@diasorin.com"]),
    ("CC-3300", "Global Marketing — Saluggia", False, ["l.conti@diasorin.com"]),
    ("CC-5100", "Field Service — Italy", True, ["g.ferrari@diasorin.com"]),
    ("CC-6200", "Quality Assurance — Saluggia", True, []),
    ("CC-7300", "Molecular Diagnostics — Gerenzano", True, ["l.conti@diasorin.com"]),
]

# code, name, scope, country iso2
BRANCHES = [
    ("DS-IT-SAL", "Diasorin Italia S.p.A. — Saluggia (IT)", "ITALY", "IT"),
    ("DS-IT-GER", "Diasorin Italia S.p.A. — Gerenzano (IT)", "ITALY", "IT"),
    ("DS-DE-DIE", "Diasorin Deutschland GmbH — Dietzenbach (DE)", "EU", "DE"),
    ("DS-FR-ANT", "Diasorin France SAS — Antony (FR)", "EU", "FR"),
    ("DS-ES-MAD", "Diasorin Iberia S.A. — Madrid (ES)", "EU", "ES"),
    ("DS-BE-BRU", "Diasorin Benelux — Brussels (BE)", "EU", "BE"),
    ("DS-UK-DAR", "Diasorin Ltd — Dartford (UK)", "EXTRA_EU", "GB"),
    ("DS-CH-ZUR", "Diasorin Schweiz AG — Zürich (CH)", "EXTRA_EU", "CH"),
    ("DS-BR-SAO", "Diasorin Brasil — São Paulo (BR)", "EXTRA_EU", "BR"),
    ("DS-US-STW", "Diasorin Inc. — Stillwater, MN (US)", "USA", "US"),
    ("DS-US-AUS", "Diasorin Molecular LLC — Austin, TX (US)", "USA", "US"),
]

# DS Inc branches: PO number mandatory when SiteConfig.po_mandatory_us is on
PO_REQUIRED_BRANCHES = {"DS-US-STW"}

CUSTOMER_MANAGEMENT = ["p.moretti@diasorin.com", "logistica@diasorin.com"]
ADMINS = ["admin@diasorin.com"]


class Command(BaseCommand):
    help = "Load sample people, branches, cost centres and access lists (idempotent, dev only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-requests",
            action="store_true",
            help="Also load the prototype's sample requests (14, idempotent).",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        centres = {}
        for code, name, approval, _ in COST_CENTRES:
            centres[code], _created = CostCentre.objects.update_or_create(
                code=code, defaults={"name": name, "approval_required": approval, "is_active": True}
            )

        users = {}
        for email, first, last, dept, title, phone, cc in DIRECTORY:
            user, _created = User.objects.get_or_create(email=email)
            user.first_name, user.last_name = first, last
            user.department, user.job_title, user.phone = dept, title, phone
            user.default_cost_centre = centres[cc]
            if _created:
                user.set_unusable_password()
            user.save()
            users[email] = user

        for code, _name, _appr, approvers in COST_CENTRES:
            for email in approvers:
                CostCentreApprover.objects.get_or_create(cost_centre=centres[code], user=users[email])

        admin_user = users[ADMINS[0]]
        for email in CUSTOMER_MANAGEMENT:
            assign_role(users[email], AppRole.CUSTOMER_MANAGEMENT, added_by=admin_user)
        for email in ADMINS:
            assign_role(users[email], AppRole.ADMIN, added_by=admin_user)  # also sets is_staff + is_superuser

        countries = {c.iso2: c for c in Country.objects.all()}
        for code, name, scope, iso2 in BRANCHES:
            Branch.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "scope": scope,
                    "country": countries.get(iso2),
                    "is_active": True,
                    "po_required": code in PO_REQUIRED_BRANCHES,  # DS Inc only (DSF-03.06)
                },
            )

        AllowedEmail.objects.get_or_create(
            email="consultant.ext@partner-lab.it",
            defaults={"note": "External consultant — Gerenzano validation study", "added_by": admin_user},
        )
        BlockedEmail.objects.get_or_create(
            email="ex.employee@diasorin.com",
            defaults={"reason": "Left the company — 30 Sep 2026", "added_by": admin_user},
        )
        BlockedEmail.objects.get_or_create(
            email="temp.agency@diasorin.it",
            defaults={"reason": "Agency contract ended", "added_by": admin_user},
        )
        User.objects.filter(email="a.greco@diasorin.com").update(approval_exempt=True)

        SiteConfig.load()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(DIRECTORY)} people, {len(COST_CENTRES)} cost centres, {len(BRANCHES)} branches."
            )
        )
        if opts["with_requests"]:
            from apps.shipments.seed_requests import load_prototype_requests

            made = load_prototype_requests()
            self.stdout.write(
                self.style.SUCCESS(f"Loaded {made} sample requests (existing ones left alone).")
            )
