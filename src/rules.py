"""Rule Engine — phát hiện vi phạm theo 10 rule (R1..R10).

Mỗi rule là một hàm `rN(data, th) -> list[dict]` nhận:
  - data: dict[name -> DataFrame] (đầu ra của data_loader.load_all)
  - th:   dict ngưỡng của rule (từ config_manager)
và trả về danh sách exception (chưa có mã/trạng thái).

`run_all_rules(data, rules_cfg)` chạy mọi rule đang bật, gán mã exception,
mức độ, và trả về một DataFrame chuẩn theo EXCEPTION_COLUMNS.

Module thuần Python/pandas — không phụ thuộc Streamlit để test độc lập.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from .schema import (BG_VALIDITY_DAYS, CONTROL_STEPS, EXCEPTION_COLUMNS,
                     RULE_REGISTRY)


def _today() -> pd.Timestamp:
    return pd.Timestamp(datetime.now().date())


def _exc(rule_id, doi_tuong_type, doi_tuong_id, kh_da, gia_tri, ly_do,
         ngay=None) -> dict:
    """Tạo một bản ghi exception thô."""
    meta = RULE_REGISTRY[rule_id]
    return {
        "rule_id": rule_id,
        "rule_name": meta["name"],
        "severity": meta["severity"],
        "doi_tuong_type": doi_tuong_type,
        "doi_tuong_id": doi_tuong_id,
        "kh_da": kh_da,
        "gia_tri": float(gia_tri) if pd.notna(gia_tri) else 0.0,
        "ngay_phat_hien": ngay if ngay is not None else _today(),
        "ly_do": ly_do,
    }


# ---------------------------------------------------------------------------
# R1 — Vượt phân quyền / CK & thiếu lưu vết duyệt
# ---------------------------------------------------------------------------
def r1(data, th) -> list[dict]:
    bg = data["bao_gia"]
    khung = data["khung_ck"].set_index("ma_khung")
    matrix = data["ma_tran_phan_quyen"].set_index("vai_tro")
    require_doc = th.get("require_official_doc", True)
    out = []
    for _, r in bg.iterrows():
        reasons = []
        # CK vượt khung CMB
        if r["ma_khung"] in khung.index:
            muc = khung.loc[r["ma_khung"], "muc_ck"]
            if r["pct_ck"] > muc:
                reasons.append(f"CK đề xuất {r['pct_ck']}% > khung {muc}% ({r['ma_khung']})")
        # Người duyệt vượt hạn mức
        vt = r["vai_tro_nguoi_duyet"]
        if vt in matrix.index:
            lim_ck = matrix.loc[vt, "han_muc_ck"]
            lim_val = matrix.loc[vt, "han_muc_gia_tri"]
            if r["pct_ck"] > lim_ck:
                reasons.append(f"CK {r['pct_ck']}% > hạn mức vai trò {vt} ({lim_ck}%)")
            if r["gia_tri"] > lim_val:
                reasons.append(f"Giá trị {r['gia_tri']:,.0f} > hạn mức vai trò {vt}")
        # Thiếu lưu vết duyệt (chỉ Zalo, không chứng từ)
        if require_doc and str(r.get("kenh_duyet")) == "Zalo" \
                and str(r.get("co_chung_tu")) == "N":
            reasons.append("Duyệt qua Zalo, thiếu chứng từ chính thức")
        if reasons:
            out.append(_exc("R1", "BG", r["ma_bg"], f"{r['ma_kh']}/{r['ma_da']}",
                            r["gia_tri"], " · ".join(reasons), r.get("ngay_tao")))
    return out


# ---------------------------------------------------------------------------
# R2 — Tỷ lệ dây dân dụng trong đơn dự án
# ---------------------------------------------------------------------------
def r2(data, th) -> list[dict]:
    lines = data["order_line"]
    orders = data["order"].set_index("ma_don")
    pct_th = th.get("pct_threshold", 0.30)
    band_pct = th.get("size_band_pct", 0.35)
    band_val = th.get("size_band_value", 500_000_000)
    out = []
    grp = lines.groupby("ma_don")
    for ma_don, g in grp:
        total = g["gia_tri"].sum()
        if total <= 0:
            continue
        dan_dung = g.loc[g["phan_loai"] == "dan_dung", "gia_tri"].sum()
        ratio = dan_dung / total
        threshold = band_pct if total >= band_val else pct_th
        if ratio > threshold:
            kh = orders.loc[ma_don, "ma_kh"] if ma_don in orders.index else "-"
            out.append(_exc("R2", "đơn", ma_don, kh, total,
                            f"Dây dân dụng {ratio:.0%} > ngưỡng {threshold:.0%} "
                            f"(đơn {total:,.0f})"))
    return out


# ---------------------------------------------------------------------------
# R3 — Vượt hạn mức / trả chậm thiếu bảo lãnh
# ---------------------------------------------------------------------------
def r3(data, th) -> list[dict]:
    orders = data["order"]
    cn = data["cong_no"]
    warn = th.get("warn_pct", 0.85)
    violate = th.get("violate_pct", 1.00)
    max_tc = th.get("max_tra_cham_days", 60)
    out = []
    # (1) Tỷ lệ sử dụng tín dụng theo KH: (dư nợ + đơn mới)/hạn mức — 1 exception/KH
    new_by_kh = orders.groupby("ma_kh")["gia_tri"].sum()
    for _, c in cn.iterrows():
        kh, du_no, han_muc = c["ma_kh"], c["du_no"], c["han_muc"]
        if han_muc <= 0:
            continue
        util = (du_no + float(new_by_kh.get(kh, 0))) / han_muc
        if util > violate:
            out.append(_exc("R3", "KH", kh, kh, du_no,
                            f"Sử dụng tín dụng {util:.0%} > 100% — vi phạm "
                            f"(dư nợ {du_no:,.0f}/hạn mức {han_muc:,.0f})"))
        elif util > warn:
            out.append(_exc("R3", "KH", kh, kh, du_no,
                            f"Sử dụng tín dụng {util:.0%} > {warn:.0%} — cảnh báo "
                            f"(dư nợ {du_no:,.0f}/hạn mức {han_muc:,.0f})"))
    # (2) Trả chậm vi phạm điều kiện — 1 exception/đơn
    cn_idx = cn.set_index("ma_kh")
    for _, o in orders.iterrows():
        if str(o.get("hinh_thuc_tt")) != "tra_cham":
            continue
        kh = o["ma_kh"]
        co_bl = str(cn_idx.loc[kh, "co_bao_lanh"]) if kh in cn_idx.index else "N"
        reasons = []
        if o.get("so_ngay_tra_cham", 0) > max_tc:
            reasons.append(f"Trả chậm {o['so_ngay_tra_cham']}d > {max_tc}d")
        if co_bl == "N":
            reasons.append("Trả chậm nhưng thiếu bảo lãnh/ký quỹ")
        if reasons:
            out.append(_exc("R3", "đơn", o["ma_don"], kh, o["gia_tri"],
                            " · ".join(reasons), o.get("ngay_dat")))
    return out


# ---------------------------------------------------------------------------
# R4 — Hiệu lực & thời điểm đặt đơn
# ---------------------------------------------------------------------------
def r4(data, th) -> list[dict]:
    orders = data["order"]
    bg = data["bao_gia"].set_index("ma_bg")
    lead = th.get("min_days_before_expiry", 7)
    out = []
    for _, o in orders.iterrows():
        if o["ma_bg"] not in bg.index:
            continue
        het = bg.loc[o["ma_bg"], "ngay_het_hieu_luc"]
        gia_han = str(bg.loc[o["ma_bg"], "gia_han"])
        ngay_dat = o["ngay_dat"]
        reasons = []
        if pd.notna(het) and pd.notna(ngay_dat):
            days_left = (het - ngay_dat).days
            if days_left < 0:
                reasons.append(f"BG đã hết hạn {abs(days_left)}d vẫn phát sinh đơn")
            elif days_left < lead:
                reasons.append(f"Đặt đơn chỉ còn {days_left}d trước hết hạn (<{lead}d)")
        if gia_han == "Y":
            reasons.append("BG có gia hạn hiệu lực (bị cấm)")
        if reasons:
            out.append(_exc("R4", "đơn", o["ma_don"], o["ma_kh"], o["gia_tri"],
                            " · ".join(reasons), ngay_dat))
    return out


# ---------------------------------------------------------------------------
# R5 — Dự án ma / dưới ngưỡng
# ---------------------------------------------------------------------------
def r5(data, th) -> list[dict]:
    da = data["du_an_master"].copy()
    min_val = th.get("min_da_value", 100_000_000)
    bg = data["bao_gia"]
    used_da = set(bg["ma_da"].dropna().unique())
    required = ["ten_da", "dia_chi", "chu_dau_tu", "gia_tri_da"]
    out = []
    # trùng tên / địa chỉ
    dup_names = da["ten_da"].duplicated(keep=False) & da["ten_da"].astype(str).str.len().gt(0)
    dup_addr = da["dia_chi"].duplicated(keep=False) & da["dia_chi"].astype(str).str.len().gt(0)
    for idx, r in da.iterrows():
        reasons = []
        missing = [c for c in required
                   if pd.isna(r[c]) or str(r[c]).strip() == ""]
        if missing:
            reasons.append(f"Thiếu trường bắt buộc: {', '.join(missing)}")
        if dup_names.iloc[idx]:
            reasons.append("Trùng tên dự án")
        if dup_addr.iloc[idx]:
            reasons.append("Trùng địa chỉ")
        gt = pd.to_numeric(r["gia_tri_da"], errors="coerce")
        if pd.notna(gt) and gt < min_val and r["ma_da"] in used_da:
            reasons.append(f"Giá trị DA {gt:,.0f} <{min_val:,.0f} nhưng vẫn nhận giá dự án")
        if reasons:
            out.append(_exc("R5", "DA", r["ma_da"], r["ma_da"],
                            gt if pd.notna(gt) else 0,
                            " · ".join(reasons)))
    return out


# ---------------------------------------------------------------------------
# R6 — Quy trình không trôi đúng mạch (skip / đảo bước)
# ---------------------------------------------------------------------------
def r6(data, th) -> list[dict]:
    ev = data["event_log"]
    orders = data["order"].set_index("ma_don")
    required = th.get("required_steps", CONTROL_STEPS)
    canonical = {s: i for i, s in enumerate(CONTROL_STEPS)}
    out = []
    if ev.empty:
        return out
    for ma_don, g in ev.groupby("ma_don"):
        g = g.sort_values("thu_tu")
        present = list(g["buoc"])
        reasons = []
        missing = [s for s in required if s not in present]
        if missing:
            reasons.append(f"Thiếu bước: {', '.join(missing)}")
        # đảo thứ tự so với chuẩn
        seq = [canonical[s] for s in present if s in canonical]
        if any(seq[i] > seq[i + 1] for i in range(len(seq) - 1)):
            reasons.append("Sai thứ tự bước control")
        if reasons:
            kh = orders.loc[ma_don, "ma_kh"] if ma_don in orders.index else "-"
            gt = orders.loc[ma_don, "gia_tri"] if ma_don in orders.index else 0
            out.append(_exc("R6", "đơn", ma_don, kh, gt, " · ".join(reasons)))
    return out


# ---------------------------------------------------------------------------
# R7 — Channel stuffing (tồn đại lý)
# ---------------------------------------------------------------------------
def r7(data, th) -> list[dict]:
    lines = data["order_line"]
    orders = data["order"].set_index("ma_don")
    tk = data["ton_kho_dai_ly"].set_index(["ma_dai_ly", "sku"])
    mult = th.get("run_rate_multiplier", 3.0)
    horizon = th.get("run_rate_horizon_days", 30)
    out = []
    # gộp SL theo (đơn, sku)
    grp = lines.groupby(["ma_don", "sku"])["so_luong"].sum().reset_index()
    for _, r in grp.iterrows():
        ma_don, sku, sl = r["ma_don"], r["sku"], r["so_luong"]
        if ma_don not in orders.index:
            continue
        dai_ly = orders.loc[ma_don, "ma_dai_ly"]
        if (dai_ly, sku) not in tk.index:
            continue
        run_rate = tk.loc[(dai_ly, sku), "toc_do_ban_bq"] * horizon
        if run_rate > 0 and sl > mult * run_rate:
            out.append(_exc(
                "R7", "đơn", ma_don, dai_ly, orders.loc[ma_don, "gia_tri"],
                f"SKU {sku}: đặt {sl:,.0f} > {mult:g}× run-rate {run_rate:,.0f} "
                f"({horizon}d) tại {dai_ly}"))
    return out


# ---------------------------------------------------------------------------
# R8 — Đặt hàng đón giá đồng
# ---------------------------------------------------------------------------
def r8(data, th) -> list[dict]:
    orders = data["order"].copy()
    gia = data["gia_dong"].copy()
    z_th = th.get("zscore_threshold", 2.0)
    window = th.get("window_days", 7)
    jump_pct = th.get("price_jump_pct", 0.03)
    out = []
    if orders.empty or gia.empty:
        return out
    gia = gia.sort_values("ngay").reset_index(drop=True)
    gia["ngay"] = pd.to_datetime(gia["ngay"])
    # các ngày có cú nhảy giá đồng (tăng) trong `window` ngày kế tiếp
    prices = gia.set_index("ngay")["gia_dong"]
    vals = orders["gia_tri"].astype(float)
    mu, sd = vals.mean(), vals.std(ddof=0)
    if sd == 0:
        return out
    for _, o in orders.iterrows():
        z = (o["gia_tri"] - mu) / sd
        if z < z_th:
            continue
        d = pd.to_datetime(o["ngay_dat"])
        future = prices[(prices.index > d) & (prices.index <= d + pd.Timedelta(days=window))]
        base = prices[prices.index <= d]
        if future.empty or base.empty:
            continue
        rise = future.max() / base.iloc[-1] - 1
        if rise >= jump_pct:
            out.append(_exc(
                "R8", "đơn", o["ma_don"], o["ma_kh"], o["gia_tri"],
                f"Đơn lớn bất thường (z={z:.1f}) ngay trước giá đồng +{rise:.1%} "
                f"trong {window}d", o["ngay_dat"]))
    return out


# ---------------------------------------------------------------------------
# R9 — Cọc < 15%
# ---------------------------------------------------------------------------
def r9(data, th) -> list[dict]:
    coc = data["coc"]
    orders = data["order"].set_index("ma_don")
    cn = data["cong_no"].set_index("ma_kh")
    min_pct = th.get("min_deposit_pct", 0.15)
    out = []
    for _, c in coc.iterrows():
        pct = pd.to_numeric(c["pct_tren_bg"], errors="coerce")
        if pd.isna(pct) or pct >= min_pct:
            continue
        ma_don = c.get("ma_don")
        # miễn trừ: trả chậm có bảo lãnh/ký quỹ
        if ma_don in orders.index:
            o = orders.loc[ma_don]
            kh = o["ma_kh"]
            if str(o.get("hinh_thuc_tt")) == "tra_cham" and kh in cn.index \
                    and str(cn.loc[kh, "co_bao_lanh"]) == "Y":
                continue
            kh_da = kh
            gt = o["gia_tri"]
        else:
            kh_da = c.get("ma_bg")
            gt = c.get("so_tien_coc", 0)
        out.append(_exc("R9", "đơn", ma_don or c.get("ma_bg"), kh_da, gt,
                        f"Cọc {pct:.1%} < {min_pct:.0%} tổng BG", c.get("ngay")))
    return out


# ---------------------------------------------------------------------------
# R10 — Phát sinh theo chiết khấu cũ
# ---------------------------------------------------------------------------
def r10(data, th) -> list[dict]:
    orders = data["order"]
    bg = data["bao_gia"].set_index("ma_bg")
    khung = data["khung_ck"].set_index("ma_khung")
    out = []
    for _, o in orders.iterrows():
        if o["ma_bg"] not in bg.index:
            continue
        ma_khung = bg.loc[o["ma_bg"], "ma_khung"]
        if ma_khung not in khung.index:
            continue
        het = khung.loc[ma_khung, "ngay_hieu_luc_den"]
        ngay_dat = o["ngay_dat"]
        if pd.notna(het) and pd.notna(ngay_dat) and het < ngay_dat:
            out.append(_exc(
                "R10", "đơn", o["ma_don"], o["ma_kh"], o["gia_tri"],
                f"Áp khung CK {ma_khung} đã hết hiệu lực "
                f"({pd.to_datetime(het).date()}) tại ngày đặt "
                f"{pd.to_datetime(ngay_dat).date()}", ngay_dat))
    return out


RULE_FUNCS = {
    "R1": r1, "R2": r2, "R3": r3, "R4": r4, "R5": r5,
    "R6": r6, "R7": r7, "R8": r8, "R9": r9, "R10": r10,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_all_rules(data: dict, rules_cfg: dict | None = None) -> pd.DataFrame:
    """Chạy mọi rule đang bật, trả DataFrame exception chuẩn (chưa gán status)."""
    from .config_manager import default_rules_config
    rules_cfg = rules_cfg or default_rules_config()
    records: list[dict] = []
    for rid, func in RULE_FUNCS.items():
        cfg = rules_cfg.get(rid, {})
        if not cfg.get("enabled", True):
            continue
        th = cfg.get("thresholds", {})
        try:
            found = func(data, th)
        except Exception as exc:  # rule lỗi không làm sập cả engine
            found = []
            print(f"[rules] {rid} lỗi: {exc}")
        # cho phép override severity từ config
        sev = cfg.get("severity")
        for e in found:
            if sev:
                e["severity"] = sev
        records.extend(found)

    if not records:
        return pd.DataFrame(columns=EXCEPTION_COLUMNS)

    df = pd.DataFrame(records)
    df = df.sort_values(["rule_id", "doi_tuong_id"]).reset_index(drop=True)
    df["ma_exception"] = [f"EX-{i:05d}" for i in range(1, len(df) + 1)]
    df["status"] = "Open"
    df["nguoi_xu_ly"] = ""
    df["ngay_phat_hien"] = pd.to_datetime(df["ngay_phat_hien"]).dt.date
    return df[EXCEPTION_COLUMNS]


def summary_by_severity(exc: pd.DataFrame) -> dict:
    """Đếm exception theo mức RAG."""
    base = {"do": 0, "vang": 0, "xanh": 0}
    if exc is None or exc.empty:
        return base
    counts = exc["severity"].value_counts().to_dict()
    base.update({k: int(v) for k, v in counts.items()})
    return base
