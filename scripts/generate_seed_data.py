"""Sinh dữ liệu giả lập (synthetic) cho toàn bộ 11 bảng nghiệp vụ.

Mô hình: 1 công ty dây & cáp điện với **11 chi nhánh / đại lý**. Dữ liệu có cài
sẵn vi phạm cho cả 10 rule (R1..R10) để mọi chart và exception đều có dữ liệu.

Chạy:  python scripts/generate_seed_data.py
Ghi CSV vào thư mục data/.
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REF_DATE = date(2026, 6, 5)              # "hôm nay"
SEED = 20260605

# ---------------------------------------------------------------------------
# Danh mục cố định
# ---------------------------------------------------------------------------
# 11 chi nhánh / đại lý của 1 công ty
BRANCHES = [
    ("DL01", "CN Hà Nội", "Bắc", "Nguyễn Văn A"),
    ("DL02", "CN Hải Phòng", "Bắc", "Trần Thị B"),
    ("DL03", "CN Bắc Ninh", "Bắc", "Lê Văn C"),
    ("DL04", "CN Quảng Ninh", "Bắc", "Phạm Thị D"),
    ("DL05", "CN Nghệ An", "Trung", "Hoàng Văn E"),
    ("DL06", "CN Đà Nẵng", "Trung", "Vũ Thị F"),
    ("DL07", "CN Khánh Hòa", "Trung", "Đặng Văn G"),
    ("DL08", "CN TP.HCM", "Nam", "Bùi Thị H"),
    ("DL09", "CN Bình Dương", "Nam", "Đỗ Văn I"),
    ("DL10", "CN Đồng Nai", "Nam", "Ngô Thị K"),
    ("DL11", "CN Cần Thơ", "Nam", "Phan Văn L"),
]

CUSTOMERS = [(f"KH{idx:02d}", name) for idx, name in enumerate([
    "Cty Xây dựng Hòa Bình", "Cty Coteccons", "Cty Vinaconex", "Cty Delta",
    "Cty Newtecons", "Cty Ricons", "Cty Hưng Thịnh", "Cty Nam Long",
    "Cty Đất Xanh", "Cty Phú Mỹ Hưng", "Cty An Gia", "Cty Sunshine",
], start=1)]

# SKU: (mã, phân loại, đơn giá)
SKUS = [
    ("CV-1.5", "dan_dung", 12_000),
    ("CV-2.5", "dan_dung", 19_000),
    ("CV-4.0", "dan_dung", 31_000),
    ("VCmd-2x1.5", "dan_dung", 27_000),
    ("CXV-3x240", "du_an", 1_350_000),
    ("CXV-4x185", "du_an", 1_180_000),
    ("CXV-1x300", "du_an", 540_000),
    ("ACSV-95", "du_an", 210_000),
    ("AXV-150", "du_an", 320_000),
]
DU_AN_SKUS = [s for s in SKUS if s[1] == "du_an"]
DAN_DUNG_SKUS = [s for s in SKUS if s[1] == "dan_dung"]

ROLES = [
    ("NV KD", 200_000_000, 5.0),
    ("Trưởng KD", 1_000_000_000, 8.0),
    ("Giám đốc CN", 3_000_000_000, 10.0),
    ("TGĐ", 1_000_000_000_000, 15.0),
]


def role_for_value(v: float) -> tuple[str, float]:
    """Vai trò duyệt hợp lệ theo giá trị BG (để BG bình thường không vi phạm R1)."""
    for name, lim_val, lim_ck in ROLES:
        if v <= lim_val:
            return name, lim_ck
    return ROLES[-1][0], ROLES[-1][2]


def _d(d: date) -> str:
    return d.isoformat()


def generate() -> dict[str, pd.DataFrame]:
    random.seed(SEED)
    np.random.seed(SEED)
    rng = random.Random(SEED)

    # -- du_an_master --------------------------------------------------------
    projects = []
    for i in range(1, 13):
        ma_da = f"DA{i:02d}"
        kh = CUSTOMERS[(i - 1) % len(CUSTOMERS)]
        gia_tri = rng.randint(2, 40) * 100_000_000
        projects.append({
            "ma_da": ma_da,
            "ten_da": f"Dự án {kh[1].split()[-1]} {i}",
            "dia_chi": f"{rng.randint(1, 300)} Đường {rng.choice(['Lê Lợi','Trần Hưng Đạo','Nguyễn Huệ','Hùng Vương'])}, "
                       f"{rng.choice(['Hà Nội','TP.HCM','Đà Nẵng','Hải Phòng'])}",
            "chu_dau_tu": kh[0],
            "gia_tri_da": gia_tri,
        })
    # Lưu chủ đầu tư gốc TRƯỚC khi cài lỗi R5 (để BG vẫn gắn đúng KH)
    da_owner = {p["ma_da"]: p["chu_dau_tu"] for p in projects}

    # R5 injection: dự án ma
    projects[2]["dia_chi"] = ""                       # thiếu trường bắt buộc
    projects[2]["chu_dau_tu"] = ""
    projects[5]["ten_da"] = projects[4]["ten_da"]     # trùng tên
    projects[5]["dia_chi"] = projects[4]["dia_chi"]   # trùng địa chỉ
    projects[8]["gia_tri_da"] = 60_000_000            # <100tr nhưng vẫn nhận giá DA
    df_da = pd.DataFrame(projects)

    # -- khung_ck ------------------------------------------------------------
    frameworks = [
        {"ma_khung": "CK-DD-2026", "nhom_sp": "Dây dân dụng", "muc_ck": 6.0,
         "ngay_ban_hanh": date(2026, 1, 1), "ngay_hieu_luc_tu": date(2026, 1, 1),
         "ngay_hieu_luc_den": date(2026, 12, 31)},
        {"ma_khung": "CK-DA-2026", "nhom_sp": "Cáp dự án", "muc_ck": 9.0,
         "ngay_ban_hanh": date(2026, 1, 1), "ngay_hieu_luc_tu": date(2026, 1, 1),
         "ngay_hieu_luc_den": date(2026, 12, 31)},
        {"ma_khung": "CK-DA-Q1", "nhom_sp": "Cáp dự án (Q1)", "muc_ck": 10.0,
         "ngay_ban_hanh": date(2025, 12, 15), "ngay_hieu_luc_tu": date(2026, 1, 1),
         "ngay_hieu_luc_den": date(2026, 3, 31)},     # ĐÃ HẾT HẠN (cho R10)
        {"ma_khung": "CK-PROMO-2025", "nhom_sp": "Khuyến mãi 2025", "muc_ck": 12.0,
         "ngay_ban_hanh": date(2025, 6, 1), "ngay_hieu_luc_tu": date(2025, 6, 1),
         "ngay_hieu_luc_den": date(2025, 12, 31)},    # ĐÃ HẾT HẠN (cho R10)
    ]
    df_khung = pd.DataFrame(frameworks)
    khung_by_id = {f["ma_khung"]: f for f in frameworks}

    # -- ma_tran_phan_quyen --------------------------------------------------
    df_matrix = pd.DataFrame(
        [{"vai_tro": r[0], "han_muc_gia_tri": r[1], "han_muc_ck": r[2]}
         for r in ROLES])

    # -- gia_dong (chuỗi 200 ngày, có 2 cú nhảy giá) -------------------------
    start_price_day = REF_DATE - timedelta(days=200)
    gia_rows, price = [], 240_000_000.0     # VND/tấn
    jump_days = {REF_DATE - timedelta(days=120): 0.06,
                 REF_DATE - timedelta(days=35): 0.05}
    for k in range(201):
        d = start_price_day + timedelta(days=k)
        price *= (1 + np.random.normal(0, 0.004))
        if d in jump_days:
            price *= (1 + jump_days[d])
        gia_rows.append({"ngay": _d(d), "gia_dong": round(price, 0)})
    df_gia = pd.DataFrame(gia_rows)

    # -- bao_gia -------------------------------------------------------------
    bg_rows = []
    n_bg = 52
    for i in range(1, n_bg + 1):
        ma_bg = f"BG{i:04d}"
        proj = projects[(i - 1) % len(projects)]
        ngay_tao = REF_DATE - timedelta(days=rng.randint(10, 150))
        het_hl = ngay_tao + timedelta(days=60)
        # phần lớn dùng khung đúng, đúng vai trò, có chứng từ
        khung = "CK-DA-2026"
        muc_khung = khung_by_id[khung]["muc_ck"]
        gia_tri = rng.randint(3, 25) * 100_000_000
        role, role_ck_lim = role_for_value(gia_tri)        # vai trò hợp lệ theo giá trị
        pct_ck = round(rng.uniform(3.0, min(muc_khung, role_ck_lim) - 0.1), 1)
        kenh = rng.choice(["Email", "System", "Zalo"])
        co_ct = "Y"
        gia_han = "N"
        bg_rows.append({
            "ma_bg": ma_bg, "ngay_tao": ngay_tao, "ngay_het_hieu_luc": het_hl,
            "ngay_het_hieu_luc_goc": het_hl,   # hạn gốc = ngày tạo + 60 (chưa gia hạn)
            "ma_kh": da_owner.get(proj["ma_da"], "KH01"), "ma_da": proj["ma_da"],
            "nguoi_duyet": rng.choice(["Lê Trưởng KD", "Phạm GĐ", "Hoàng TGĐ"]),
            "vai_tro_nguoi_duyet": role, "kenh_duyet": kenh, "co_chung_tu": co_ct,
            "gia_tri": gia_tri, "pct_ck": pct_ck, "ma_khung": khung,
            "gia_han": gia_han,
        })

    # R1 injections — CK vượt khung / vượt hạn mức / Zalo thiếu chứng từ
    bg_rows[3]["pct_ck"] = 13.0                       # > khung 9% và > hạn mức Trưởng KD 8%
    bg_rows[7]["vai_tro_nguoi_duyet"] = "NV KD"; bg_rows[7]["pct_ck"] = 7.5  # NV KD vượt 5%
    bg_rows[11]["kenh_duyet"] = "Zalo"; bg_rows[11]["co_chung_tu"] = "N"     # thiếu lưu vết
    bg_rows[15]["gia_tri"] = 1_500_000_000; bg_rows[15]["vai_tro_nguoi_duyet"] = "NV KD"  # vượt hạn mức giá trị
    bg_rows[20]["kenh_duyet"] = "Zalo"; bg_rows[20]["co_chung_tu"] = "N"

    # R4 injections — gia hạn hiệu lực (lưu hạn gốc + số ngày gia hạn)
    for idx, ext in [(9, 25), (18, 40)]:
        bg_rows[idx]["gia_han"] = "Y"
        goc = bg_rows[idx]["ngay_het_hieu_luc_goc"]
        bg_rows[idx]["ngay_het_hieu_luc"] = goc + timedelta(days=ext)

    # R4 injections — hiệu lực dài bất thường ngay từ đầu (>60 ngày, không gia hạn)
    for idx in (25, 27):
        tao = bg_rows[idx]["ngay_tao"]
        long_het = tao + timedelta(days=85)
        bg_rows[idx]["ngay_het_hieu_luc"] = long_het
        bg_rows[idx]["ngay_het_hieu_luc_goc"] = long_het

    # R10 injections — BG dùng khung CK đã hết hiệu lực
    bg_rows[5]["ma_khung"] = "CK-DA-Q1"
    bg_rows[13]["ma_khung"] = "CK-PROMO-2025"
    bg_rows[22]["ma_khung"] = "CK-DA-Q1"

    df_bg = pd.DataFrame(bg_rows)
    bg_by_id = {r["ma_bg"]: r for r in bg_rows}

    # -- order + order_line --------------------------------------------------
    order_rows, line_rows = [], []
    n_orders = 70
    order_values = []
    for i in range(1, n_orders + 1):
        ma_don = f"DH{i:05d}"
        bg = bg_rows[(i - 1) % len(bg_rows)]
        branch = rng.choice(BRANCHES)
        # ngày đặt: thường trong thời hạn hiệu lực BG
        het = bg["ngay_het_hieu_luc"]
        ngay_dat = het - timedelta(days=rng.randint(8, 45))
        hinh_thuc = rng.choices(["tra_truoc", "tra_cham"], weights=[0.7, 0.3])[0]
        so_ngay_tc = rng.choice([0, 30, 45, 60]) if hinh_thuc == "tra_cham" else 0

        # order_lines (chủ yếu cáp dự án + ít dây dân dụng)
        n_lines = rng.randint(1, 3)
        lines, gia_tri_don = [], 0
        for _ in range(n_lines):
            sku = rng.choice(DU_AN_SKUS)
            sl = rng.randint(200, 2000)
            val = sl * sku[2]
            lines.append({"ma_don": ma_don, "sku": sku[0], "phan_loai": sku[1],
                          "so_luong": sl, "gia_tri": val})
            gia_tri_don += val
        # thêm 1 line dân dụng nhỏ
        if rng.random() < 0.5:
            sku = rng.choice(DAN_DUNG_SKUS)
            sl = rng.randint(500, 3000)
            val = sl * sku[2]
            lines.append({"ma_don": ma_don, "sku": sku[0], "phan_loai": sku[1],
                          "so_luong": sl, "gia_tri": val})
            gia_tri_don += val

        order_rows.append({
            "ma_don": ma_don, "ma_bg": bg["ma_bg"], "ngay_dat": ngay_dat,
            "ma_kh": bg["ma_kh"], "ma_dai_ly": branch[0], "khu_vuc": branch[2],
            "nhan_vien_kd": branch[3], "gia_tri": gia_tri_don,
            "hinh_thuc_tt": hinh_thuc, "so_ngay_tra_cham": so_ngay_tc,
        })
        line_rows.extend(lines)
        order_values.append(gia_tri_don)

    # R4 injections — thời điểm đặt đơn
    bg0 = bg_rows[0]
    order_rows[0]["ngay_dat"] = bg0["ngay_het_hieu_luc"] + timedelta(days=5)   # quá hạn
    order_rows[0]["ma_bg"] = bg0["ma_bg"]
    bg1 = bg_rows[1]
    order_rows[1]["ngay_dat"] = bg1["ngay_het_hieu_luc"] - timedelta(days=3)   # <7 ngày
    order_rows[1]["ma_bg"] = bg1["ma_bg"]

    # R2 injection — tỷ lệ dây dân dụng cao trong đơn dự án
    for oidx in (4, 9, 14):
        ma_don = order_rows[oidx]["ma_don"]
        line_rows[:] = [l for l in line_rows if l["ma_don"] != ma_don]
        du_sku = DU_AN_SKUS[0]
        dd_sku = DAN_DUNG_SKUS[1]
        du_val = 300 * du_sku[2]
        dd_val = int(du_val * 0.9)                    # ~47% dân dụng
        line_rows.append({"ma_don": ma_don, "sku": du_sku[0], "phan_loai": "du_an",
                          "so_luong": 300, "gia_tri": du_val})
        line_rows.append({"ma_don": ma_don, "sku": dd_sku[0], "phan_loai": "dan_dung",
                          "so_luong": dd_val // dd_sku[2], "gia_tri": dd_val})
        order_rows[oidx]["gia_tri"] = du_val + dd_val

    # R7 injection — channel stuffing (SL đặt ≫ run-rate)
    stuff_targets = []
    for oidx in (3, 8, 19):
        o = order_rows[oidx]
        sku = DU_AN_SKUS[1]
        line_rows.append({"ma_don": o["ma_don"], "sku": sku[0], "phan_loai": "du_an",
                          "so_luong": 9000, "gia_tri": 9000 * sku[2]})
        o["gia_tri"] += 9000 * sku[2]
        stuff_targets.append((o["ma_dai_ly"], sku[0]))

    # R8 injection — đơn lớn bất thường ngay trước cú nhảy giá đồng (~35 ngày trước)
    jump_date = REF_DATE - timedelta(days=35)
    for oidx in (6, 12):
        o = order_rows[oidx]
        o["ngay_dat"] = jump_date - timedelta(days=4)
        o["gia_tri"] = max(o["gia_tri"], 9_000_000_000)   # rất lớn → z-score cao

    df_order = pd.DataFrame(order_rows)
    df_line = pd.DataFrame(line_rows)

    # -- cong_no -------------------------------------------------------------
    cn_rows = []
    for kh, _name in CUSTOMERS:
        han_muc = rng.randint(15, 50) * 1_000_000_000   # 15–50 tỷ
        du_no = int(han_muc * rng.uniform(0.15, 0.40))
        cn_rows.append({
            "ma_kh": kh, "du_no": du_no, "han_muc": han_muc,
            "co_bao_lanh": rng.choices(["Y", "N"], weights=[0.7, 0.3])[0],
            "han_tra_cham_ngay": rng.choice([30, 45, 60]),
        })
    # R3 injections — vượt hạn mức & trả chậm thiếu bảo lãnh
    cn_rows[0]["du_no"] = int(cn_rows[0]["han_muc"] * 0.98)   # gần/vượt hạn mức
    cn_rows[1]["du_no"] = int(cn_rows[1]["han_muc"] * 1.05)   # vượt hạn mức
    cn_rows[3]["co_bao_lanh"] = "N"                            # trả chậm thiếu bảo lãnh (kết hợp order)
    df_cn = pd.DataFrame(cn_rows)

    # đảm bảo có đơn trả chậm >60d thiếu bảo lãnh cho R3
    order_rows[2]["hinh_thuc_tt"] = "tra_cham"
    order_rows[2]["so_ngay_tra_cham"] = 75
    order_rows[2]["ma_kh"] = "KH04"          # KH04 co_bao_lanh = N
    df_order = pd.DataFrame(order_rows)

    # -- coc -----------------------------------------------------------------
    coc_rows = []
    for o in order_rows:
        bg = bg_by_id[o["ma_bg"]]
        pct = round(rng.uniform(0.15, 0.40), 3)
        coc_rows.append({
            "ma_bg": o["ma_bg"], "ma_don": o["ma_don"],
            "so_tien_coc": int(bg["gia_tri"] * pct),
            "pct_tren_bg": pct,
            "ngay": _d(o["ngay_dat"] - timedelta(days=rng.randint(1, 10))),
        })
    # R9 injections — cọc <15%
    for cidx in (5, 10, 16, 24):
        coc_rows[cidx]["pct_tren_bg"] = round(rng.uniform(0.03, 0.12), 3)
        bgv = bg_by_id[order_rows[cidx]["ma_bg"]]["gia_tri"]
        coc_rows[cidx]["so_tien_coc"] = int(bgv * coc_rows[cidx]["pct_tren_bg"])
    df_coc = pd.DataFrame(coc_rows)

    # -- ton_kho_dai_ly ------------------------------------------------------
    tk_rows = []
    for branch in BRANCHES:
        for sku in DU_AN_SKUS:
            tk_rows.append({
                "ma_dai_ly": branch[0], "sku": sku[0],
                "ton": rng.randint(200, 1500),
                "toc_do_ban_bq": rng.randint(20, 120),   # đv/ngày
            })
    df_tk = pd.DataFrame(tk_rows)

    # -- event_log -----------------------------------------------------------
    steps = ["tham_dinh_da", "tgd_duyet", "xac_nhan_coc", "check_cong_no",
             "dat_don", "giao_hang", "thanh_toan"]
    ev_rows = []
    for oidx, o in enumerate(order_rows):
        base_ts = datetime.combine(o["ngay_dat"], datetime.min.time()) - timedelta(days=10)
        # R6 injections: vài order bỏ bước / đảo thứ tự
        order_steps = list(steps)
        if oidx == 30:
            order_steps.remove("xac_nhan_coc")           # thiếu xác nhận cọc
        elif oidx == 33:
            order_steps.remove("check_cong_no")           # thiếu check công nợ
        elif oidx == 37:
            order_steps[1], order_steps[2] = order_steps[2], order_steps[1]  # đảo thứ tự
        for si, step in enumerate(order_steps):
            ev_rows.append({
                "ma_don": o["ma_don"], "buoc": step, "thu_tu": si + 1,
                "timestamp": (base_ts + timedelta(days=si, hours=rng.randint(0, 8)))
                .isoformat(),
                "user": rng.choice(["kd01", "kt01", "tgd", "kho01"]),
                "co_chung_tu": rng.choice(["Y", "Y", "N"]),
            })
    df_event = pd.DataFrame(ev_rows)

    # Stringify dates cho CSV gọn
    for col in ["ngay_ban_hanh", "ngay_hieu_luc_tu", "ngay_hieu_luc_den"]:
        df_khung[col] = df_khung[col].map(_d)
    df_bg["ngay_tao"] = df_bg["ngay_tao"].map(_d)
    df_bg["ngay_het_hieu_luc"] = df_bg["ngay_het_hieu_luc"].map(_d)
    df_bg["ngay_het_hieu_luc_goc"] = df_bg["ngay_het_hieu_luc_goc"].map(_d)
    df_order["ngay_dat"] = df_order["ngay_dat"].map(_d)

    return {
        "khung_ck": df_khung, "bao_gia": df_bg, "order": df_order,
        "order_line": df_line, "cong_no": df_cn, "coc": df_coc,
        "du_an_master": df_da, "ma_tran_phan_quyen": df_matrix,
        "ton_kho_dai_ly": df_tk, "gia_dong": df_gia, "event_log": df_event,
    }


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tables = generate()
    for name, df in tables.items():
        df.to_csv(DATA_DIR / f"{name}.csv", index=False)
        print(f"  ✓ {name:18s} {len(df):5d} dòng")
    print(f"\nĐã ghi {len(tables)} bảng vào {DATA_DIR}")


if __name__ == "__main__":
    main()
