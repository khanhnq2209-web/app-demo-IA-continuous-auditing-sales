"""Audit trail — log mọi thay đổi ngưỡng / trạng thái / cảnh báo (user, time, before→after).

Append-only JSONL ở logs/audit_log.jsonl. Đọc lại để hiển thị ở UI.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
AUDIT_FILE = LOG_DIR / "audit_log.jsonl"


def _ensure_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_event(action: str, target: str, user: str = "system",
              before=None, after=None, note: str = "") -> None:
    """Ghi một sự kiện audit (append-only)."""
    _ensure_dir()
    record = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user": user,
        "action": action,        # vd: "threshold_change", "status_change", "alert_sent"
        "target": target,        # vd: "R3.warn_pct", "EX-0007"
        "before": before,
        "after": after,
        "note": note,
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def read_audit(limit: int | None = None) -> pd.DataFrame:
    """Đọc audit log thành DataFrame (mới nhất trước)."""
    if not AUDIT_FILE.exists():
        return pd.DataFrame(columns=[
            "timestamp", "user", "action", "target", "before", "after", "note"])
    rows = []
    with AUDIT_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)
    if limit:
        df = df.head(limit)
    return df
