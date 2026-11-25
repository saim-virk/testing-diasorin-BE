from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api import ApprovalHintSerializer
from apps.accounts.authentication import Session401Authentication
from apps.accounts.services.profile import approval_hint

from .enums import Currency, Destination, destination_for_scope_group
from .models import (
    Branch,
    Carrier,
    CostCentre,
    Country,
    PackagingType,
    PVARICode,
    ReasonCode,
    ShipsFromSite,
)


class CostCentreSerializer(serializers.ModelSerializer):
    approval_hint = serializers.SerializerMethodField()

    class Meta:
        model = CostCentre
        fields = ["code", "name", "approval_required", "approval_hint"]

    @extend_schema_field(ApprovalHintSerializer(allow_null=True))
    def get_approval_hint(self, obj):
        return approval_hint(self.context["request"].user, obj)


class CostCentreListView(ListAPIView):
    """Active cost centres for the signed-in user (reference list: not paginated)."""

    authentication_classes = [Session401Authentication]
    serializer_class = CostCentreSerializer
    pagination_class = None

    def get_queryset(self):
        return CostCentre.objects.filter(is_active=True)

    @extend_schema(operation_id="masterdata_cost_centres_list")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# ---------------------------------------------------------------- reference lists for the request form
_DEST_PARAM = OpenApiParameter("destination", str, enum=Destination.values, required=False)


class _Ref(ListAPIView):
    """Authenticated, active rows only, not paginated. `?destination=` narrows lists that depend on it."""

    authentication_classes = [Session401Authentication]
    pagination_class = None

    def get_queryset(self):
        qs = self.model.objects.filter(is_active=True)
        dest = self.request.query_params.get("destination")
        if dest:
            if dest not in Destination.values:
                raise ValidationError({"destination": ["Use one of: " + ", ".join(Destination.values) + "."]})
            qs = self.narrow(qs, dest)
        return qs

    def narrow(self, qs, dest):
        return qs


class BranchSerializer(serializers.ModelSerializer):
    country = serializers.SlugRelatedField(slug_field="iso2", read_only=True)

    class Meta:
        model = Branch
        fields = ["code", "name", "scope", "country", "po_required"]


class BranchListView(_Ref):
    model, serializer_class = Branch, BranchSerializer

    def narrow(self, qs, dest):
        return qs.filter(scope=dest)

    @extend_schema(operation_id="masterdata_branches_list", parameters=[_DEST_PARAM])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ReasonCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReasonCode
        fields = ["code", "description_it", "description_en", "scope_group"]


class ReasonCodeListView(_Ref):
    model, serializer_class = ReasonCode, ReasonCodeSerializer

    def narrow(self, qs, dest):
        return qs.filter(scope_group=destination_for_scope_group(dest))

    @extend_schema(operation_id="masterdata_reason_codes_list", parameters=[_DEST_PARAM])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["iso2", "name", "scope"]


class CountryListView(_Ref):
    """Italy: Italy only; USA: United States only; EU / Extra-EU: their countries (DSF-03.05)."""

    model, serializer_class = Country, CountrySerializer

    def narrow(self, qs, dest):
        return qs.filter(scope=dest)

    @extend_schema(operation_id="masterdata_countries_list", parameters=[_DEST_PARAM])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PVARISerializer(serializers.ModelSerializer):
    class Meta:
        model = PVARICode
        fields = ["code", "description_it", "description_en", "un_number", "hazard", "default_temperature"]


class PVARIListView(_Ref):
    model, serializer_class = PVARICode, PVARISerializer

    @extend_schema(operation_id="masterdata_pvari_list")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class PackagingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackagingType
        fields = ["code", "dimensions", "description"]


class PackagingListView(_Ref):
    model, serializer_class = PackagingType, PackagingSerializer

    @extend_schema(operation_id="masterdata_packaging_list")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CarrierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrier
        fields = ["id", "name"]


class CarrierListView(_Ref):
    model, serializer_class = Carrier, CarrierSerializer

    @extend_schema(operation_id="masterdata_carriers_list")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ShipsFromSerializer(serializers.ModelSerializer):
    hint = serializers.SerializerMethodField()

    class Meta:
        model = ShipsFromSite
        fields = ["code", "name", "applies_calendar", "allowed_weekdays", "hint"]

    def get_hint(self, obj) -> str | None:
        """e.g. "Saluggia ships Mon, Tue, Wed, Thu." - null when the site has no calendar."""
        from apps.shipments.services.validation import saluggia_hint

        return saluggia_hint(obj) if obj.applies_calendar else None


class ShipsFromListView(_Ref):
    """Ships-from sites with their calendar, read from the database on every call (AC-03.03.4)."""

    model, serializer_class = ShipsFromSite, ShipsFromSerializer

    @extend_schema(operation_id="masterdata_ships_from_list")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CurrencyListView(APIView):
    authentication_classes = [Session401Authentication]

    @extend_schema(
        operation_id="masterdata_currencies_list",
        responses=inline_serializer("CurrencyItem", {"code": serializers.CharField()}, many=True),
    )
    def get(self, request):
        return Response([{"code": c} for c in Currency.values])
