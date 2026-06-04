"""Alert dispatcher (STUB) — định tuyến exception → vai trò → kênh → tần suất.

Bản này KHÔNG gửi thật. Nó tính toán định tuyến theo cấu hình và ghi "cảnh báo"
vào logs/alert_log.jsonl để xem/preview trong UI. Khi có credential thật
(SMTP/Telegram/Zalo) chỉ cần thay hàm `_send` bên dưới.

Chống nhiễu:
  - gộp digest theo (rule, vai trò, kênh)
  - không gửi lại exception đã đóng (status ∈ {Đã giải trình, Đóng})
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
ALERT_LOG = LOG_DIR / "alert_log.jsonl"

CLOSED_STATUSES = {"Đã giải trình", "Đóng"}


def build_alerts(exc: pd.DataFrame, routing: list) -> pd.DataFrame:
    """Tính danh sách cảnh báo cần gửi (chưa gửi). Trả DataFrame.

    Mỗi dòng = 1 nhóm (rule × vai trò × kênh × tần suất) kèm số exception khớp.
    """
    rows = []
    if exc is None or exc.empty:
        return pd.DataFrame(columns=[
            "rule_ids", "vai_tro", "kenh", "tan_suat", "so_exception",
            "gia_tri_rui_ro", "doi_tuong"])
    open_exc = exc[~exc["status"].isin(CLOSED_STATUSES)] \
        if "status" in exc.columns else exc
    for rule in routing:
        rids = rule.get("rule_ids", [])
        match = open_exc[open_exc["rule_id"].isin(rids)]
        if match.empty:
            continue
        for kenh in rule.get("kenh", []):
            rows.append({
                "rule_ids": ",".join(rids),
                "vai_tro": rule.get("vai_tro", ""),
                "kenh": kenh,
                "tan_suat": rule.get("tan_suat", "digest_ngay"),
                "so_exception": int(len(match)),
                "gia_tri_rui_ro": float(match["gia_tri"].sum()),
                "doi_tuong": ", ".join(match["doi_tuong_id"].astype(str)
                                       .head(8).tolist()),
            })
    return pd.DataFrame(rows)


def _send(channel: str, recipient: str, subject: str, body: str) -> bool:
    """STUB gửi cảnh báo. Trả True (giả lập thành công).

    Thay phần này bằng SMTP / Telegram Bot API / Zalo OA API khi tích hợp thật.
    """
    return True


def dispatch(alerts: pd.DataFrame, user: str = "system") -> int:
    """'Gửi' (stub) các cảnh báo và ghi vào alert_log.jsonl. Trả số cảnh báo đã ghi."""
    if alerts is None or alerts.empty:
        return 0
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with ALERT_LOG.open("a", encoding="utf-8") as fh:
        for _, a in alerts.iterrows():
            ok = _send(a["kenh"], a["vai_tro"],
                       subject=f"[Cảnh báo] {a['rule_ids']} — {a['so_exception']} exception",
                       body=f"Đối tượng: {a['doi_tuong']}")
            rec = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "rule_ids": a["rule_ids"], "vai_tro": a["vai_tro"],
                "kenh": a["kenh"], "tan_suat": a["tan_suat"],
                "so_exception": int(a["so_exception"]),
                "gia_tri_rui_ro": float(a["gia_tri_rui_ro"]),
                "status": "sent" if ok else "failed", "by": user,
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_alert_log(limit: int | None = 200) -> pd.DataFrame:
    if not ALERT_LOG.exists():
        return pd.DataFrame(columns=[
            "timestamp", "rule_ids", "vai_tro", "kenh", "tan_suat",
            "so_exception", "gia_tri_rui_ro", "status", "by"])
    rows = []
    with ALERT_LOG.open(encoding="utf-8") as fh:
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
