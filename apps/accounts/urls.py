from django.urls import path

from . import api

urlpatterns = [
    path("auth/request-code", api.RequestCodeView.as_view(), name="auth-request-code"),
    path("auth/verify", api.VerifyView.as_view(), name="auth-verify"),
    path("auth/logout", api.LogoutView.as_view(), name="auth-logout"),
    path("auth/csrf", api.CsrfView.as_view(), name="auth-csrf"),
    path("me", api.MeView.as_view(), name="me"),
    path("me/view", api.MeViewSwitchView.as_view(), name="me-view"),
    path("admin/permissions", api.PermissionsView.as_view(), name="admin-permissions"),
]
