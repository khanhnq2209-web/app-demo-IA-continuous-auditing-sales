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
from src.schema import (ALL_RULE_IDS, EXCEPTION_STATUSES, ENTITIES, RAG_COLORS,
                        RAG_LABEL, RULE_REGISTRY)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

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


def sev_badge(sev: str) -> str:
    return RAG_LABEL.get(sev, sev)


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
def sidebar_nav() -> tuple[str, str]:
    """Sidebar trái = điều hướng 3 tab + vai trò + nút chạy rule."""
    st.sidebar.title("🛰️ Giám sát Bán hàng DA")
    st.sidebar.caption("Continuous monitoring · Dây & Cáp điện")

    role = st.sidebar.selectbox("Vai trò đăng nhập",
                                ["KTNB / Admin", "BOM / TGĐ"], index=0)

    if st.sidebar.button("🔄 Run rules / Refresh", width="stretch",
                         type="primary"):
        refresh_all()
        st.rerun()

    st.sidebar.divider()
    pages = (["⚙️ Config", "📊 Monitoring", "🚨 Exceptions"]
             if role == "KTNB / Admin" else ["📊 Monitoring"])
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
    with st.expander("🔎 Bộ lọc", expanded=True):
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
            flt["nhan_vien"] = st.multiselect("Nhân viên KD", nv, key="flt_nv")
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
                "Mức độ (RAG)", ["do", "vang", "xanh"],
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
        en = en[en["kh_da"].isin(flt["kh"]) | en["doi_tuong_id"].isin(flt["kh"])]
    if flt.get("rule"):
        en = en[en["rule_id"].isin(flt["rule"])]
    if flt.get("sev"):
        en = en[en["severity"].isin(flt["sev"])]
    return en


# ===========================================================================
# TAB 1 — CONFIG
# ===========================================================================
def tab_config(data: dict):
    st.header("⚙️ Config — Cấu hình rule, cảnh báo, nguồn dữ liệu")
    cfg = config_manager.load_rules_config()

    # --- Rule Registry -----------------------------------------------------
    st.subheader("1) Rule Registry")
    reg_rows = []
    for rid in ALL_RULE_IDS:
        meta = RULE_REGISTRY[rid]
        c = cfg.get(rid, {})
        reg_rows.append({
            "Rule": rid, "Tên": meta["name"], "Nhóm": meta["group"],
            "Bật": c.get("enabled", True),
            "Mức": c.get("severity", meta["severity"]),
        })
    reg_df = pd.DataFrame(reg_rows)
    edited = st.data_editor(
        reg_df, hide_index=True, width="stretch", key="reg_editor",
        column_config={
            "Bật": st.column_config.CheckboxColumn(),
            "Mức": st.column_config.SelectboxColumn(options=["do", "vang", "xanh"]),
            "Rule": st.column_config.TextColumn(disabled=True),
            "Tên": st.column_config.TextColumn(disabled=True),
            "Nhóm": st.column_config.TextColumn(disabled=True),
        })
    if st.button("💾 Lưu Rule Registry"):
        for _, r in edited.iterrows():
            rid = r["Rule"]
            if cfg[rid].get("enabled") != bool(r["Bật"]):
                config_manager.toggle_rule(rid, bool(r["Bật"]))
            if cfg[rid].get("severity") != r["Mức"]:
                cfg[rid]["severity"] = r["Mức"]
        config_manager.save_rules_config(cfg)
        refresh_all()
        st.success("Đã lưu Rule Registry (ghi audit).")

    # --- Ngưỡng (thresholds) ----------------------------------------------
    st.subheader("2) Ngưỡng rule (editable)")
    rid = st.selectbox("Chọn rule để chỉnh ngưỡng", ALL_RULE_IDS,
                       format_func=lambda r: f"{r} — {RULE_REGISTRY[r]['name']}")
    th = cfg[rid].get("thresholds", {})
    st.caption(RULE_REGISTRY[rid]["desc"])
    if not th:
        st.info("Rule này không có ngưỡng số (dựa trên khung CK / ma trận / chuỗi bước).")
    else:
        new_vals = {}
        cols = st.columns(min(3, len(th)))
        for i, (k, v) in enumerate(th.items()):
            with cols[i % len(cols)]:
                if isinstance(v, bool):
                    new_vals[k] = st.checkbox(k, value=v, key=f"th_{rid}_{k}")
                elif isinstance(v, (int, float)):
                    step = 0.01 if (isinstance(v, float) and v < 5) else 1.0
                    new_vals[k] = st.number_input(k, value=float(v), step=step,
                                                  key=f"th_{rid}_{k}")
                else:
                    st.text_input(k, value=str(v), disabled=True,
                                  key=f"th_{rid}_{k}")
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
        if st.button("🎲 Tạo lại dữ liệu mẫu"):
            subprocess.run([sys.executable,
                            str(ROOT / "scripts" / "generate_seed_data.py")],
                           check=True)
            refresh_all()
            st.success("Đã tạo lại dữ liệu mẫu.")

    # --- Audit trail -------------------------------------------------------
    st.subheader("6) Audit trail (thay đổi ngưỡng / trạng thái / cảnh báo)")
    st.dataframe(audit.read_audit(200), hide_index=True, width="stretch")


# ===========================================================================
# TAB 2 — MONITORING
# ===========================================================================
def tab_monitoring(data: dict, exc_all: pd.DataFrame, exc_f: pd.DataFrame, cfg: dict):
    st.header("📊 Monitoring — Giám sát RAG cấp cao")

    # Scorecard + tổng giá trị rủi ro + delta 30 ngày
    summ = rules.summary_by_severity(exc_f)
    today = pd.Timestamp(pd.Timestamp.now().date())
    d = pd.to_datetime(exc_f["ngay_phat_hien"]) if not exc_f.empty else pd.Series([], dtype="datetime64[ns]")
    cur = exc_f[d >= today - timedelta(days=30)] if not exc_f.empty else exc_f
    prev = exc_f[(d >= today - timedelta(days=60)) & (d < today - timedelta(days=30))] \
        if not exc_f.empty else exc_f
    prev_summ = rules.summary_by_severity(prev)
    cur_summ = rules.summary_by_severity(cur)
    # delta = 30 ngày gần đây vs 30 ngày trước
    delta_ref = {k: summ[k] - (cur_summ[k] - prev_summ[k]) for k in summ}

    c1, c2 = st.columns([3, 1])
    with c1:
        st.plotly_chart(charts.scorecard(summ, delta_ref),
                        width="stretch")
        st.caption("Số exception theo mức RAG · delta = 30 ngày gần đây so với 30 ngày trước.")
    with c2:
        tong = exc_f["gia_tri"].sum() if not exc_f.empty else 0
        st.metric("Tổng giá trị rủi ro", fmt_vnd(tong))
        st.metric("Tổng exception", len(exc_f))

    st.divider()

    # RAG heatmap
    st.plotly_chart(charts.rag_heatmap(exc_f, data), width="stretch")
    st.caption("Hàng = Rule, cột = khu vực; ô đậm = nhiều exception. Dùng bộ lọc bên trái để drill.")

    st.divider()
    st.subheader("Biểu đồ theo rule")
    g1, g2 = st.columns(2)
    with g1:
        th3 = cfg["R3"]["thresholds"]
        st.plotly_chart(charts.credit_util_bar(data, th3.get("warn_pct", 0.85),
                                               th3.get("violate_pct", 1.0)),
                        width="stretch")
        st.plotly_chart(charts.bg_validity_funnel(
            data, int(cfg["R4"]["thresholds"].get("min_days_before_expiry", 7))),
            width="stretch")
        st.plotly_chart(charts.channel_stuffing_bar(
            data, cfg["R7"]["thresholds"].get("run_rate_multiplier", 3.0),
            int(cfg["R7"]["thresholds"].get("run_rate_horizon_days", 30))),
            width="stretch")
    with g2:
        st.plotly_chart(charts.dan_dung_hist(
            data, cfg["R2"]["thresholds"].get("pct_threshold", 0.30)),
            width="stretch")
        st.plotly_chart(charts.order_sankey(data), width="stretch")
        st.plotly_chart(charts.copper_overlay(data), width="stretch")

    st.divider()
    st.plotly_chart(charts.exception_trend(exc_f), width="stretch")
    t1, t2 = st.columns(2)
    with t1:
        st.plotly_chart(charts.top_violators(exc_f, data, "nhan_vien_kd"),
                        width="stretch")
    with t2:
        st.plotly_chart(charts.top_violators(exc_f, data, "khu_vuc"),
                        width="stretch")


# ===========================================================================
# TAB 3 — EXCEPTIONS
# ===========================================================================
def tab_exceptions(data: dict, exc_f: pd.DataFrame):
    st.header("🚨 Exceptions — Chi tiết cho Kiểm toán")

    # bộ lọc nhanh trạng thái
    cstat, cinfo = st.columns([2, 2])
    with cstat:
        statuses = st.multiselect("Lọc nhanh theo trạng thái", EXCEPTION_STATUSES)
    view = exc_f.copy()
    if statuses:
        view = view[view["status"].isin(statuses)]
    with cinfo:
        st.metric("Số exception hiển thị", len(view))

    if view.empty:
        st.info("Không có exception khớp bộ lọc.")
        return

    # Bảng exception
    disp = view[["ma_exception", "rule_id", "doi_tuong_type", "doi_tuong_id",
                 "kh_da", "gia_tri", "ngay_phat_hien", "severity",
                 "status", "nguoi_xu_ly"]].copy()
    disp["severity"] = disp["severity"].map(RAG_LABEL)
    disp = disp.rename(columns={
        "ma_exception": "Mã", "rule_id": "Rule", "doi_tuong_type": "Loại",
        "doi_tuong_id": "Đối tượng", "kh_da": "KH/DA", "gia_tri": "Giá trị",
        "ngay_phat_hien": "Ngày", "severity": "Mức", "status": "Trạng thái",
        "nguoi_xu_ly": "Người xử lý"})
    event = st.dataframe(disp, hide_index=True, width="stretch",
                         on_select="rerun", selection_mode="single-row",
                         column_config={"Giá trị": st.column_config.NumberColumn(
                             format="%.0f")})

    # Export
    cex1, cex2, _ = st.columns([1, 1, 4])
    with cex1:
        st.download_button("⬇️ Export CSV", view.to_csv(index=False).encode("utf-8-sig"),
                           "exceptions.csv", "text/csv", width="stretch")
    with cex2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as xw:
            view.drop(columns=["key"], errors="ignore").to_excel(
                xw, index=False, sheet_name="exceptions")
        st.download_button("⬇️ Export Excel", buf.getvalue(),
                           "exceptions.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           width="stretch")

    # Panel chi tiết
    rows = event.selection.rows if event and event.selection else []
    if not rows:
        st.info("Chọn một dòng trong bảng để xem chi tiết & xử lý.")
        return
    row = view.iloc[rows[0]]
    st.divider()
    st.subheader(f"Chi tiết {row['ma_exception']} · {row['rule_id']} — "
                 f"{RULE_REGISTRY[row['rule_id']]['name']}")

    cdetail, cwf = st.columns([3, 2])
    with cdetail:
        st.markdown(f"**Mức:** {sev_badge(row['severity'])}  ·  "
                    f"**Đối tượng:** {row['doi_tuong_type']} `{row['doi_tuong_id']}`  ·  "
                    f"**KH/DA:** {row['kh_da']}")
        st.markdown(f"**Giá trị:** {fmt_vnd(row['gia_tri'])}  ·  "
                    f"**Ngày:** {row['ngay_phat_hien']}")
        st.markdown(f"**Lý do trigger:** {row['ly_do']}")
        st.markdown("**Dữ liệu gốc (snapshot):**")
        st.dataframe(_source_records(data, row), hide_index=True,
                     width="stretch")

    with cwf:
        st.markdown("**Workflow trạng thái**")
        cur_status = row["status"]
        new_status = st.selectbox("Trạng thái", EXCEPTION_STATUSES,
                                  index=EXCEPTION_STATUSES.index(cur_status)
                                  if cur_status in EXCEPTION_STATUSES else 0)
        assignee = st.text_input("Gán người xử lý", value=row.get("nguoi_xu_ly", ""))
        note = st.text_area("Ghi chú KT / lý do", value=row.get("ghi_chu", ""))
        if st.button("✅ Cập nhật trạng thái", type="primary"):
            store.update_status(row["key"], new_status, user="ktnb",
                                note=note, nguoi_xu_ly=assignee)
            st.success("Đã cập nhật (ghi audit + lịch sử).")
            st.rerun()
        st.markdown("**Lịch sử trạng thái**")
        hist = store.get_history(row["key"])
        if hist:
            st.dataframe(pd.DataFrame(hist), hide_index=True,
                         width="stretch")
        else:
            st.caption("Chưa có lịch sử (Open).")


def _source_records(data: dict, row: pd.Series) -> pd.DataFrame:
    """Truy ngược dữ liệu gốc theo loại đối tượng để hiển thị snapshot."""
    t, oid = row["doi_tuong_type"], row["doi_tuong_id"]
    try:
        if t == "BG":
            return data["bao_gia"][data["bao_gia"]["ma_bg"] == oid]
        if t == "đơn":
            o = data["order"][data["order"]["ma_don"] == oid]
            return o
        if t == "DA":
            return data["du_an_master"][data["du_an_master"]["ma_da"] == oid]
        if t == "KH":
            return data["cong_no"][data["cong_no"]["ma_kh"] == oid]
    except Exception:
        pass
    return pd.DataFrame()


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

    role, page = sidebar_nav()

    if page == "⚙️ Config":
        tab_config(data)
    elif page == "📊 Monitoring":
        flt = render_filters(data, exc_all)
        exc_f = apply_filters(exc_all, data, flt)
        tab_monitoring(data, exc_all, exc_f, cfg)
    elif page == "🚨 Exceptions":
        flt = render_filters(data, exc_all)
        exc_f = apply_filters(exc_all, data, flt)
        tab_exceptions(data, exc_f)


if __name__ == "__main__":
    main()
