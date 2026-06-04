"""Lớp visual — mọi biểu đồ dùng Plotly (theo đặc tả §6). Template plotly_white,
bảng màu RAG nhất quán khớp màu flow.

Mỗi hàm trả về một `plotly.graph_objects.Figure` để app gọi
`st.plotly_chart(fig, use_container_width=True)`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .schema import CONTROL_STEPS, RAG_COLORS

TEMPLATE = "plotly_white"
SEV_COLOR = {"do": RAG_COLORS["do"], "vang": RAG_COLORS["vang"],
             "xanh": RAG_COLORS["xanh"]}
SEV_LABEL = {"do": "🔴 Cao", "vang": "🟡 Trung bình", "xanh": "🟢 Thông tin"}

STEP_LABEL = {
    "tham_dinh_da": "Thẩm định dự án", "tgd_duyet": "Tổng Giám đốc duyệt",
    "xac_nhan_coc": "Xác nhận cọc", "check_cong_no": "Kiểm tra công nợ",
    "dat_don": "Đặt đơn", "giao_hang": "Giao hàng", "thanh_toan": "Thanh toán",
}


def _empty(msg: str = "Không có dữ liệu") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False, font=dict(size=14, color="#888"))
    fig.update_layout(template=TEMPLATE, height=260,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


# ---------------------------------------------------------------------------
# Enrich: gắn nhân viên KD / khu vực vào exception (qua đơn hàng)
# ---------------------------------------------------------------------------
def enrich_exceptions(exc: pd.DataFrame, data: dict) -> pd.DataFrame:
    """Gắn `ma_kh`, `nhan_vien_kd`, `khu_vuc` cho từng exception.

    Nguồn khu vực/nhân viên KD lấy từ đơn hàng theo nhiều khóa (đơn → báo giá →
    khách hàng) để hạn chế tối đa ô '(không xác định)' cho exception cấp Báo giá/
    Dự án/Khách hàng (vốn không gắn trực tiếp với một đơn).
    """
    if exc is None or exc.empty:
        return exc
    if {"nhan_vien_kd", "khu_vuc", "ma_kh"}.issubset(exc.columns):
        return exc  # đã enrich rồi — idempotent
    o = data["order"]
    en = exc.copy()
    en["ma_kh"] = en["kh_da"].astype(str).str.extract(r"(KH\d+)")[0]
    da_owner = dict(zip(data["du_an_master"]["ma_da"].astype(str),
                        data["du_an_master"]["chu_dau_tu"].astype(str)))

    def kh_of(row):
        if isinstance(row["ma_kh"], str) and row["ma_kh"]:
            return row["ma_kh"]
        oid = str(row["doi_tuong_id"])
        if oid in da_owner and da_owner[oid].startswith("KH"):
            return da_owner[oid]
        return oid if oid.startswith("KH") else None

    en["ma_kh"] = en.apply(kh_of, axis=1)
    ord_nv = dict(zip(o["ma_don"], o["nhan_vien_kd"]))
    ord_kv = dict(zip(o["ma_don"], o["khu_vuc"]))
    bg = o.drop_duplicates("ma_bg")
    bg_nv, bg_kv = dict(zip(bg["ma_bg"], bg["nhan_vien_kd"])), dict(zip(bg["ma_bg"], bg["khu_vuc"]))
    kh = o.drop_duplicates("ma_kh")
    kh_nv, kh_kv = dict(zip(kh["ma_kh"], kh["nhan_vien_kd"])), dict(zip(kh["ma_kh"], kh["khu_vuc"]))

    def resolve(row, omap, bmap, kmap):
        oid = row["doi_tuong_id"]
        return (omap.get(oid) or bmap.get(oid)
                or (kmap.get(row["ma_kh"]) if row["ma_kh"] else None)
                or "(không xác định)")

    en["nhan_vien_kd"] = en.apply(lambda r: resolve(r, ord_nv, bg_nv, kh_nv), axis=1)
    en["khu_vuc"] = en.apply(lambda r: resolve(r, ord_kv, bg_kv, kh_kv), axis=1)
    return en


# ---------------------------------------------------------------------------
# Scorecard 🔴🟡🟢 — go.Indicator (number + delta vs 30 ngày trước)
# ---------------------------------------------------------------------------
def scorecard(summary: dict, prev: dict | None = None) -> go.Figure:
    prev = prev or {}
    fig = make_subplots(rows=1, cols=3, specs=[[{"type": "indicator"}] * 3])
    for i, sev in enumerate(["do", "vang", "xanh"], start=1):
        ind = dict(mode="number", value=summary.get(sev, 0),
                   title={"text": SEV_LABEL[sev],
                          "font": {"size": 16, "color": SEV_COLOR[sev]}},
                   number={"font": {"size": 44, "color": SEV_COLOR[sev]}})
        if sev in prev:
            ind["mode"] = "number+delta"
            ind["delta"] = {"reference": prev[sev], "increasing": {"color": RAG_COLORS["do"]},
                            "decreasing": {"color": RAG_COLORS["xanh"]}}
        fig.add_trace(go.Indicator(**ind), row=1, col=i)
    fig.update_layout(template=TEMPLATE, height=180,
                      margin=dict(t=40, b=10, l=10, r=10))
    return fig


# ---------------------------------------------------------------------------
# RAG heatmap: hàng = Rule, cột = khu vực — go.Heatmap (count, customdata drill)
# ---------------------------------------------------------------------------
def rag_heatmap(exc: pd.DataFrame, data: dict, col_dim: str = "khu_vuc") -> go.Figure:
    if exc is None or exc.empty:
        return _empty("Chưa có exception để vẽ heatmap")
    en = enrich_exceptions(exc, data)
    rules = sorted(en["rule_id"].unique(),
                   key=lambda r: int(r[1:]))
    cols = sorted(en[col_dim].unique())
    mat = (en.groupby(["rule_id", col_dim]).size()
           .unstack(fill_value=0).reindex(index=rules, columns=cols, fill_value=0))
    fig = go.Figure(go.Heatmap(
        z=mat.values, x=list(mat.columns), y=list(mat.index),
        colorscale=[[0, "#F4F7F4"], [0.5, RAG_COLORS["vang"]], [1, RAG_COLORS["do"]]],
        text=mat.values, texttemplate="%{text}", textfont={"size": 12},
        hovertemplate="Rule %{y} · %{x}<br>Số exception: %{z}<extra></extra>",
        colorbar=dict(title="Số EX")))
    fig.update_layout(template=TEMPLATE, height=420,
                      title="Bản đồ nhiệt rủi ro — Rule × Khu vực (dùng bộ lọc phía trên)",
                      xaxis_title=col_dim, yaxis_title="Rule")
    return fig


# ---------------------------------------------------------------------------
# R3 — Tỷ lệ sử dụng tín dụng (px.bar ngang, màu theo ngưỡng 85/100, add_vline)
# ---------------------------------------------------------------------------
def credit_util_bar(data: dict, warn: float = 0.85, violate: float = 1.0) -> go.Figure:
    """Tỷ lệ sử dụng tín dụng hiện tại = dư nợ / hạn mức (theo khách hàng).

    Dùng dư nợ thực tế (không cộng dồn toàn bộ lịch sử đơn) nên thang đo gọn 0–~110%.
    """
    cn = data["cong_no"].copy()
    if cn.empty:
        return _empty()
    cn["su_dung"] = cn["du_no"] / cn["han_muc"].replace(0, float("nan"))
    cn = cn.dropna(subset=["su_dung"]).sort_values("su_dung", ascending=True)

    def color(u):
        return RAG_COLORS["do"] if u > violate else (
            RAG_COLORS["vang"] if u > warn else RAG_COLORS["xanh"])

    fig = go.Figure(go.Bar(
        x=cn["su_dung"], y=cn["ma_kh"], orientation="h",
        marker_color=[color(u) for u in cn["su_dung"]],
        customdata=cn[["du_no", "han_muc"]].values,
        hovertemplate="%{y}<br>Sử dụng tín dụng: %{x:.0%}"
                      "<br>Dư nợ: %{customdata[0]:,.0f}"
                      "<br>Hạn mức: %{customdata[1]:,.0f}<extra></extra>"))
    fig.add_vline(x=warn, line_dash="dash", line_color=RAG_COLORS["vang"],
                  annotation_text=f"Cảnh báo {warn:.0%}")
    fig.add_vline(x=violate, line_dash="dash", line_color=RAG_COLORS["do"],
                  annotation_text=f"Vi phạm {violate:.0%}")
    fig.update_layout(template=TEMPLATE, height=360,
                      title="R3 — Tỷ lệ sử dụng tín dụng theo khách hàng",
                      xaxis_tickformat=".0%", xaxis_title="Dư nợ / hạn mức",
                      yaxis_title="Khách hàng")
    return fig


# ---------------------------------------------------------------------------
# R2 — Phân bố tỷ lệ dây dân dụng trong đơn (histogram + add_vline 30%)
# ---------------------------------------------------------------------------
def dan_dung_hist(data: dict, threshold: float = 0.30) -> go.Figure:
    lines = data["order_line"]
    if lines.empty:
        return _empty()
    g = lines.groupby("ma_don").apply(
        lambda d: d.loc[d["phan_loai"] == "dan_dung", "gia_tri"].sum()
        / max(d["gia_tri"].sum(), 1), include_groups=False)
    ratios = g.values
    fig = px.histogram(x=ratios, nbins=20, template=TEMPLATE,
                       color_discrete_sequence=[RAG_COLORS["xanh"]])
    fig.add_vline(x=threshold, line_dash="dash", line_color=RAG_COLORS["do"],
                  annotation_text=f"ngưỡng {threshold:.0%}")
    fig.update_layout(height=320,
                      title="R2 — Phân bố tỷ lệ dây dân dụng/đơn",
                      xaxis_tickformat=".0%", xaxis_title="Tỷ lệ dân dụng",
                      yaxis_title="Số đơn", showlegend=False)
    return fig


# ---------------------------------------------------------------------------
# R4 — Funnel hiệu lực BG (go.Funnel)
# ---------------------------------------------------------------------------
def bg_validity_funnel(data: dict, lead: int = 7) -> go.Figure:
    bg = data["bao_gia"].copy()
    orders = data["order"].copy()
    if bg.empty:
        return _empty()
    today = pd.Timestamp(pd.Timestamp.now().date())
    total = len(bg)
    con_hl = int((bg["ngay_het_hieu_luc"] >= today).sum())
    co_don = int(bg["ma_bg"].isin(orders["ma_bg"]).sum())
    # đơn đặt ≥ lead ngày trước hết hạn
    m = orders.merge(bg[["ma_bg", "ngay_het_hieu_luc"]], on="ma_bg", how="left")
    days_left = (m["ngay_het_hieu_luc"] - m["ngay_dat"]).dt.days
    dung_han = int((days_left >= lead).sum())
    fig = go.Figure(go.Funnel(
        y=["Báo giá phát hành", "Báo giá còn hiệu lực", "Báo giá có đơn",
           f"Đơn đặt ≥{lead} ngày trước hạn"],
        x=[total, con_hl, co_don, dung_han],
        marker={"color": [RAG_COLORS["xanh"], "#9cc06f", RAG_COLORS["vang"],
                          RAG_COLORS["do"]]},
        textinfo="value+percent initial"))
    fig.update_layout(template=TEMPLATE, height=320,
                      title="R4 — Funnel hiệu lực & thời điểm đặt đơn")
    return fig


# ---------------------------------------------------------------------------
# R4 (Mục tiêu 2) — Báo giá sắp hết hiệu lực: đã lấy vs còn lại theo từng BG
# ---------------------------------------------------------------------------
def bg_fulfillment_bar(data: dict, near_days: int = 45, top_n: int = 15) -> go.Figure:
    """Với mỗi báo giá sắp hết hiệu lực (trong `near_days` ngày tới): đã lấy được
    bao nhiêu hàng (tổng giá trị đơn) và còn lại bao nhiêu so với giá trị báo giá."""
    bg = data["bao_gia"].copy()
    orders = data["order"]
    if bg.empty:
        return _empty()
    today = pd.Timestamp(pd.Timestamp.now().date())
    bg["het"] = pd.to_datetime(bg["ngay_het_hieu_luc"])
    bg["days_left"] = (bg["het"] - today).dt.days
    near = bg[(bg["days_left"] >= 0) & (bg["days_left"] <= near_days)].copy()
    if near.empty:                       # fallback: các BG còn hiệu lực gần hết nhất
        near = bg[bg["days_left"] >= 0].copy()
    if near.empty:
        return _empty("Không có báo giá còn hiệu lực")
    taken = orders.groupby("ma_bg")["gia_tri"].sum()
    near["da_lay"] = near["ma_bg"].map(taken).fillna(0)
    near["con_lai"] = (near["gia_tri"] - near["da_lay"]).clip(lower=0)
    near["pct"] = near["da_lay"] / near["gia_tri"].replace(0, float("nan"))
    near = near.sort_values("days_left").head(top_n).iloc[::-1]
    near["nhan"] = near["ma_bg"] + " (còn " + near["days_left"].astype(int).astype(str) + " ngày)"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=near["nhan"], x=near["da_lay"], name="Đã lấy", orientation="h",
        marker_color=RAG_COLORS["xanh"], customdata=near["pct"],
        hovertemplate="%{y}<br>Đã lấy: %{x:,.0f} (%{customdata:.0%})<extra></extra>"))
    fig.add_trace(go.Bar(
        y=near["nhan"], x=near["con_lai"], name="Còn lại", orientation="h",
        marker_color=RAG_COLORS["vang"],
        hovertemplate="%{y}<br>Còn lại: %{x:,.0f}<extra></extra>"))
    fig.update_layout(
        template=TEMPLATE, height=400, barmode="stack",
        title=f"R4 — Báo giá sắp hết hiệu lực (≤{near_days} ngày): đã lấy vs còn lại",
        xaxis_title="Giá trị (VND)", yaxis_title="Báo giá",
        legend=dict(orientation="h", y=1.08))
    return fig


# ---------------------------------------------------------------------------
# R6 — Sankey luồng bước kiểm soát (skip/đảo bước)
# ---------------------------------------------------------------------------
def order_sankey(data: dict) -> go.Figure:
    ev = data["event_log"]
    if ev.empty:
        return _empty()
    nodes = CONTROL_STEPS
    idx = {s: i for i, s in enumerate(nodes)}
    links: dict[tuple, int] = {}
    for _, g in ev.groupby("ma_don"):
        present = list(g.sort_values("thu_tu")["buoc"])
        for a, b in zip(present, present[1:]):
            if a in idx and b in idx:
                links[(idx[a], idx[b])] = links.get((idx[a], idx[b]), 0) + 1
    if not links:
        return _empty()
    src = [k[0] for k in links]
    tgt = [k[1] for k in links]
    val = list(links.values())
    # tô đỏ các link "nhảy bước" (đích cách nguồn > 1 bậc)
    colors = ["rgba(224,60,50,0.55)" if (t - s) > 1 else "rgba(123,182,98,0.45)"
              for s, t in zip(src, tgt)]
    fig = go.Figure(go.Sankey(
        node=dict(label=[STEP_LABEL[s] for s in nodes], pad=18, thickness=16,
                  color=RAG_COLORS["xanh"]),
        link=dict(source=src, target=tgt, value=val, color=colors,
                  hovertemplate="%{source.label} → %{target.label}: %{value} đơn<extra></extra>")))
    fig.update_layout(template=TEMPLATE, height=360,
                      title="R6 — Luồng bước kiểm soát (đỏ = nhảy/bỏ bước)")
    return fig


# ---------------------------------------------------------------------------
# R8 — Overlay giá đồng × khối lượng đặt (secondary_y)
# ---------------------------------------------------------------------------
def copper_overlay(data: dict) -> go.Figure:
    gia = data["gia_dong"].copy()
    orders = data["order"].copy()
    if gia.empty:
        return _empty()
    gia["ngay"] = pd.to_datetime(gia["ngay"])
    vol = (orders.assign(ngay=pd.to_datetime(orders["ngay_dat"]))
           .groupby("ngay")["gia_tri"].sum().reset_index())
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=vol["ngay"], y=vol["gia_tri"], name="Khối lượng đặt (VND)",
                         marker_color=RAG_COLORS["vang"], opacity=0.7,
                         hovertemplate="%{x|%d/%m}<br>Khối lượng: %{y:,.0f}<extra></extra>"),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=gia["ngay"], y=gia["gia_dong"], name="Giá đồng",
                             line=dict(color=RAG_COLORS["do"], width=2),
                             hovertemplate="%{x|%d/%m}<br>Giá đồng: %{y:,.0f}<extra></extra>"),
                  secondary_y=True)
    fig.update_layout(template=TEMPLATE, height=360,
                      title="R8 — Giá đồng × Khối lượng đặt hàng",
                      legend=dict(orientation="h", y=1.1))
    fig.update_yaxes(title_text="Khối lượng đặt (VND)", secondary_y=False)
    fig.update_yaxes(title_text="Giá đồng (VND/tấn)", secondary_y=True)
    return fig


# ---------------------------------------------------------------------------
# Xu hướng exception theo thời gian (area stack theo mức độ)
# ---------------------------------------------------------------------------
def exception_trend(exc: pd.DataFrame, freq: str = "W") -> go.Figure:
    if exc is None or exc.empty:
        return _empty("Chưa có exception")
    df = exc.copy()
    df["ngay"] = pd.to_datetime(df["ngay_phat_hien"])
    df = df.dropna(subset=["ngay"])
    if df.empty:
        return _empty("Chưa có ngày hợp lệ")
    g = (df.groupby([pd.Grouper(key="ngay", freq=freq), "severity"])
         .size().reset_index(name="so_luong"))
    g["mức"] = g["severity"].map(SEV_LABEL)
    fig = px.area(g, x="ngay", y="so_luong", color="severity",
                  color_discrete_map=SEV_COLOR, template=TEMPLATE,
                  category_orders={"severity": ["do", "vang", "xanh"]})
    fig.for_each_trace(lambda t: t.update(name=SEV_LABEL.get(t.name, t.name)))
    fig.update_layout(height=320, title="Xu hướng exception theo thời gian",
                      xaxis_title="Kỳ", yaxis_title="Số exception",
                      legend_title="Mức")
    return fig


# ---------------------------------------------------------------------------
# Top vi phạm theo nhân viên KD / khu vực (px.bar sort giảm dần)
# ---------------------------------------------------------------------------
def top_violators(exc: pd.DataFrame, data: dict, by: str = "nhan_vien_kd",
                  top_n: int = 10) -> go.Figure:
    if exc is None or exc.empty:
        return _empty("Chưa có exception")
    en = enrich_exceptions(exc, data)
    g = (en.groupby(by).size().reset_index(name="so_ex")
         .sort_values("so_ex", ascending=True).tail(top_n))
    label = "Nhân viên Kinh doanh" if by == "nhan_vien_kd" else "Khu vực"
    fig = go.Figure(go.Bar(
        x=g["so_ex"], y=g[by], orientation="h",
        marker_color=RAG_COLORS["do"],
        hovertemplate="%{y}<br>%{x} exception<extra></extra>"))
    fig.update_layout(template=TEMPLATE, height=340,
                      title=f"Top vi phạm theo {label.lower()}",
                      xaxis_title="Số exception", yaxis_title=label)
    return fig


# ---------------------------------------------------------------------------
# R7 — Channel stuffing: SL đặt vs run-rate (bar nhóm)
# ---------------------------------------------------------------------------
def channel_stuffing_bar(data: dict, mult: float = 3.0, horizon: int = 30,
                         top_n: int = 12) -> go.Figure:
    lines, orders = data["order_line"], data["order"]
    tk = data["ton_kho_dai_ly"]
    if lines.empty or tk.empty:
        return _empty()
    g = lines.groupby(["ma_don", "sku"])["so_luong"].sum().reset_index()
    g = g.merge(orders[["ma_don", "ma_dai_ly"]], on="ma_don", how="left")
    g = g.merge(tk, on=["ma_dai_ly", "sku"], how="left").dropna(subset=["toc_do_ban_bq"])
    g["run_rate"] = g["toc_do_ban_bq"] * horizon
    g["ty_le"] = g["so_luong"] / g["run_rate"].replace(0, np.nan)
    g = g.dropna(subset=["ty_le"]).sort_values("ty_le", ascending=False).head(top_n)
    g["nhan"] = g["ma_dai_ly"] + " · " + g["sku"]
    g["mau"] = np.where(g["ty_le"] > mult, RAG_COLORS["do"], RAG_COLORS["xanh"])
    fig = go.Figure(go.Bar(
        x=g["nhan"], y=g["ty_le"], marker_color=g["mau"],
        hovertemplate="%{x}<br>Số lượng / tốc độ bán: %{y:.1f} lần<extra></extra>"))
    fig.add_hline(y=mult, line_dash="dash", line_color=RAG_COLORS["do"],
                  annotation_text=f"{mult:g} lần tốc độ bán")
    fig.update_layout(template=TEMPLATE, height=340,
                      title="R7 — Số lượng đặt so với tốc độ bán (đại lý · mã hàng)",
                      xaxis_title="", yaxis_title="Bội số tốc độ bán")
    return fig
