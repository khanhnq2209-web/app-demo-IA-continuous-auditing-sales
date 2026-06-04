"""Test rule engine độc lập (không cần Streamlit).

Chạy:  python -m pytest tests/ -v   (hoặc)  python tests/test_rules.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import data_loader, rules, store  # noqa: E402
from src.config_manager import default_rules_config  # noqa: E402
from src.schema import ALL_RULE_IDS  # noqa: E402


@pytest.fixture(scope="module")
def data():
    if not (ROOT / "data" / "order.csv").exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_seed_data.py")],
                       check=True)
    return data_loader.load_all()


# --- mỗi rule phải bắt được ít nhất 1 vi phạm trên dữ liệu mẫu --------------
@pytest.mark.parametrize("rid", ALL_RULE_IDS)
def test_each_rule_fires(data, rid):
    cfg = default_rules_config()[rid]["thresholds"]
    found = rules.RULE_FUNCS[rid](data, cfg)
    assert len(found) >= 1, f"{rid} không bắt được vi phạm nào trên dữ liệu mẫu"


def test_run_all_rules_shape(data):
    exc = rules.run_all_rules(data)
    assert not exc.empty
    # đủ cột chuẩn
    for col in ("ma_exception", "rule_id", "severity", "ly_do", "status"):
        assert col in exc.columns
    # có đủ 10 rule xuất hiện
    assert set(exc["rule_id"].unique()) == set(ALL_RULE_IDS)
    # mã exception duy nhất
    assert exc["ma_exception"].is_unique


def test_disabled_rule_excluded(data):
    cfg = default_rules_config()
    cfg["R9"]["enabled"] = False
    exc = rules.run_all_rules(data, cfg)
    assert "R9" not in set(exc["rule_id"].unique())


def test_threshold_sensitivity_r9(data):
    """Hạ ngưỡng cọc xuống 0 → không còn vi phạm R9."""
    base = len(rules.r9(data, {"min_deposit_pct": 0.15}))
    none = len(rules.r9(data, {"min_deposit_pct": 0.0}))
    assert base >= 1 and none == 0


def test_threshold_sensitivity_r2(data):
    """Nâng ngưỡng dân dụng lên 99% → không còn vi phạm R2."""
    assert len(rules.r2(data, {"pct_threshold": 0.99, "size_band_pct": 0.99,
                               "size_band_value": 500_000_000})) == 0


def test_r3_has_customer_and_order_level(data):
    th = default_rules_config()["R3"]["thresholds"]
    found = rules.r3(data, th)
    types = {e["doi_tuong_type"] for e in found}
    assert "Khách hàng" in types   # tỷ lệ sử dụng tín dụng theo khách hàng
    assert "Đơn hàng" in types     # trả chậm theo đơn


def test_severity_mapping(data):
    exc = rules.run_all_rules(data)
    # R1 đỏ, R6 vàng, R8 xanh
    assert exc.loc[exc.rule_id == "R1", "severity"].eq("do").all()
    assert exc.loc[exc.rule_id == "R6", "severity"].eq("vang").all()
    assert exc.loc[exc.rule_id == "R8", "severity"].eq("xanh").all()


def test_summary_by_severity(data):
    exc = rules.run_all_rules(data)
    summ = rules.summary_by_severity(exc)
    assert set(summ.keys()) == {"do", "vang", "xanh"}
    assert sum(summ.values()) == len(exc)


def test_enrich_extracts_ma_kh(data):
    """Lọc theo KH phải khớp cả khi kh_da dạng 'KH04/DA04' (bug Round 2)."""
    from src import charts
    exc = rules.run_all_rules(data)
    en = charts.enrich_exceptions(exc, data)
    assert "ma_kh" in en.columns
    # các dòng R1 có kh_da 'KHxx/DAxx' phải tách được ra 'KHxx'
    r1 = en[en["rule_id"] == "R1"]
    assert r1["ma_kh"].str.fullmatch(r"KH\d+").all()


def test_bg_fulfillment_chart_builds(data):
    """Mục tiêu 2: chart 'đã lấy vs còn lại theo báo giá' dựng được (2 trace)."""
    from src import charts
    fig = charts.bg_fulfillment_bar(data)
    assert len(fig.data) == 2


def test_r3_customer_util_uses_du_no(data):
    """R3 cấp khách hàng dùng dư nợ/hạn mức (thang gọn, không cộng dồn lịch sử)."""
    cn = data["cong_no"]
    util = (cn["du_no"] / cn["han_muc"]).max()
    assert util < 2.0, "Tỷ lệ sử dụng tín dụng không được vỡ thang (bug 521x)"


def test_exception_key_stable():
    k1 = store.exception_key("R1", "BG0001", "lý do A")
    k2 = store.exception_key("R1", "BG0001", "lý do A")
    k3 = store.exception_key("R1", "BG0001", "lý do B")
    assert k1 == k2 and k1 != k3


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
