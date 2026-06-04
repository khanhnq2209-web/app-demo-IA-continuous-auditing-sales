"""Lưu trạng thái xử lý exception (workflow Tab 3) bền vững qua các lần chạy rule.

Vì mã EX-xxxxx được sinh lại mỗi lần chạy engine, ta dùng một *khóa ổn định*
(rule_id|đối tượng|lý do) để gắn trạng thái / người xử lý / ghi chú.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import audit

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
STATUS_FILE = LOG_DIR / "exception_status.json"


def exception_key(rule_id: str, doi_tuong_id, ly_do: str) -> str:
    raw = f"{rule_id}|{doi_tuong_id}|{ly_do}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _load() -> dict:
    if not STATUS_FILE.exists():
        return {}
    with STATUS_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


def _save(data: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with STATUS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def apply_status(exc: pd.DataFrame) -> pd.DataFrame:
    """Gắn cột `key` + merge status/người xử lý/ghi chú đã lưu vào DataFrame exception."""
    if exc is None or exc.empty:
        out = exc.copy() if exc is not None else pd.DataFrame()
        if "key" not in out.columns:
            out["key"] = []
        return out
    store = _load()
    exc = exc.copy()
    exc["key"] = [
        exception_key(r.rule_id, r.doi_tuong_id, r.ly_do)
        for r in exc.itertuples()
    ]
    exc["status"] = exc["key"].map(lambda k: store.get(k, {}).get("status", "Open"))
    exc["nguoi_xu_ly"] = exc["key"].map(
        lambda k: store.get(k, {}).get("nguoi_xu_ly", ""))
    exc["ghi_chu"] = exc["key"].map(lambda k: store.get(k, {}).get("note", ""))
    return exc


def update_status(key: str, status: str, user: str = "ktnb",
                  note: str = "", nguoi_xu_ly: str | None = None) -> None:
    """Cập nhật trạng thái 1 exception + ghi audit + lưu lịch sử chuyển trạng thái."""
    store = _load()
    rec = store.get(key, {"status": "Open", "nguoi_xu_ly": "", "note": "",
                          "history": []})
    old = rec.get("status")
    rec["status"] = status
    if nguoi_xu_ly is not None:
        rec["nguoi_xu_ly"] = nguoi_xu_ly
    if note:
        rec["note"] = note
    rec.setdefault("history", []).append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "user": user, "from": old, "to": status, "note": note,
    })
    store[key] = rec
    _save(store)
    audit.log_event("status_change", key, user=user, before=old, after=status,
                    note=note)


def get_history(key: str) -> list:
    return _load().get(key, {}).get("history", [])


def seed_demo_if_empty(exc: pd.DataFrame) -> bool:
    """Lần đầu chạy: gán sẵn vài exception trạng thái ≠ Open để minh hoạ workflow.

    Trả True nếu vừa seed (để caller re-apply trạng thái).
    """
    if STATUS_FILE.exists() or exc is None or exc.empty or "key" not in exc.columns:
        return False
    plan = [("R1", "Đang rà soát", "Nguyễn Văn A"),
            ("R9", "Xác nhận vi phạm", "Trần Thị B"),
            ("R3", "Đã giải trình", "Lê Văn C")]
    seeded = False
    for rid, status, who in plan:
        sub = exc[exc["rule_id"] == rid]
        if sub.empty:
            continue
        update_status(sub.iloc[0]["key"], status, user="seed",
                      note="(dữ liệu demo)", nguoi_xu_ly=who)
        seeded = True
    return seeded
