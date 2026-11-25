import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

YESNO = [("YES", "Yes"), ("NO", "No")]
ACTOR_ROLES = [
    ("requester", "Requester"),
    ("approver", "Cost Centre Approver"),
    ("customer_management", "Customer Management"),
    ("admin", "Administrator"),
    ("system", "System"),
]
CURRENCIES = [
    (c, c) for c in "EUR USD GBP CHF JPY CNY CAD AUD SEK DKK NOK PLN CZK HUF".split()
]


def _s(n):
    return models.CharField(blank=True, max_length=n, null=True)


def _yn():
    return models.CharField(blank=True, choices=YESNO, max_length=3, null=True)


class Migration(migrations.Migration):
    dependencies = [
        ("shipments", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # reason label snapshots (B3) and branch name snapshot (B4)
        migrations.RenameField("shipmentrequest", "reason_label", "reason_label_en"),
        migrations.AddField("shipmentrequest", "reason_label_it", _s(255)),
        migrations.AddField("shipmentrequest", "recipient_branch_name", _s(200)),
        # raw-material details merged in (A4)
        migrations.AddField("shipmentrequest", "rm_description", _s(255)),
        migrations.AddField(
            "shipmentrequest",
            "rm_kind",
            models.CharField(
                blank=True,
                choices=[("TEST_SAMPLE", "Test sample"), ("MAIN_SHIPMENT", "Main shipment")],
                max_length=14,
                null=True,
            ),
        ),
        migrations.AddField("shipmentrequest", "rm_protein", _s(100)),
        migrations.AddField("shipmentrequest", "rm_lot_number", _s(60)),
        migrations.AddField("shipmentrequest", "rm_quantity", _s(60)),
        migrations.AddField(
            "shipmentrequest", "rm_number_of_vials", models.PositiveIntegerField(blank=True, null=True)
        ),
        migrations.AddField("shipmentrequest", "rm_leftover_stock", _s(100)),
        migrations.AddField("shipmentrequest", "rm_article_number", _s(60)),
        migrations.AddField("shipmentrequest", "rm_date_of_shipment", models.DateField(blank=True, null=True)),
        # US requirements merged in (A5)
        migrations.AddField("shipmentrequest", "us_usda_guideline", _yn()),
        migrations.AddField("shipmentrequest", "us_usda_guideline_number", _s(60)),
        migrations.AddField("shipmentrequest", "us_usda_permit", _yn()),
        migrations.AddField("shipmentrequest", "us_attach_000614", _yn()),
        migrations.AddField("shipmentrequest", "us_cdc_permit", _yn()),
        migrations.AddField("shipmentrequest", "us_importer_certification_statement", _yn()),
        # inventory link goes (A9)
        migrations.RemoveField("requestline", "inventory_item"),
        migrations.AlterField(
            "requestline",
            "currency",
            models.CharField(blank=True, choices=CURRENCIES, max_length=3, null=True),
        ),
        # parcel confirmation (B6)
        migrations.AddField("parcel", "confirmed_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            "parcel",
            "confirmed_by",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # one open round = PENDING or HELD (B1)
        migrations.RemoveConstraint("approvalround", "uniq_pending_round_per_request"),
        migrations.AddConstraint(
            "approvalround",
            models.UniqueConstraint(
                condition=models.Q(state__in=["PENDING", "HELD"]),
                fields=("request",),
                name="uniq_open_round_per_request",
            ),
        ),
        # events absorb comments (A6) and become undeletable with their request (B2)
        migrations.AddField(
            "requestevent",
            "kind",
            models.CharField(
                choices=[
                    ("EVENT", "Event"),
                    ("COMMENT", "Comment"),
                    ("QUESTION", "Question"),
                    ("NOTE", "Note"),
                ],
                default="EVENT",
                max_length=10,
            ),
        ),
        migrations.AddField("requestevent", "in_conversation", models.BooleanField(default=False)),
        migrations.AlterField("requestevent", "note", models.TextField(blank=True)),
        migrations.AlterField(
            "requestevent",
            "actor_role",
            models.CharField(choices=ACTOR_ROLES, default="system", max_length=20),
        ),
        migrations.AlterField(
            "requestevent",
            "request",
            models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="events",
                to="shipments.shipmentrequest",
            ),
        ),
    ]
