"""LeakGuard 範例：兩個功能放在開關後面，並在伺服器端檢查權限。

這是示範用的最小版本：
- 登入以 /login/<使用者> 簡化（正式版規劃改用 GitHub OAuth / OIDC）
- 資料存在記憶體（正式版規劃改用資料庫）
- SECRET_KEY 從環境變數讀取，不寫在程式碼裡
"""
import os
import secrets
from datetime import datetime, timezone

from flask import Flask, abort, jsonify, render_template_string, request, session

import flags

# ---- 示範資料 ----------------------------------------------------------
USERS = {
    "alice": {"role": "admin", "repos": []},
    "bob": {"role": "repo_owner", "repos": ["team/api"]},
    "chen": {"role": "repo_owner", "repos": ["team/web"]},
    "dana": {"role": "member", "repos": []},
}

# 嚴重度 → 通知管道（severity_notify = ON 時）
CHANNEL_BY_SEVERITY = {"high": "即時（Email＋推播）", "medium": "每日摘要", "low": "每週摘要"}
CHANNEL_WHEN_OFF = "即時（Email＋推播）"  # 開關 OFF：全部一視同仁


def seed_alerts():
    return [
        {"id": 1, "repo": "team/api", "type": "雲端管理金鑰", "severity": "high", "status": "open"},
        {"id": 2, "repo": "team/api", "type": "第三方 API token", "severity": "medium", "status": "open"},
        {"id": 3, "repo": "team/api", "type": "測試用 token", "severity": "low", "status": "open"},
        {"id": 4, "repo": "team/web", "type": "資料庫密碼", "severity": "high", "status": "open"},
        {"id": 5, "repo": "team/web", "type": "第三方 API token", "severity": "medium", "status": "open"},
    ]


def channel_for(severity, severity_notify_on):
    if not severity_notify_on:
        return CHANNEL_WHEN_OFF
    return CHANNEL_BY_SEVERITY.get(severity, CHANNEL_WHEN_OFF)


def rotation_checklist(alert):
    """撤銷後產生的輪替清單。"""
    return [
        f"1. 已在發行方撤銷：{alert['type']}（{alert['repo']}）",
        "2. 產生新的金鑰並存入 GitHub Secrets（不要放進程式碼）",
        "3. 更新使用此金鑰的部署與 CI 設定",
        "4. 從 git 歷史移除舊金鑰，或確認舊金鑰已完全失效",
        "5. 檢查撤銷前後的存取紀錄，確認未被濫用",
    ]


PAGE = """
<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<title>LeakGuard</title>
<style>
 body{font-family:sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}
 table{border-collapse:collapse;width:100%} td,th{border:1px solid #bbb;padding:.4rem .6rem}
 .on{color:#157f3b;font-weight:bold} .off{color:#b3261e;font-weight:bold}
 .high{background:#fde8e6}.medium{background:#fff4d6}.low{background:#eef3f8}
</style>
<h1>LeakGuard 洩漏金鑰通報</h1>
<p>登入：<b>{{ user }}</b>（{{ role }}）｜
 one_click_revoke：<span class="{{ 'on' if revoke_on else 'off' }}">{{ 'ON' if revoke_on else 'OFF' }}</span>｜
 severity_notify：<span class="{{ 'on' if notify_on else 'off' }}">{{ 'ON' if notify_on else 'OFF' }}</span></p>
<table>
<tr><th>#</th><th>Repo</th><th>類型</th><th>嚴重度</th><th>通知管道</th><th>狀態</th><th>操作</th></tr>
{% for a in alerts %}
<tr class="{{ a.severity if notify_on else '' }}">
 <td>{{ a.id }}</td><td>{{ a.repo }}</td><td>{{ a.type }}</td><td>{{ a.severity }}</td>
 <td>{{ channels[a.id] }}</td><td>{{ a.status }}</td>
 <td>
 {% if revoke_on and a.repo in owned and a.status == 'open' %}
  <form method="post" action="/alerts/{{ a.id }}/revoke">
   <input type="hidden" name="csrf" value="{{ csrf }}"><button>一鍵撤銷並產生輪替清單</button>
  </form>
 {% elif a.status == 'open' %}手動處理{% else %}已撤銷{% endif %}
 </td></tr>
{% endfor %}
</table>
"""


def create_app(secret_key=None):
    app = Flask(__name__)
    key = secret_key or os.environ.get("SECRET_KEY")
    if not key:
        # 沒設定就產生隨機值（重啟後 session 失效），絕不使用寫死的預設值
        key = secrets.token_hex(32)
    app.config.update(
        SECRET_KEY=key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    )
    app.alerts = seed_alerts()
    app.audit = []

    # ---- 輔助函式 -------------------------------------------------------
    def current_user():
        name = session.get("user")
        if name not in USERS:
            abort(401)
        return name, USERS[name]

    def check_csrf():
        token = request.form.get("csrf") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf"):
            abort(403)

    def log(user, action, **kw):
        app.audit.append(
            {"time": datetime.now(timezone.utc).isoformat(), "user": user, "action": action, **kw}
        )

    def visible_alerts(name, info):
        if info["role"] == "admin":
            return app.alerts
        return [a for a in app.alerts if a["repo"] in info["repos"]]

    # ---- 路由 -----------------------------------------------------------
    @app.get("/login/<name>")
    def login(name):
        if name not in USERS:
            abort(404)
        session.clear()
        session["user"] = name
        session["csrf"] = secrets.token_hex(16)
        return jsonify(ok=True, user=name, role=USERS[name]["role"])

    @app.get("/alerts")
    def alerts_page():
        name, info = current_user()
        revoke_on = flags.is_on("one_click_revoke", name)
        notify_on = flags.is_on("severity_notify", name)
        items = visible_alerts(name, info)
        owned = set(info["repos"]) | ({a["repo"] for a in app.alerts} if info["role"] == "admin" else set())
        return render_template_string(
            PAGE,
            user=name, role=info["role"], alerts=items, owned=owned,
            revoke_on=revoke_on, notify_on=notify_on, csrf=session["csrf"],
            channels={a["id"]: channel_for(a["severity"], notify_on) for a in items},
        )

    @app.get("/api/notifications")
    def notifications():
        name, info = current_user()
        notify_on = flags.is_on("severity_notify", name)
        return jsonify([
            {"id": a["id"], "severity": a["severity"], "channel": channel_for(a["severity"], notify_on)}
            for a in visible_alerts(name, info)
        ])

    @app.post("/alerts/<int:alert_id>/revoke")
    def revoke(alert_id):
        # 檢查順序：①登入 ②CSRF ③開關 ④角色 ⑤擁有者（任一失敗即在伺服器端拒絕）
        name, info = current_user()
        check_csrf()
        if not flags.is_on("one_click_revoke", name):
            log(name, "revoke_denied", reason="flag_off", alert=alert_id)
            abort(404)  # 開關 OFF：假裝這個功能不存在
        if info["role"] not in ("repo_owner", "admin"):
            log(name, "revoke_denied", reason="role", alert=alert_id)
            abort(403)
        alert = next((a for a in app.alerts if a["id"] == alert_id), None)
        if alert is None:
            abort(404)
        if info["role"] != "admin" and alert["repo"] not in info["repos"]:
            log(name, "revoke_denied", reason="not_owner", alert=alert_id)
            abort(403)
        if alert["status"] != "open":
            abort(409)
        alert["status"] = "revoked"
        log(name, "revoke", alert=alert_id, repo=alert["repo"])
        return jsonify(ok=True, alert=alert_id, checklist=rotation_checklist(alert))

    @app.post("/admin/flags/<flag>")
    def admin_flag(flag):
        name, info = current_user()
        check_csrf()
        if info["role"] != "admin":
            log(name, "flag_denied", flag=flag)
            abort(403)
        if flag not in flags.load_flags():
            abort(404)
        body = request.get_json(silent=True) or {}
        result = flags.set_flag(flag, enabled=body.get("enabled"), rollout=body.get("rollout"))
        log(name, "flag_set", flag=flag, **result)
        return jsonify(ok=True, flag=flag, **result)

    @app.get("/admin/audit")
    def audit():
        name, info = current_user()
        if info["role"] != "admin":
            abort(403)
        return jsonify(app.audit)

    return app


if __name__ == "__main__":
    create_app().run(debug=False)
