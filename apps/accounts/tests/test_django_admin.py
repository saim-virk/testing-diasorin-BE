import pytest

pytestmark = pytest.mark.django_db


def test_anonymous_is_sent_to_spa_sign_in(client):
    r = client.get("/django-admin/")
    assert r.status_code == 302
    r2 = client.get(r["Location"])  # admin:login
    assert r2.status_code == 302 and r2["Location"] == "/sign-in?next=/django-admin/"


def test_old_admin_path_is_not_django(client):
    assert client.get("/admin/").status_code == 404


def test_otp_signed_in_admin_gets_in_and_sees_models(api, make_user, sign_in):
    make_user("admin@diasorin.com", admin=True)
    sign_in("admin@diasorin.com")
    assert api.get("/django-admin/").status_code == 200
    # superuser: model lists are visible, not "no permission to view or edit anything"
    r = api.get("/django-admin/accounts/user/")
    assert r.status_code == 200


def test_signed_in_non_admin_is_forbidden(api, make_user, sign_in):
    make_user("m.rossi@diasorin.com")
    sign_in("m.rossi@diasorin.com")
    r = api.get("/django-admin/")
    assert r.status_code == 302
    assert api.get(r["Location"]).status_code == 403


def test_password_form_is_gone(client):
    r = client.post("/django-admin/login/", {"username": "x", "password": "y"})
    assert r.status_code == 302 and r["Location"].startswith("/sign-in")
