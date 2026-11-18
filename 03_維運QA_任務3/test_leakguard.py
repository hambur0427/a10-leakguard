"""QA 測試：ON、OFF、切換，以及「被隱藏的功能在伺服器端也被擋」。"""
import json
import shutil
import os

import pytest

import flags
from app import create_app

HERE = os.path.dirname(__file__)


@pytest.fixture
def app(tmp_path, monkeypatch):
    # 每個測試使用獨立的 flags.json 副本，不污染原檔
    path = tmp_path / "flags.json"
    shutil.copy(os.path.join(HERE, "flags.json"), path)
    monkeypatch.setattr(flags, "FLAGS_PATH", str(path))
    return create_app(secret_key="test-only-key")


def login(app, name):
    c = app.test_client()
    c.get(f"/login/{name}")
    with c.session_transaction() as s:
        token = s["csrf"]
    return c, token


def post_revoke(c, token, alert_id):
    return c.post(f"/alerts/{alert_id}/revoke", data={"csrf": token})


def set_flag(path, name, **kw):
    flags.set_flag(name, path=path, **kw)


# ---------- 開關本身 ----------
def test_kill_switch_off_for_everyone():
    f = {"x": {"enabled": False, "rollout": 100}}
    assert not any(flags.is_on("x", f"u{i}", f) for i in range(200))


def test_rollout_100_on_and_0_off():
    assert all(flags.is_on("x", f"u{i}", {"x": {"enabled": True, "rollout": 100}}) for i in range(200))
    assert not any(flags.is_on("x", f"u{i}", {"x": {"enabled": True, "rollout": 0}}) for i in range(200))


def test_same_user_always_same_group():
    f = {"x": {"enabled": True, "rollout": 30}}
    assert len({flags.is_on("x", "user-42", f) for _ in range(50)}) == 1


def test_rollout_roughly_matches_percentage():
    f = {"x": {"enabled": True, "rollout": 20}}
    on = sum(flags.is_on("x", f"user-{i}", f) for i in range(5000))
    assert 0.15 < on / 5000 < 0.25


def test_unknown_flag_is_off():
    assert not flags.is_on("nope", "u1", {})


# ---------- one_click_revoke：ON ----------
def test_on_owner_can_revoke_own_repo(app):
    c, t = login(app, "bob")
    r = post_revoke(c, t, 1)
    assert r.status_code == 200
    assert len(r.get_json()["checklist"]) >= 4
    assert app.alerts[0]["status"] == "revoked"


def test_on_owner_cannot_revoke_other_repo(app):
    c, t = login(app, "bob")
    assert post_revoke(c, t, 4).status_code == 403  # alert 4 屬於 team/web
    assert app.alerts[3]["status"] == "open"


def test_on_member_cannot_revoke(app):
    c, t = login(app, "dana")
    assert post_revoke(c, t, 1).status_code == 403


def test_on_admin_can_revoke(app):
    c, t = login(app, "alice")
    assert post_revoke(c, t, 4).status_code == 200


def test_anonymous_gets_401(app):
    assert app.test_client().post("/alerts/1/revoke").status_code == 401


def test_missing_csrf_rejected(app):
    c, _ = login(app, "bob")
    assert c.post("/alerts/1/revoke").status_code == 403
    assert app.alerts[0]["status"] == "open"


def test_double_revoke_conflict(app):
    c, t = login(app, "bob")
    assert post_revoke(c, t, 1).status_code == 200
    assert post_revoke(c, t, 1).status_code == 409


def test_ui_shows_button_when_on_for_owner(app):
    c, _ = login(app, "bob")
    html = c.get("/alerts").get_data(as_text=True)
    assert "一鍵撤銷並產生輪替清單" in html


def test_ui_hides_button_for_member(app):
    c, _ = login(app, "dana")
    assert "一鍵撤銷並產生輪替清單" not in c.get("/alerts").get_data(as_text=True)


# ---------- one_click_revoke：OFF（伺服器端也要擋） ----------
def test_off_hides_button_and_blocks_api(app):
    set_flag(flags.FLAGS_PATH, "one_click_revoke", enabled=False)
    c, t = login(app, "bob")
    assert "一鍵撤銷並產生輪替清單" not in c.get("/alerts").get_data(as_text=True)
    r = post_revoke(c, t, 1)  # 直接打 API，不經過按鈕
    assert r.status_code == 404
    assert app.alerts[0]["status"] == "open"


def test_off_blocks_even_admin(app):
    set_flag(flags.FLAGS_PATH, "one_click_revoke", enabled=False)
    c, t = login(app, "alice")
    assert post_revoke(c, t, 1).status_code == 404


# ---------- 切換 ----------
def test_switch_off_then_on_via_admin_api(app):
    admin, at = login(app, "alice")
    owner, ot = login(app, "bob")

    r = admin.post("/admin/flags/one_click_revoke", json={"enabled": False}, headers={"X-CSRF-Token": at})
    assert r.status_code == 200
    assert post_revoke(owner, ot, 1).status_code == 404

    admin.post("/admin/flags/one_click_revoke", json={"enabled": True}, headers={"X-CSRF-Token": at})
    assert post_revoke(owner, ot, 1).status_code == 200


def test_non_admin_cannot_flip_flag(app):
    c, t = login(app, "bob")
    r = c.post("/admin/flags/one_click_revoke", json={"enabled": False}, headers={"X-CSRF-Token": t})
    assert r.status_code == 403
    with open(flags.FLAGS_PATH, encoding="utf-8") as fh:
        assert json.load(fh)["one_click_revoke"]["enabled"] is True


# ---------- severity_notify ----------
def channels(app, name):
    c, _ = login(app, name)
    return {n["id"]: n["channel"] for n in c.get("/api/notifications").get_json()}


def test_notify_on_grades_by_severity(app):
    ch = channels(app, "bob")
    assert "即時" in ch[1]   # high
    assert "每日" in ch[2]   # medium
    assert "每週" in ch[3]   # low


def test_notify_off_everything_instant(app):
    set_flag(flags.FLAGS_PATH, "severity_notify", enabled=False)
    assert all("即時" in v for v in channels(app, "bob").values())


def test_member_sees_no_other_repo_alerts(app):
    assert channels(app, "dana") == {}


# ---------- 稽核紀錄 ----------
def test_audit_records_success_and_denial(app):
    c, t = login(app, "bob")
    post_revoke(c, t, 1)
    post_revoke(c, t, 4)
    admin, _ = login(app, "alice")
    actions = [(e["action"], e.get("reason")) for e in admin.get("/admin/audit").get_json()]
    assert ("revoke", None) in actions
    assert ("revoke_denied", "not_owner") in actions


def test_audit_admin_only(app):
    c, _ = login(app, "bob")
    assert c.get("/admin/audit").status_code == 403


# Task 2: direct API requests must enforce access, independently of the UI.
@pytest.mark.parametrize("path", ["/alerts", "/api/notifications", "/admin/audit"])
def test_anonymous_read_endpoints_rejected(app, path):
    assert app.test_client().get(path).status_code == 401


@pytest.mark.parametrize("token", [None, "incorrect-csrf-token"])
@pytest.mark.parametrize("path", ["/alerts/1/revoke", "/admin/flags/one_click_revoke"])
def test_invalid_csrf_never_mutates_state(app, token, path):
    c, _ = login(app, "alice")
    before = flags.load_flags()
    headers = {} if token is None else {"X-CSRF-Token": token}
    r = c.post(path, json={"enabled": False}, headers=headers)
    assert r.status_code == 403
    assert flags.load_flags() == before
    assert app.alerts[0]["status"] == "open"


def test_owner_notification_api_filters_other_repositories(app):
    assert set(channels(app, "bob")) == {1, 2, 3}
    assert set(channels(app, "chen")) == {4, 5}


def test_off_denial_is_audited_without_mutation(app):
    set_flag(flags.FLAGS_PATH, "one_click_revoke", enabled=False)
    c, t = login(app, "bob")
    assert post_revoke(c, t, 1).status_code == 404
    assert app.alerts[0]["status"] == "open"
    assert app.audit[-1]["action"] == "revoke_denied"
    assert app.audit[-1]["reason"] == "flag_off"


def test_environment_key_and_cookie_configuration(monkeypatch):
    # An ephemeral test value, not a production credential.
    import secrets
    key = secrets.token_hex(32)
    monkeypatch.setenv("SECRET_KEY", key)
    monkeypatch.setenv("COOKIE_SECURE", "1")
    instance = create_app()
    assert instance.secret_key == key
    assert instance.config["SESSION_COOKIE_HTTPONLY"] is True
    assert instance.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert instance.config["SESSION_COOKIE_SECURE"] is True
