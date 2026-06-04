"""Quản lý cấu hình rule (ngưỡng, on/off) và alert routing, lưu JSON + ghi audit."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from . import audit
from .schema import RULE_REGISTRY

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
RULES_CFG_FILE = CONFIG_DIR / "rules_config.json"
ROUTING_FILE = CONFIG_DIR / "alert_routing.json"

# Routing mặc định theo requirement §5/§7
DEFAULT_ROUTING = [
    {"rule_ids": ["R1", "R3", "R4", "R5", "R9"], "vai_tro": "TGĐ + Trưởng KTNB",
     "kenh": ["Email", "Telegram"], "tan_suat": "realtime"},
    {"rule_ids": ["R2", "R10"], "vai_tro": "Trưởng KD",
     "kenh": ["Email"], "tan_suat": "realtime"},
    {"rule_ids": ["R6", "R7", "R8"], "vai_tro": "KTNB",
     "kenh": ["Telegram"], "tan_suat": "digest_ngay"},
    {"rule_ids": list(RULE_REGISTRY.keys()), "vai_tro": "KTNB",
     "kenh": ["Email"], "tan_suat": "digest_ngay"},
]


def _ensure_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def default_rules_config() -> dict:
    """Bản config rule mặc định, suy ra từ RULE_REGISTRY."""
    cfg = {}
    for rid, meta in RULE_REGISTRY.items():
        cfg[rid] = {
            "enabled": meta["enabled"],
            "severity": meta["severity"],
            "thresholds": copy.deepcopy(meta["thresholds"]),
        }
    return cfg


def load_rules_config() -> dict:
    """Đọc config rule (tạo file mặc định nếu chưa có); merge field mới từ registry."""
    _ensure_dir()
    if not RULES_CFG_FILE.exists():
        cfg = default_rules_config()
        _write_json(RULES_CFG_FILE, cfg)
        return cfg
    cfg = _read_json(RULES_CFG_FILE)
    # Merge: bổ sung rule/threshold mới nếu registry thay đổi
    base = default_rules_config()
    for rid, base_meta in base.items():
        if rid not in cfg:
            cfg[rid] = base_meta
            continue
        for key in ("enabled", "severity"):
            cfg[rid].setdefault(key, base_meta[key])
        cfg[rid].setdefault("thresholds", {})
        for tk, tv in base_meta["thresholds"].items():
            cfg[rid]["thresholds"].setdefault(tk, tv)
    return cfg


def save_rules_config(cfg: dict, user: str = "admin") -> None:
    _ensure_dir()
    _write_json(RULES_CFG_FILE, cfg)
    audit.log_event("config_save", "rules_config", user=user,
                    note="Lưu toàn bộ config rule")


def update_threshold(rule_id: str, key: str, new_value, user: str = "admin") -> dict:
    """Cập nhật 1 ngưỡng + ghi audit before→after. Trả về config mới."""
    cfg = load_rules_config()
    old = cfg.get(rule_id, {}).get("thresholds", {}).get(key)
    cfg.setdefault(rule_id, {}).setdefault("thresholds", {})[key] = new_value
    _write_json(RULES_CFG_FILE, cfg)
    audit.log_event("threshold_change", f"{rule_id}.{key}", user=user,
                    before=old, after=new_value)
    return cfg


def toggle_rule(rule_id: str, enabled: bool, user: str = "admin") -> dict:
    cfg = load_rules_config()
    old = cfg.get(rule_id, {}).get("enabled")
    cfg.setdefault(rule_id, {})["enabled"] = enabled
    _write_json(RULES_CFG_FILE, cfg)
    audit.log_event("toggle_rule", rule_id, user=user, before=old, after=enabled)
    return cfg


def load_routing() -> list:
    _ensure_dir()
    if not ROUTING_FILE.exists():
        _write_json(ROUTING_FILE, DEFAULT_ROUTING)
        return copy.deepcopy(DEFAULT_ROUTING)
    return _read_json(ROUTING_FILE)


def save_routing(routing: list, user: str = "admin") -> None:
    _ensure_dir()
    _write_json(ROUTING_FILE, routing)
    audit.log_event("routing_save", "alert_routing", user=user)


# --- helpers ---------------------------------------------------------------
def _read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
