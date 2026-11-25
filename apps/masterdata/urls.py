from django.urls import path

from . import api

urlpatterns = [
    path("masterdata/cost-centres", api.CostCentreListView.as_view(), name="masterdata-cost-centres"),
    path("masterdata/branches", api.BranchListView.as_view(), name="masterdata-branches"),
    path("masterdata/reason-codes", api.ReasonCodeListView.as_view(), name="masterdata-reason-codes"),
    path("masterdata/countries", api.CountryListView.as_view(), name="masterdata-countries"),
    path("masterdata/pvari", api.PVARIListView.as_view(), name="masterdata-pvari"),
    path("masterdata/currencies", api.CurrencyListView.as_view(), name="masterdata-currencies"),
    path("masterdata/packaging", api.PackagingListView.as_view(), name="masterdata-packaging"),
    path("masterdata/carriers", api.CarrierListView.as_view(), name="masterdata-carriers"),
    path("masterdata/ships-from", api.ShipsFromListView.as_view(), name="masterdata-ships-from"),
]
