from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SelfApprovalMode, SiteConfig


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "Health", {"status": serializers.CharField(), "db": serializers.BooleanField()}
        ),
        auth=[],
    )
    def get(self, request):
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            db_ok = True
        except Exception:
            db_ok = False
        return Response({"status": "ok" if db_ok else "degraded", "db": db_ok}, status=200 if db_ok else 503)


class PublicSiteSerializer(serializers.Serializer):
    """Everything the public 'How it works' page may show. Never the SFTP host or credentials."""

    ticketing_url = serializers.CharField()
    sla_hours = serializers.IntegerField()
    reminder_hours = serializers.IntegerField()
    escalate_hours = serializers.IntegerField()
    approval_global_enabled = serializers.BooleanField()
    no_approver_fallback = serializers.CharField()
    reject_comment_required = serializers.BooleanField()
    self_approval_mode = serializers.ChoiceField(choices=SelfApprovalMode.choices)
    po_mandatory_us = serializers.BooleanField()
    msds_required_other_hazard = serializers.BooleanField()
    max_parcel_lines = serializers.IntegerField()
    sync_path = serializers.CharField()
    sync_pattern = serializers.CharField()
    sync_every_minutes = serializers.IntegerField()
    sync_alert_hours = serializers.IntegerField()
    sync_archive_path = serializers.CharField()


class PublicSiteView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicSiteSerializer, auth=[])
    def get(self, request):
        site = SiteConfig.load()
        return Response(
            {
                "ticketing_url": site.ticketing_url,
                "sla_hours": site.sla_hours,
                "reminder_hours": site.reminder_hours,
                "escalate_hours": site.escalate_hours,
                "approval_global_enabled": site.approval_global_enabled,
                "no_approver_fallback": site.no_approver_fallback,
                "reject_comment_required": site.reject_comment_required,
                "self_approval_mode": site.self_approval_mode,
                "po_mandatory_us": site.po_mandatory_us,
                "msds_required_other_hazard": site.msds_required_other_hazard,
                "max_parcel_lines": site.max_parcel_lines,
                "sync_path": site.sync_path,
                "sync_pattern": site.sync_pattern,
                "sync_every_minutes": site.sync_every_minutes,
                "sync_alert_hours": site.sync_alert_hours,
                "sync_archive_path": site.sync_archive_path,
            }
        )
