"""功能開關：flags.json + 依使用者 ID 雜湊分組。

- enabled=false：緊急開關（kill switch），對所有人關閉
- rollout：0–100，代表開放給多少百分比的使用者
- 同一個使用者每次都會落在同一組（雜湊結果固定）
"""
import hashlib
import json
import os

FLAGS_PATH = os.environ.get(
    "FLAGS_PATH", os.path.join(os.path.dirname(__file__), "flags.json")
)


def load_flags(path=None):
    with open(path or FLAGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def is_on(flag, user_id, flags=None):
    flags = load_flags() if flags is None else flags
    f = flags.get(flag, {})
    if not f.get("enabled", False):
        return False
    bucket = int(hashlib.sha256(f"{flag}:{user_id}".encode()).hexdigest(), 16) % 100
    return bucket < f.get("rollout", 100)


def set_flag(flag, enabled=None, rollout=None, path=None):
    """切換開關（寫回 flags.json）。"""
    if rollout is not None:
        if isinstance(rollout, bool) or not isinstance(rollout, (int, str)):
            raise ValueError("rollout must be an integer from 0 to 100")
        rollout = int(rollout)
        if not 0 <= rollout <= 100:
            raise ValueError("rollout must be an integer from 0 to 100")
    path = path or FLAGS_PATH
    flags = load_flags(path)
    f = flags.setdefault(flag, {"enabled": False, "rollout": 0})
    if enabled is not None:
        f["enabled"] = bool(enabled)
    if rollout is not None:
        f["rollout"] = rollout
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(flags, fh, ensure_ascii=False, indent=2)
    return f
