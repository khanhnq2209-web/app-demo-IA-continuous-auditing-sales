"""Web App Giám sát Liên tục Quy trình Bán hàng Dự án (Dây & Cáp điện).

Streamlit + Plotly · 3 tab: Config · Monitoring · Exceptions.
Chạy:  streamlit run app.py
"""
from __future__ import annotations

import glob
import io
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from src import (alerts, audit, charts, config_manager, data_loader, rules,
                 store)
from src.schema import (ALL_RULE_IDS, EXCEPTION_STATUSES, ENTITIES, RAG_LABEL,
                        RULES_BY_SEVERITY, RULES_BY_THRESHOLD, RULE_REGISTRY,
                        SEV_RANK)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# Nhãn mức rủi ro (hiển thị) ↔ mã nội bộ
SEV_CODE2LABEL = {"do": "🔴 Cao", "vang": "🟡 Trung bình", "xanh": "🟢 Thông tin"}
SEV_LABEL2CODE = {v: k for k, v in SEV_CODE2LABEL.items()}

# Nhãn tiếng Việt cho các khóa ngưỡng kỹ thuật
THRESHOLD_LABELS = {
    "require_official_doc": "Bắt buộc chứng từ chính thức",
    "pct_threshold": "Ngưỡng tỷ lệ dây dân dụng",
    "size_band_pct": "Ngưỡng tỷ lệ (đơn lớn)",
    "size_band_value": "Ngưỡng giá trị đơn lớn (VND)",
    "warn_pct": "Ngưỡng cảnh báo tín dụng",
    "violate_pct": "Ngưỡng vi phạm tín dụng",
    "max_tra_cham_days": "Số ngày trả chậm tối đa",
    "min_days_before_expiry": "Số ngày đặt đơn tối thiểu trước hạn",
    "min_da_value": "Giá trị dự án tối thiểu (VND)",
    "run_rate_multiplier": "Bội số tốc độ bán (cảnh báo)",
    "run_rate_horizon_days": "Số ngày tính tốc độ bán",
    "zscore_threshold": "Ngưỡng điểm z",
    "window_days": "Cửa sổ quan sát (ngày)",
    "price_jump_pct": "Ngưỡng tăng giá đồng",
    "min_deposit_pct": "Tỷ lệ cọc tối thiểu",
}

st.set_page_config(page_title="Giám sát Bán hàng Dự án",
                   page_icon="🛰️", layout="wide")


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------
def data_token() -> str:
    files = glob.glob(str(DATA_DIR / "*.csv"))
    return str(round(max((os.path.getmtime(f) for f in files), default=0.0), 2))


@st.cache_data(show_spinner=False)
def get_data(token: str) -> dict:
    return data_loader.load_all()


@st.cache_data(show_spinner=False)
def get_exceptions(cfg_json: str, token: str) -> pd.DataFrame:
    data = data_loader.load_all()
    return rules.run_all_rules(data, json.loads(cfg_json))


def refresh_all():
    st.cache_data.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_vnd(x) -> str:
    try:
        return f"{float(x):,.0f} ₫"
    except (TypeError, ValueError):
        return "-"


def fmt_vnd_short(x) -> str:
    """Rút gọn cho số lớn: 208,5 tỷ ₫ / 12 triệu ₫."""
    try:
        x = float(x or 0)
    except (TypeError, ValueError):
        return "-"
    if abs(x) >= 1e9:
        return f"{x / 1e9:,.1f} tỷ ₫"
    if abs(x) >= 1e6:
        return f"{x / 1e6:,.0f} triệu ₫"
    return f"{x:,.0f} ₫"


# Màu chữ + nền nhẹ cho card theo mức RAG (chữ đủ đậm để đọc trên nền sáng)
RAG_CARD = {"do": ("#E03C32", "#FDECEA"), "vang": ("#B8860B", "#FFF8E1"),
            "xanh": ("#5A8F3C", "#EEF6E9")}


def metric_card(label: str, value, sub: str = "", color: str = "#1A1A1A",
                border: str = "#E2E5E9", bg: str = "#F8FAFC") -> str:
    """HTML một ô số có viền + nền nhẹ (card) để nhìn rõ."""
    sub_html = (f'<div style="font-size:12.5px;margin-top:4px;">{sub}</div>'
                if sub else "")
    return (
        f'<div style="border:1px solid {border};background:{bg};border-radius:12px;'
        f'padding:12px 14px;text-align:center;min-height:108px;'
        f'box-shadow:0 1px 2px rgba(0,0,0,.05);">'
        f'<div style="font-size:14px;color:{color};font-weight:600;">{label}</div>'
        f'<div style="font-size:38px;font-weight:700;line-height:1.2;color:{color};">'
        f'{value}</div>{sub_html}</div>')


def _compact(fig, h: int = 300):
    """Giảm chiều cao chart khi đặt trong expander."""
    try:
        fig.update_layout(height=h)
    except Exception:
        pass
    return fig


def _violator_drill(ev, exc_f: pd.DataFrame, data: dict, col: str, label: str):
    """Bấm vào bar Top vi phạm → liệt kê các vi phạm của đối tượng đó."""
    try:
        pts = ev["selection"]["points"]
    except (KeyError, TypeError):
        pts = []
    if not pts:
        st.caption(f"↑ Bấm vào một cột để xem danh sách vi phạm của {label}.")
        return
    val = pts[0].get("y")
    if not val:
        return
    en = charts.enrich_exceptions(exc_f, data)
    sub = en[en[col] == val]
    st.markdown(f"**Vi phạm của {label} `{val}`:** {len(sub)} exception")
    if not sub.empty:
        show = sub[["ma_exception", "rule_id", "doi_tuong_type", "doi_tuong_id",
                    "kh_da", "gia_tri", "severity", "status"]].copy()
        show["gia_tri"] = show["gia_tri"].map(fmt_vnd)
        show["severity"] = show["severity"].map(RAG_LABEL)
        st.dataframe(show.rename(columns={
            "ma_exception": "Mã", "rule_id": "Rule", "doi_tuong_type": "Loại",
            "doi_tuong_id": "Đối tượng", "kh_da": "KH/DA", "gia_tri": "Giá trị",
            "severity": "Mức", "status": "Trạng thái"}),
            hide_index=True, width="stretch")


def pillar_card(icon: str, title: str, subtitle: str, stat: str, bg: str) -> str:
    """Banner một 'trụ' (Continuous Monitoring / Reporting) — nền màu, chữ trắng."""
    return (
        f'<div style="background:{bg};border-radius:14px;padding:16px 20px;'
        f'color:#fff;box-shadow:0 1px 3px rgba(0,0,0,.15);min-height:120px;">'
        f'<div style="font-size:16px;font-weight:700;letter-spacing:.3px;">{icon} {title}</div>'
        f'<div style="font-size:13.5px;opacity:.93;margin-top:5px;">{subtitle}</div>'
        f'<div style="font-size:20px;font-weight:700;margin-top:9px;">{stat}</div></div>')


def sev_badge(sev: str) -> str:
    return RAG_LABEL.get(sev, sev)


def page_header(title: str):
    """Tiêu đề trang + disclaimer dữ liệu demo."""
    st.header(title)
    st.caption("⚠️ **Dữ liệu mẫu — chỉ phục vụ minh hoạ (data demo only).** "
               "Không phải dữ liệu sản xuất thật.")


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
def sidebar_nav() -> tuple[str, str]:
    """Sidebar trái = điều hướng 3 tab + vai trò + nút chạy rule."""
    st.sidebar.title("🛰️ Giám sát Bán hàng Dự án")
    st.sidebar.caption("Continuous monitoring · Dây & Cáp điện")

    role = st.sidebar.selectbox(
        "Vai trò đăng nhập",
        ["Kiểm toán nội bộ / Quản trị", "Ban điều hành / Tổng Giám đốc"], index=0)

    if st.sidebar.button("🔄 Run rules / Refresh", width="stretch",
                         type="primary"):
        refresh_all()
        st.rerun()

    st.sidebar.divider()
    pages = (["📖 Hướng dẫn", "⚙️ Config", "📊 Monitoring", "🚨 Exceptions"]
             if role.startswith("Kiểm toán") else ["📖 Hướng dẫn", "📊 Monitoring"])
    default_page = "📊 Monitoring"        # mặc định mở Monitoring trước
    if st.session_state.get("nav_page") not in pages:
        st.session_state["nav_page"] = (default_page if default_page in pages
                                        else pages[0])
    page = st.sidebar.radio("Điều hướng", pages, key="nav_page")

    st.sidebar.divider()
    st.sidebar.caption(f"Cập nhật dữ liệu: {data_token_human()}")
    return role, page


def render_filters(data: dict, exc: pd.DataFrame) -> dict:
    """Bộ lọc đặt TRONG trang (không ở sidebar) — dùng chung Monitoring & Exceptions."""
    flt = {}
    active = any(st.session_state.get(k) for k in
                 ("flt_nv", "flt_kv", "flt_kh", "flt_rule", "flt_sev"))
    with st.expander("🔎 Bộ lọc" + (" · đang lọc" if active else ""),
                     expanded=active):
        c1, c2, c3 = st.columns(3)
        with c1:
            if not exc.empty:
                dmin = pd.to_datetime(exc["ngay_phat_hien"]).min().date()
                dmax = pd.to_datetime(exc["ngay_phat_hien"]).max().date()
                flt["date_range"] = st.date_input(
                    "Khoảng ngày", (dmin, dmax), min_value=dmin, max_value=dmax,
                    key="flt_date")
        with c2:
            nv = sorted(data["order"]["nhan_vien_kd"].dropna().unique())
            flt["nhan_vien"] = st.multiselect("Nhân viên Kinh doanh", nv, key="flt_nv")
        with c3:
            kv = sorted(data["order"]["khu_vuc"].dropna().unique())
            flt["khu_vuc"] = st.multiselect("Khu vực", kv, key="flt_kv")
        c4, c5, c6 = st.columns(3)
        with c4:
            kh = sorted(data["order"]["ma_kh"].dropna().unique())
            flt["kh"] = st.multiselect("Khách hàng / Đại lý", kh, key="flt_kh")
        with c5:
            flt["rule"] = st.multiselect("Rule", ALL_RULE_IDS, key="flt_rule")
        with c6:
            flt["sev"] = st.multiselect(
                "Mức độ rủi ro", ["do", "vang", "xanh"],
                format_func=lambda s: RAG_LABEL[s], key="flt_sev")
    return flt


def data_token_human() -> str:
    files = glob.glob(str(DATA_DIR / "*.csv"))
    if not files:
        return "—"
    return pd.Timestamp(max(os.path.getmtime(f) for f in files),
                        unit="s").strftime("%Y-%m-%d %H:%M")


def apply_filters(exc: pd.DataFrame, data: dict, flt: dict) -> pd.DataFrame:
    if exc.empty:
        return exc
    en = charts.enrich_exceptions(exc, data)
    if flt.get("date_range") and len(flt["date_range"]) == 2:
        d0, d1 = flt["date_range"]
        d = pd.to_datetime(en["ngay_phat_hien"]).dt.date
        en = en[(d >= d0) & (d <= d1)]
    if flt.get("nhan_vien"):
        en = en[en["nhan_vien_kd"].isin(flt["nhan_vien"])]
    if flt.get("khu_vuc"):
        en = en[en["khu_vuc"].isin(flt["khu_vuc"])]
    if flt.get("kh"):
        en = en[en["ma_kh"].isin(flt["kh"]) | en["doi_tuong_id"].isin(flt["kh"])]
    if flt.get("rule"):
        en = en[en["rule_id"].isin(flt["rule"])]
    if flt.get("sev"):
        en = en[en["severity"].isin(flt["sev"])]
    return en


# ===========================================================================
# TAB 1 — CONFIG
# ===========================================================================
def tab_config(data: dict, exc_all: pd.DataFrame):
    page_header("⚙️ Config — Cấu hình rule, cảnh báo, nguồn dữ liệu")
    cfg = config_manager.load_rules_config()

    # --- Rule Registry -----------------------------------------------------
    st.subheader("1) Rule Registry")
    st.caption("Sắp xếp ưu tiên: 🔴 Cao → 🟡 Trung bình → 🟢 Thông tin.")
    reg_rows = []
    for rid in RULES_BY_SEVERITY:
        meta = RULE_REGISTRY[rid]
        c = cfg.get(rid, {})
        reg_rows.append({
            "Rule": rid, "Tên": meta["name"], "Nhóm": meta["group"],
            "Bật": c.get("enabled", True),
            "Mức": SEV_CODE2LABEL.get(c.get("severity", meta["severity"])),
        })
    reg_df = pd.DataFrame(reg_rows)
    edited = st.data_editor(
        reg_df, hide_index=True, width="stretch", key="reg_editor",
        column_config={
            "Bật": st.column_config.CheckboxColumn(),
            "Mức": st.column_config.SelectboxColumn(options=list(SEV_LABEL2CODE)),
            "Rule": st.column_config.TextColumn(disabled=True),
            "Tên": st.column_config.TextColumn(disabled=True),
            "Nhóm": st.column_config.TextColumn(disabled=True),
        })
    if st.button("💾 Lưu Rule Registry"):
        for _, r in edited.iterrows():
            rid = r["Rule"]
            new_sev = SEV_LABEL2CODE.get(r["Mức"], cfg[rid].get("severity"))
            if cfg[rid].get("enabled") != bool(r["Bật"]):
                config_manager.toggle_rule(rid, bool(r["Bật"]))
            if cfg[rid].get("severity") != new_sev:
                cfg[rid]["severity"] = new_sev
        config_manager.save_rules_config(cfg)
        refresh_all()
        st.success("Đã lưu Rule Registry (ghi audit).")

    # --- Ngưỡng (thresholds) ----------------------------------------------
    st.subheader("2) Ngưỡng rule (editable)")
    st.caption("Rule có ngưỡng số (chỉnh được) hiển thị trước.")
    rid = st.selectbox("Chọn rule để chỉnh ngưỡng", RULES_BY_THRESHOLD,
                       format_func=lambda r: f"{r} — {RULE_REGISTRY[r]['name']}")
    th = cfg[rid].get("thresholds", {})
    st.caption(RULE_REGISTRY[rid]["desc"])
    if not th:
        st.info("Rule này không có ngưỡng số (dựa trên khung chiết khấu / "
                "ma trận phân quyền / chuỗi bước kiểm soát).")
    else:
        new_vals = {}
        cols = st.columns(min(3, len(th)))
        for i, (k, v) in enumerate(th.items()):
            lbl = THRESHOLD_LABELS.get(k, k)
            with cols[i % len(cols)]:
                if isinstance(v, bool):
                    new_vals[k] = st.checkbox(lbl, value=v, key=f"th_{rid}_{k}")
                elif isinstance(v, (int, float)):
                    step = 0.01 if (isinstance(v, float) and v < 5) else 1.0
                    new_vals[k] = st.number_input(lbl, value=float(v), step=step,
                                                  key=f"th_{rid}_{k}")
                else:
                    st.text_input(lbl, value=str(v), disabled=True,
                                  key=f"th_{rid}_{k}")
                st.caption(f"`{k}`")
        if st.button("💾 Lưu ngưỡng"):
            for k, v in new_vals.items():
                if th.get(k) != v:
                    config_manager.update_threshold(rid, k, v)
            refresh_all()
            st.success(f"Đã cập nhật ngưỡng {rid} (ghi audit before→after).")

    # --- Alert Routing -----------------------------------------------------
    st.subheader("3) Alert Routing")
    routing = config_manager.load_routing()
    rt_df = pd.DataFrame([{
        "Rule (CSV)": ",".join(r["rule_ids"]),
        "Vai trò": r["vai_tro"],
        "Kênh (CSV)": ",".join(r["kenh"]),
        "Tần suất": r["tan_suat"],
    } for r in routing])
    rt_edit = st.data_editor(rt_df, num_rows="dynamic", hide_index=True,
                             width="stretch", key="rt_editor",
                             column_config={"Tần suất": st.column_config.SelectboxColumn(
                                 options=["realtime", "digest_ngay", "digest_tuan"])})
    if st.button("💾 Lưu Routing"):
        new_routing = []
        for _, r in rt_edit.iterrows():
            new_routing.append({
                "rule_ids": [x.strip() for x in str(r["Rule (CSV)"]).split(",") if x.strip()],
                "vai_tro": r["Vai trò"],
                "kenh": [x.strip() for x in str(r["Kênh (CSV)"]).split(",") if x.strip()],
                "tan_suat": r["Tần suất"],
            })
        config_manager.save_routing(new_routing)
        st.success("Đã lưu Alert Routing.")

    # --- Alert preview & log (stub dispatcher) ----------------------------
    st.markdown("**Cảnh báo sẽ gửi (preview theo routing — chế độ stub/log)**")
    al = alerts.build_alerts(exc_all, config_manager.load_routing())
    if al.empty:
        st.caption("Không có cảnh báo cần gửi (đã lọc exception đã đóng).")
    else:
        st.dataframe(al, hide_index=True, width="stretch",
                     column_config={"gia_tri_rui_ro": st.column_config.NumberColumn(
                         "Giá trị rủi ro", format="%.0f")})
        if st.button("📨 Gửi cảnh báo (stub → ghi log)"):
            n = alerts.dispatch(al, user="admin")
            st.success(f"Đã ghi {n} cảnh báo vào alert log (chưa gửi thật).")
    with st.expander("Lịch sử alert log"):
        st.dataframe(alerts.read_alert_log(100), hide_index=True, width="stretch")

    # --- User & Role / ma trận phân quyền ---------------------------------
    st.subheader("4) User & Role — Ma trận phân quyền")
    st.dataframe(data["ma_tran_phan_quyen"], hide_index=True,
                 width="stretch")
    up_mt = st.file_uploader("Upload ma trận phân quyền (Excel/CSV)",
                             type=["xlsx", "csv"], key="up_matrix")
    if up_mt is not None:
        df = data_loader.read_upload("ma_tran_phan_quyen", up_mt)
        miss = data_loader.validate_table("ma_tran_phan_quyen", df)
        if miss:
            st.error(f"Thiếu cột: {miss}")
        else:
            df.to_csv(DATA_DIR / "ma_tran_phan_quyen.csv", index=False)
            audit.log_event("upload", "ma_tran_phan_quyen", user="admin")
            refresh_all()
            st.success("Đã cập nhật ma trận phân quyền.")

    # --- Data Source -------------------------------------------------------
    st.subheader("5) Data Source")
    c1, c2 = st.columns([2, 1])
    with c1:
        st.dataframe(data_loader.data_status(), hide_index=True,
                     width="stretch")
    with c2:
        tbl = st.selectbox("Bảng cần upload", list(ENTITIES.keys()))
        up = st.file_uploader(f"Upload {tbl} (CSV/Excel)", type=["csv", "xlsx"],
                              key="up_table")
        if up is not None:
            df = data_loader.read_upload(tbl, up)
            miss = data_loader.validate_table(tbl, df)
            if miss:
                st.error(f"Thiếu cột: {miss}")
            else:
                df.to_csv(DATA_DIR / f"{tbl}.csv", index=False)
                audit.log_event("upload", tbl, user="admin")
                refresh_all()
                st.success(f"Đã cập nhật bảng {tbl}.")
        confirm_regen = st.checkbox("Xác nhận ghi đè dữ liệu hiện tại",
                                    key="confirm_regen")
        if st.button("🎲 Tạo lại dữ liệu mẫu", disabled=not confirm_regen,
                     help="Sẽ GHI ĐÈ toàn bộ file trong thư mục data/"):
            try:
                subprocess.run([sys.executable,
                                str(ROOT / "scripts" / "generate_seed_data.py")],
                               check=True)
                audit.log_event("regenerate_seed", "data/", user="admin")
                refresh_all()
                st.success("Đã tạo lại dữ liệu mẫu (ghi đè data/).")
            except Exception as exc:
                st.error(f"Không tạo lại được dữ liệu (môi trường chỉ đọc?): {exc}")

    # --- Audit trail -------------------------------------------------------
    st.subheader("6) Audit trail (thay đổi ngưỡng / trạng thái / cảnh báo)")
    st.dataframe(audit.read_audit(200), hide_index=True, width="stretch")


def monitor_summary(data: dict, exc_f: pd.DataFrame):
    """⚡ Ticker cảnh báo mới nhất + 📋 tóm tắt nhanh (top rule/khu vực) + tuổi exception."""
    st.divider()
    st.markdown("**⚡ Cảnh báo mới nhất**")
    if exc_f is None or exc_f.empty:
        st.caption("Không có exception trong phạm vi lọc.")
        return
    latest = exc_f.sort_values("ngay_phat_hien", ascending=False).head(5)
    items = ""
    for _, r in latest.iterrows():
        c = RAG_CARD.get(r["severity"], ("#666", "#eee"))[0]
        items += (
            '<div style="padding:7px 12px;border-bottom:1px solid #eef0f2;font-size:13.5px;">'
            f'<span style="color:{c};font-weight:700;">●</span> '
            f'<b>{r["rule_id"]}</b> · {r["doi_tuong_type"]} {r["doi_tuong_id"]} · '
            f'{r["kh_da"]} · {fmt_vnd(r["gia_tri"])}'
            f'<span style="color:#9ca3af;"> · {r["ngay_phat_hien"]}</span></div>')
    st.markdown('<div style="border:1px solid #E2E5E9;border-radius:10px;'
                f'background:#fff;overflow:hidden;">{items}</div>',
                unsafe_allow_html=True)

    st.markdown("**📋 Tóm tắt nhanh (cho Ban lãnh đạo)**")
    en = charts.enrich_exceptions(exc_f, data)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Top rule nhiều exception")
        tr = (exc_f.groupby("rule_id").size().sort_values(ascending=False)
              .head(3).reset_index(name="Số EX"))
        tr["Mức"] = tr["rule_id"].map(lambda r: RAG_LABEL[RULE_REGISTRY[r]["severity"]])
        tr["Tên"] = tr["rule_id"].map(lambda r: RULE_REGISTRY[r]["name"])
        st.dataframe(tr.rename(columns={"rule_id": "Rule"})[["Rule", "Mức", "Tên", "Số EX"]],
                     hide_index=True, width="stretch")
    with c2:
        st.caption("Top khu vực rủi ro")
        tk = (en.groupby("khu_vuc").size().sort_values(ascending=False).head(3)
              .reset_index(name="Số EX").rename(columns={"khu_vuc": "Khu vực"}))
        st.dataframe(tk, hide_index=True, width="stretch")
    with c3:
        st.caption("Tuổi exception đang mở (theo ngày phát sinh)")
        today = pd.Timestamp(pd.Timestamp.now().date())
        op = exc_f[~exc_f["status"].isin(["Đã giải trình", "Đóng"])]
        if not op.empty:
            age = (today - pd.to_datetime(op["ngay_phat_hien"])).dt.days
            n7, n30 = int((age > 7).sum()), int((age > 30).sum())
        else:
            n7 = n30 = 0
        a1, a2 = st.columns(2)
        c7 = ("#E03C32", "#FDECEA") if n7 else ("#5A8F3C", "#EEF6E9")
        c30 = ("#E03C32", "#FDECEA") if n30 else ("#5A8F3C", "#EEF6E9")
        a1.markdown(metric_card("Open > 7 ngày", n7, color=c7[0], border=c7[0], bg=c7[1]),
                    unsafe_allow_html=True)
        a2.markdown(metric_card("Open > 30 ngày", n30, color=c30[0], border=c30[0], bg=c30[1]),
                    unsafe_allow_html=True)


# ===========================================================================
# TAB 2 — MONITORING
# ===========================================================================
def tab_monitoring(data: dict, exc_all: pd.DataFrame, exc_f: pd.DataFrame,
                   cfg: dict, role: str = "Kiểm toán nội bộ / Quản trị"):
    page_header("📊 Monitoring — Giám sát rủi ro cấp cao")

    # --- 2 trụ Kiểm soát tự động (theo slide đề xuất) ---------------------
    n_txn = len(data["order"]) + len(data["bao_gia"])
    n_rule_on = sum(1 for r in ALL_RULE_IDS if cfg.get(r, {}).get("enabled", True))
    valid_ids = set(data["order"]["ma_don"]) | set(data["bao_gia"]["ma_bg"])
    flagged = set(exc_all.loc[exc_all["doi_tuong_type"].isin(["Đơn hàng", "Báo giá"]),
                              "doi_tuong_id"]) if not exc_all.empty else set()
    pass_pct = (n_txn - len(flagged & valid_ids)) / n_txn if n_txn else 0
    st.caption("**Kiểm soát tự động:** giám sát liên tục toàn bộ giao dịch theo "
               "rule, phát hiện bất thường và cảnh báo để hỗ trợ ra quyết định.")
    p1, p2 = st.columns(2)
    p1.markdown(pillar_card(
        "🔍", "Continuous Monitoring", "Giám sát 100% giao dịch theo rule tự động",
        f"Đã quét {n_txn:,} giao dịch · {pass_pct:.0%} đạt · "
        f"{n_rule_on}/{len(ALL_RULE_IDS)} rule bật", "#1C6EA4"), unsafe_allow_html=True)
    p2.markdown(pillar_card(
        "✅", "Continuous Reporting", "Dashboard thời gian thực cho Ban lãnh đạo",
        f"{len(exc_all)} exception phát hiện · cập nhật {data_token_human()}",
        "#2E8B57"), unsafe_allow_html=True)
    st.write("")

    # Scorecard = TỔNG trong khoảng lọc (không kèm delta để tránh hiểu nhầm).
    summ = rules.summary_by_severity(exc_f)
    today = pd.Timestamp(pd.Timestamp.now().date())
    if not exc_f.empty:
        d = pd.to_datetime(exc_f["ngay_phat_hien"])
        cur30 = exc_f[d >= today - timedelta(days=30)]
        prev30 = exc_f[(d >= today - timedelta(days=60)) & (d < today - timedelta(days=30))]
    else:
        cur30 = prev30 = exc_f
    cur_summ = rules.summary_by_severity(cur30)
    prev_summ = rules.summary_by_severity(prev30)

    labels = {"do": "🔴 Cao", "vang": "🟡 Trung bình", "xanh": "🟢 Thông tin"}
    tong = exc_f["gia_tri"].sum() if not exc_f.empty else 0

    # --- KPI gộp 1 hàng: 3 RAG (kèm Δ30 ngày) | Tổng EX | Giá trị rủi ro ----
    def _delta_sub(sev):
        diff = cur_summ[sev] - prev_summ[sev]
        if diff > 0:
            d = f'<span style="color:#E03C32;font-weight:600;">▲ +{diff}</span>'
        elif diff < 0:
            d = f'<span style="color:#7BB662;font-weight:600;">▼ {diff}</span>'
        else:
            d = "— 0"
        return f'<span style="color:#9ca3af">Δ30 ngày:</span> {d}'

    cols = st.columns(5)
    for col, sev in zip(cols[:3], ["do", "vang", "xanh"]):
        color, bg = RAG_CARD[sev]
        col.markdown(metric_card(labels[sev], summ[sev], sub=_delta_sub(sev),
                                 color=color, border=color, bg=bg),
                     unsafe_allow_html=True)
    cols[3].markdown(metric_card("Tổng exception", f"{len(exc_f)}"),
                     unsafe_allow_html=True)
    cols[4].markdown(metric_card("Tổng giá trị rủi ro", fmt_vnd_short(tong),
                                 sub=f'<span style="color:#6b7280">{fmt_vnd(tong)}</span>'),
                     unsafe_allow_html=True)
    st.caption("Số lớn = **TỔNG** exception đang mở trong khoảng lọc · Δ30 ngày = "
               "30 ngày gần nhất so với 30 ngày liền trước (theo ngày phát sinh) · "
               "Giá trị rủi ro = tổng giá trị đối tượng các exception hiển thị.")

    # --- HEATMAP (xương sống) — ngay sau KPI -----------------------------
    hm = st.plotly_chart(charts.rag_heatmap(exc_f, data), width="stretch",
                         on_select="rerun", key="hm_sel")
    st.caption("Hàng = Rule, cột = khu vực; ô đậm = nhiều exception. "
               "**Bấm vào một ô** để drill-down · bộ lọc ở đầu trang.")
    try:
        sel_pts = hm["selection"]["points"]
    except (KeyError, TypeError):
        sel_pts = []
    if sel_pts:
        sel_rule = sel_pts[0].get("y")
        sel_kv = sel_pts[0].get("x")
        if sel_rule and sel_kv:
            en = charts.enrich_exceptions(exc_f, data)
            cnt = int(((en["rule_id"] == sel_rule) & (en["khu_vuc"] == sel_kv)).sum())
            da, db = st.columns([3, 1])
            da.markdown(f"🔎 Đang chọn **Rule {sel_rule} × Khu vực {sel_kv}** → "
                        f"**{cnt}** exception")
            if db.button("➡️ Mở ở Exceptions", width="stretch"):
                st.session_state["_drill"] = {"rule": sel_rule, "kv": sel_kv}
                st.rerun()

    # --- Tóm tắt nhanh (ticker + top) — đặt DƯỚI heatmap -----------------
    monitor_summary(data, exc_f)

    # --- Nhóm chart chi tiết — chỉ Kiểm toán nội bộ ----------------------
    is_ktnb = role.startswith("Kiểm toán")
    if not is_ktnb:
        st.caption("ℹ️ Phân tích chi tiết theo nhóm dành cho Kiểm toán nội bộ "
                   "(chọn vai trò KTNB ở sidebar để xem).")
        return

    st.divider()
    hc1, hc2 = st.columns([3, 1])
    hc1.subheader("Biểu đồ phân tích theo nhóm")
    open_all = hc2.toggle("Mở tất cả nhóm", value=False)
    st.caption("Badge = số exception thuộc nhóm · bật **Mở tất cả** để xem nhanh.")

    def _ex(rules_set):
        return int(exc_f["rule_id"].isin(rules_set).sum()) if not exc_f.empty else 0

    th4 = cfg["R4"]["thresholds"]
    th3 = cfg["R3"]["thresholds"]
    th7 = cfg["R7"]["thresholds"]

    # Nhóm 1 — Báo giá & Chiết khấu (mặc định mở)
    with st.expander(f"📋 Báo giá & Chiết khấu (R1 · R4 · R5 · R10) · "
                     f"{_ex({'R1', 'R4', 'R5', 'R10'})} exception", expanded=True):
        st.caption("ℹ️ R1 (chiết khấu vượt khung / thiếu chứng từ) & R10 (chiết khấu "
                   "cũ) không có biểu đồ riêng — xem chi tiết ở trang **Exceptions**.")
        a, b = st.columns(2)
        with a:
            st.plotly_chart(_compact(charts.bg_validity_funnel(
                data, int(th4.get("min_days_before_expiry", 7)))), width="stretch")
            st.plotly_chart(_compact(charts.bg_fulfillment_bar(data), 340),
                            width="stretch")
        with b:
            st.plotly_chart(_compact(charts.bg_validity_anomaly_bar(
                data, int(th4.get("max_validity_days", 60)))), width="stretch")

    # Nhóm 2 — Giao hàng & Tín dụng
    with st.expander(f"🚚 Giao hàng & Tín dụng (R3 · R6 · R9) · "
                     f"{_ex({'R3', 'R6', 'R9'})} exception", expanded=open_all):
        a, b = st.columns(2)
        with a:
            st.plotly_chart(_compact(charts.credit_util_bar(
                data, th3.get("warn_pct", 0.85), th3.get("violate_pct", 1.0))),
                width="stretch")
        with b:
            st.plotly_chart(_compact(charts.order_sankey(data)), width="stretch")

    # Nhóm 3 — Kênh & Thị trường
    with st.expander(f"📦 Kênh & Thị trường (R2 · R7 · R8) · "
                     f"{_ex({'R2', 'R7', 'R8'})} exception", expanded=open_all):
        a, b = st.columns(2)
        with a:
            st.plotly_chart(_compact(charts.dan_dung_hist(
                data, cfg["R2"]["thresholds"].get("pct_threshold", 0.30))),
                width="stretch")
            st.plotly_chart(_compact(charts.copper_overlay(data)), width="stretch")
        with b:
            st.plotly_chart(_compact(charts.channel_stuffing_bar(
                data, th7.get("run_rate_multiplier", 3.0),
                int(th7.get("run_rate_horizon_days", 30)))), width="stretch")

    # Nhóm 4 — Tổng hợp & Top vi phạm (bấm cột → danh sách vi phạm)
    with st.expander(f"📈 Tổng hợp & Top vi phạm · {len(exc_f)} exception",
                     expanded=open_all):
        st.plotly_chart(_compact(charts.exception_trend(exc_f)), width="stretch")
        t1, t2 = st.columns(2)
        with t1:
            ev_kd = st.plotly_chart(
                _compact(charts.top_violators(exc_f, data, "nhan_vien_kd"), 320),
                on_select="rerun", key="tv_kd", width="stretch")
            _violator_drill(ev_kd, exc_f, data, "nhan_vien_kd", "nhân viên")
        with t2:
            ev_kv = st.plotly_chart(
                _compact(charts.top_violators(exc_f, data, "khu_vuc"), 320),
                on_select="rerun", key="tv_kv", width="stretch")
            _violator_drill(ev_kv, exc_f, data, "khu_vuc", "khu vực")


# ===========================================================================
# TAB 3 — EXCEPTIONS
# ===========================================================================
def tab_exceptions(data: dict, exc_f: pd.DataFrame):
    page_header("🚨 Exceptions — Chi tiết cho Kiểm toán")

    # Hàng điều khiển: lọc trạng thái · số hiển thị · export (cùng hàng)
    c1, c2, c3, c4 = st.columns([3, 1.4, 1.1, 1.1])
    with c1:
        statuses = st.multiselect("Lọc nhanh theo trạng thái", EXCEPTION_STATUSES)
    view = exc_f.copy()
    if statuses:
        view = view[view["status"].isin(statuses)]
    if not view.empty:                       # 🔴 Cao → 🟡 → 🟢 lên trước
        view = (view.assign(_r=view["severity"].map(SEV_RANK).fillna(9))
                .sort_values(["_r", "rule_id", "doi_tuong_id"])
                .drop(columns="_r"))
    c2.metric("Số exception hiển thị", len(view))
    if not view.empty:
        c3.write("")
        c3.download_button("⬇️ CSV", view.to_csv(index=False).encode("utf-8-sig"),
                           "exceptions.csv", "text/csv", width="stretch")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            view.to_excel(xw, index=False, sheet_name="exceptions")
        c4.write("")
        c4.download_button("⬇️ Excel", buf.getvalue(), "exceptions.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

    if view.empty:
        st.info("Không có exception khớp bộ lọc.")
        return

    disp = view[["ma_exception", "rule_id", "doi_tuong_type", "doi_tuong_id",
                 "kh_da", "gia_tri", "severity", "status"]].copy()
    disp["severity"] = disp["severity"].map(RAG_LABEL)
    disp["gia_tri"] = disp["gia_tri"].map(fmt_vnd)
    disp = disp.rename(columns={
        "ma_exception": "Mã", "rule_id": "Rule", "doi_tuong_type": "Loại",
        "doi_tuong_id": "Đối tượng", "kh_da": "KH/DA", "gia_tri": "Giá trị",
        "severity": "Mức", "status": "Trạng thái"})

    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.caption("👉 Bấm chọn một dòng → **chi tiết hiển thị bên phải**.")
        event = st.dataframe(disp, hide_index=True, width="stretch", height=460,
                             on_select="rerun", selection_mode="single-row")
    with right:
        rows = event.selection.rows if event and event.selection else []
        if not rows:
            st.info("Chọn một dòng ở bảng bên trái để xem chi tiết, "
                    "timeline & xử lý.")
        else:
            _exception_detail(data, view.iloc[rows[0]])


def _exception_detail(data: dict, row: pd.Series):
    """Panel chi tiết 1 exception: dữ liệu gốc + timeline + workflow + bằng chứng."""
    st.markdown(f"**{row['ma_exception']} · {row['rule_id']}** — "
                f"{RULE_REGISTRY[row['rule_id']]['name']}")
    st.markdown(f"**Mức:** {sev_badge(row['severity'])} · **Đối tượng:** "
                f"{row['doi_tuong_type']} `{row['doi_tuong_id']}` · "
                f"**KH/DA:** {row['kh_da']} · **Giá trị:** {fmt_vnd(row['gia_tri'])}")
    st.markdown(f"**Lý do trigger:** {row['ly_do']}")
    with st.expander("Dữ liệu gốc (snapshot)", expanded=False):
        st.dataframe(_source_records(data, row), hide_index=True, width="stretch")
    st.markdown("**Timeline case**")
    _t, _oid = row["doi_tuong_type"], row["doi_tuong_id"]
    st.plotly_chart(charts.case_timeline(
        data, ma_don=_oid if _t == "Đơn hàng" else None,
        ma_bg=_oid if _t == "Báo giá" else None), width="stretch")

    st.markdown("**Workflow xử lý**")
    cur_status = row["status"]
    new_status = st.selectbox("Trạng thái", EXCEPTION_STATUSES,
                              index=EXCEPTION_STATUSES.index(cur_status)
                              if cur_status in EXCEPTION_STATUSES else 0)
    assignee = st.text_input("Gán người xử lý", value=row.get("nguoi_xu_ly", ""))
    note = st.text_area("Ghi chú KT / lý do", value=row.get("ghi_chu", ""))
    evidence = st.text_input("Link bằng chứng (Zalo / URL / hồ sơ)",
                             value=row.get("bang_chung", ""),
                             placeholder="https://… hoặc link chat Zalo")
    if row.get("bang_chung"):
        st.caption(f"📎 Bằng chứng hiện tại: {row['bang_chung']}")
    if st.button("✅ Cập nhật", type="primary"):
        store.update_status(row["key"], new_status, user="ktnb", note=note,
                            nguoi_xu_ly=assignee, evidence=evidence)
        st.success("Đã cập nhật (ghi audit + lịch sử).")
        st.rerun()
    hist = store.get_history(row["key"])
    if hist:
        with st.expander("Lịch sử trạng thái", expanded=False):
            st.dataframe(pd.DataFrame(hist), hide_index=True, width="stretch")


def _source_records(data: dict, row: pd.Series) -> pd.DataFrame:
    """Truy ngược dữ liệu gốc theo loại đối tượng để hiển thị snapshot."""
    t, oid = row["doi_tuong_type"], row["doi_tuong_id"]
    try:
        if t == "Báo giá":
            return data["bao_gia"][data["bao_gia"]["ma_bg"] == oid]
        if t == "Đơn hàng":
            return data["order"][data["order"]["ma_don"] == oid]
        if t == "Dự án":
            return data["du_an_master"][data["du_an_master"]["ma_da"] == oid]
        if t == "Khách hàng":
            return data["cong_no"][data["cong_no"]["ma_kh"] == oid]
    except Exception:
        pass
    return pd.DataFrame()


# ===========================================================================
# TAB 0 — HƯỚNG DẪN (landing)
# ===========================================================================
FLOW_STEPS = [
    ("1️⃣ Khung chiết khấu", "KD Dự án", "Ban hành & thông báo khung CK chuẩn đến đại lý", "R1 · R10", "#7BB662"),
    ("2️⃣ Thẩm định DA", "KD Dự án", "Dự án ≥ 100tr · đề xuất CK ≤ khung", "R2 · R5", "#7BB662"),
    ("3️⃣ TGĐ duyệt CK", "Tổng Giám đốc", "Duyệt qua Zalo · hiệu lực báo giá 60 ngày, không gia hạn", "R1 · R4", "#E03C32"),
    ("4️⃣ Cọc & Công nợ", "Kế toán", "Xác nhận cọc ≥ 15% · kiểm tra công nợ trước xuất hóa đơn", "R3 · R9", "#E6B400"),
    ("5️⃣ Đặt đơn & Giao", "KD Dự án", "Nhận đặt đơn ≥ 7 ngày trước hạn · vận chuyển", "R4 · R6 · R7 · R8", "#7BB662"),
    ("6️⃣ Thanh toán", "Kế toán", "Trả chậm ≤ 60 ngày nếu có bảo lãnh/ký quỹ", "R3", "#E6B400"),
]


def tab_guide(data: dict, cfg: dict):
    page_header("📖 Hướng dẫn — Demo Giám sát Bán hàng Dự án")
    st.markdown(
        "Ứng dụng **giám sát liên tục (continuous monitoring)** rủi ro trong quy "
        "trình bán hàng dự án (dây & cáp điện): tự động quét toàn bộ giao dịch theo "
        "**10 rule**, sinh **exception** và hỗ trợ điều tra — xử lý — báo cáo.")

    st.subheader("1) Hai trụ Kiểm soát tự động")
    g1, g2 = st.columns(2)
    g1.markdown(pillar_card(
        "🔍", "Continuous Monitoring", "Giám sát 100% giao dịch theo rule tự động",
        "Rule engine R1–R10 quét báo giá · đơn hàng · cọc · công nợ…", "#1C6EA4"),
        unsafe_allow_html=True)
    g2.markdown(pillar_card(
        "✅", "Continuous Reporting", "Dashboard thời gian thực cho Ban lãnh đạo",
        "Scorecard RAG · heatmap · drill-down · cảnh báo định tuyến", "#2E8B57"),
        unsafe_allow_html=True)

    st.subheader("2) Luồng quy trình chuẩn & điểm kiểm soát (trái → phải)")
    boxes = ""
    for title, pb, desc, rules_, color in FLOW_STEPS:
        boxes += (
            f'<div style="flex:1 1 150px;min-width:150px;border:1px solid #E2E5E9;'
            f'border-top:4px solid {color};border-radius:10px;padding:10px 12px;background:#fff;">'
            f'<div style="font-weight:700;font-size:13.5px;">{title}</div>'
            f'<div style="font-size:11.5px;color:#555;font-weight:600;margin-top:2px;">{pb}</div>'
            f'<div style="font-size:12px;color:#444;margin:6px 0;">{desc}</div>'
            f'<div style="font-size:11.5px;color:#E03C32;font-weight:600;">Rule: {rules_}</div></div>')
    st.markdown(f'<div style="display:flex;gap:10px;flex-wrap:wrap;">{boxes}</div>',
                unsafe_allow_html=True)
    st.caption("Ngưỡng nghiệp vụ chốt: DA ≥100tr · cọc ≥15% · báo giá 60 ngày "
               "(không gia hạn) · đặt đơn ≥7 ngày trước hạn · trả chậm ≤60 ngày "
               "khi có bảo lãnh · không phát sinh theo chiết khấu cũ.")

    st.subheader("3) Bộ 10 rule giám sát")
    reg = []
    for rid in RULES_BY_SEVERITY:
        m = RULE_REGISTRY[rid]
        reg.append({"Rule": rid, "Mức": RAG_LABEL[m["severity"]], "Nhóm": m["group"],
                    "Tên": m["name"], "Mô tả": m["desc"],
                    "Bật": "✓" if cfg.get(rid, {}).get("enabled", True) else "—"})
    st.dataframe(pd.DataFrame(reg), hide_index=True, width="stretch")

    st.subheader("4) Các trang & cách dùng")
    st.markdown(
        "- **📖 Hướng dẫn** — trang này: luồng, rule, cách dùng.\n"
        "- **📊 Monitoring** (cho Ban lãnh đạo) — 2 trụ, scorecard RAG, cảnh báo mới "
        "nhất, tóm tắt nhanh (top rule/khu vực, tuổi exception), bản đồ nhiệt "
        "(**bấm ô để drill-down**), biểu đồ theo rule.\n"
        "- **🚨 Exceptions** (cho Kiểm toán nội bộ) — danh sách exception, **chọn dòng** "
        "để xem dữ liệu gốc + **timeline case** + xử lý workflow; export CSV/Excel.\n"
        "- **⚙️ Config** — bật/tắt rule, chỉnh ngưỡng (ghi audit), định tuyến cảnh "
        "báo, ma trận phân quyền, nguồn dữ liệu.\n\n"
        "**Bộ lọc** nằm ở đầu mỗi trang (ngày · nhân viên KD · khu vực · khách hàng "
        "· rule · mức). **Vai trò** chọn ở sidebar: *Ban điều hành* chỉ thấy "
        "Monitoring; *Kiểm toán nội bộ* thấy tất cả.")

    st.subheader("5) Ma trận Rule × Điểm kiểm soát")
    rule_control = {
        "R1": "TGĐ duyệt chiết khấu · Khung chiết khấu",
        "R2": "Thẩm định DA — cơ cấu giá (dân dụng/dự án)",
        "R3": "Công nợ / Thanh toán (hạn mức, trả chậm, giao hàng)",
        "R4": "Hiệu lực báo giá · thời điểm đặt đơn",
        "R5": "Thẩm định DA — dữ liệu danh mục (master)",
        "R6": "Toàn chuỗi bước kiểm soát (đặt→cọc→công nợ→giao)",
        "R7": "Đặt đơn — tồn kho đại lý",
        "R8": "Đặt đơn — biến động giá đồng",
        "R9": "Xác nhận cọc ≥ 15%",
        "R10": "Khung chiết khấu · đặt đơn",
    }
    mt = pd.DataFrame([{
        "Rule": r, "Mức": RAG_LABEL[RULE_REGISTRY[r]["severity"]],
        "Điểm kiểm soát": rule_control.get(r, ""),
        "Tên rule": RULE_REGISTRY[r]["name"]} for r in RULES_BY_SEVERITY])
    st.dataframe(mt, hide_index=True, width="stretch")

    st.subheader("6) Quy trình xử lý exception")
    st.markdown("`Open → Đang rà soát → ` ┬ ` Đã giải trình (đóng)` / "
                "`Xác nhận vi phạm → Escalate BOM → Đóng`")
    st.info("⚠️ Toàn bộ dữ liệu trong demo là **giả lập** (1 công ty · 11 chi nhánh/"
            "đại lý), có cài sẵn vi phạm cho cả 10 rule. Cảnh báo đang ở chế độ "
            "**stub** (ghi log, chưa gửi thật).")


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    token = data_token()
    if not glob.glob(str(DATA_DIR / "*.csv")):
        st.warning("Chưa có dữ liệu. Chạy `python scripts/generate_seed_data.py` "
                   "hoặc dùng nút *Tạo lại dữ liệu mẫu* trong tab Config.")
        st.stop()

    data = get_data(token)
    cfg = config_manager.load_rules_config()
    exc_raw = get_exceptions(json.dumps(cfg, sort_keys=True), token)
    exc_all = store.apply_status(exc_raw)
    try:                                        # minh hoạ workflow lần đầu chạy
        if store.seed_demo_if_empty(exc_all):
            exc_all = store.apply_status(exc_raw)
    except Exception:                           # FS chỉ đọc trên cloud → bỏ qua
        pass

    # Drill-down từ heatmap: áp filter + chuyển trang TRƯỚC khi tạo widget
    drill = st.session_state.pop("_drill", None)
    if drill:
        st.session_state["flt_rule"] = [drill["rule"]]
        kv_opts = sorted(data["order"]["khu_vuc"].dropna().unique())
        st.session_state["flt_kv"] = [drill["kv"]] if drill["kv"] in kv_opts else []
        st.session_state["nav_page"] = "🚨 Exceptions"

    role, page = sidebar_nav()

    if page == "📖 Hướng dẫn":
        tab_guide(data, cfg)
    elif page == "⚙️ Config":
        tab_config(data, exc_all)
    elif page == "📊 Monitoring":
        flt = render_filters(data, exc_all)
        exc_f = apply_filters(exc_all, data, flt)
        tab_monitoring(data, exc_all, exc_f, cfg, role)
    elif page == "🚨 Exceptions":
        flt = render_filters(data, exc_all)
        exc_f = apply_filters(exc_all, data, flt)
        tab_exceptions(data, exc_f)


if __name__ == "__main__":
    main()
