"""Single source of truth: entity schemas, RAG palette, business thresholds, rule registry.

Every other module imports constants from here so the UI, rule engine, data
generator, and tests stay in sync.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# RAG palette (khớp màu flow) — dùng nhất quán cho mọi chart Plotly
# ---------------------------------------------------------------------------
RAG_COLORS = {"do": "#E03C32", "vang": "#FFD301", "xanh": "#7BB662"}
RAG_LABEL = {"do": "🔴 Cao", "vang": "🟡 Trung bình", "xanh": "🟢 Thông tin"}
RAG_ORDER = ["do", "vang", "xanh"]

# ---------------------------------------------------------------------------
# Ngưỡng nghiệp vụ chốt (mặc định) — có thể override qua config UI
# ---------------------------------------------------------------------------
BG_VALIDITY_DAYS = 60          # hiệu lực báo giá
DEPOSIT_MIN_PCT = 0.15         # cọc tối thiểu 15% tổng BG
ORDER_LEAD_DAYS = 7            # đặt đơn ≥7 ngày trước khi BG hết hạn
DA_MIN_VALUE = 100_000_000     # giá trị DA tối thiểu để nhận giá dự án (100tr)
MAX_TRA_CHAM_DAYS = 60         # trả chậm tối đa 60 ngày (cần bảo lãnh)

# ---------------------------------------------------------------------------
# Các bảng dữ liệu đầu vào & cột bắt buộc (dùng cho validate khi upload)
# ---------------------------------------------------------------------------
ENTITIES: dict[str, list[str]] = {
    "khung_ck": [
        "ma_khung", "nhom_sp", "muc_ck", "ngay_ban_hanh",
        "ngay_hieu_luc_tu", "ngay_hieu_luc_den",
    ],
    "bao_gia": [
        "ma_bg", "ngay_tao", "ngay_het_hieu_luc", "ma_kh", "ma_da",
        "nguoi_duyet", "vai_tro_nguoi_duyet", "kenh_duyet", "co_chung_tu",
        "gia_tri", "pct_ck", "ma_khung", "gia_han",
    ],
    "order": [
        "ma_don", "ma_bg", "ngay_dat", "ma_kh", "ma_dai_ly", "khu_vuc",
        "nhan_vien_kd", "gia_tri", "hinh_thuc_tt", "so_ngay_tra_cham",
    ],
    "order_line": [
        "ma_don", "sku", "phan_loai", "so_luong", "gia_tri",
    ],
    "cong_no": [
        "ma_kh", "du_no", "han_muc", "co_bao_lanh", "han_tra_cham_ngay",
    ],
    "coc": [
        "ma_bg", "ma_don", "so_tien_coc", "pct_tren_bg", "ngay",
    ],
    "du_an_master": [
        "ma_da", "ten_da", "dia_chi", "chu_dau_tu", "gia_tri_da",
    ],
    "ma_tran_phan_quyen": [
        "vai_tro", "han_muc_gia_tri", "han_muc_ck",
    ],
    "ton_kho_dai_ly": [
        "ma_dai_ly", "sku", "ton", "toc_do_ban_bq",
    ],
    "gia_dong": [
        "ngay", "gia_dong",
    ],
    "event_log": [
        "ma_don", "buoc", "thu_tu", "timestamp", "user", "co_chung_tu",
    ],
}

# Chuỗi bước control chuẩn của một order (dùng cho R6)
CONTROL_STEPS = [
    "tham_dinh_da",      # thẩm định dự án
    "tgd_duyet",         # TGĐ phê duyệt CK
    "xac_nhan_coc",      # kế toán xác nhận cọc ≥15%
    "check_cong_no",     # kiểm tra công nợ trước xuất HĐ
    "dat_don",           # nhận đặt đơn
    "giao_hang",         # vận chuyển/giao
    "thanh_toan",        # nhận thanh toán / xuất HĐ
]

# ---------------------------------------------------------------------------
# Rule registry — metadata + ngưỡng mặc định (override được qua config)
# ---------------------------------------------------------------------------
RULE_REGISTRY: dict[str, dict] = {
    "R1": {
        "name": "Vượt phân quyền / Chiết khấu & thiếu lưu vết duyệt",
        "group": "Authorization",
        "severity": "do",
        "enabled": True,
        "desc": "Đề xuất chiết khấu vượt khung chiết khấu HOẶC người duyệt "
                "vượt hạn mức; duyệt chỉ qua Zalo, không có chứng từ chính thức.",
        "thresholds": {"require_official_doc": True},
    },
    "R2": {
        "name": "Tỷ lệ dây dân dụng trong đơn dự án",
        "group": "Pricing leakage",
        "severity": "do",
        "enabled": True,
        "desc": "Giá trị dây dân dụng / giá trị đơn vượt ngưỡng cho phép.",
        "thresholds": {"pct_threshold": 0.30, "size_band_pct": 0.35,
                       "size_band_value": 500_000_000},
    },
    "R3": {
        "name": "Vượt hạn mức / trả chậm thiếu bảo lãnh",
        "group": "Credit",
        "severity": "do",
        "enabled": True,
        "desc": "(dư nợ + đơn)/hạn mức vượt ngưỡng; trả chậm quá 60 ngày; "
                "trả chậm mà thiếu bảo lãnh/ký quỹ.",
        "thresholds": {"warn_pct": 0.85, "violate_pct": 1.00,
                       "max_tra_cham_days": MAX_TRA_CHAM_DAYS},
    },
    "R4": {
        "name": "Hiệu lực & thời điểm đặt đơn",
        "group": "Quote validity",
        "severity": "do",
        "enabled": True,
        "desc": "Báo giá hết hạn vẫn phát sinh đơn; đơn đặt dưới 7 ngày trước "
                "hết hạn; có gia hạn hiệu lực (bị cấm).",
        "thresholds": {"min_days_before_expiry": ORDER_LEAD_DAYS},
    },
    "R5": {
        "name": "Dự án ma / dưới ngưỡng",
        "group": "Master data",
        "severity": "do",
        "enabled": True,
        "desc": "Dữ liệu danh mục thiếu trường bắt buộc; trùng tên/địa chỉ; "
                "giá trị dự án dưới 100 triệu vẫn nhận giá dự án.",
        "thresholds": {"min_da_value": DA_MIN_VALUE},
    },
    "R6": {
        "name": "Quy trình không trôi đúng mạch",
        "group": "Process",
        "severity": "vang",
        "enabled": True,
        "desc": "Bỏ/đảo bước kiểm soát (gồm thiếu xác nhận cọc, "
                "thiếu kiểm tra công nợ trước xuất hóa đơn).",
        "thresholds": {"required_steps": CONTROL_STEPS},
    },
    "R7": {
        "name": "Channel stuffing (tồn đại lý)",
        "group": "Channel",
        "severity": "vang",
        "enabled": True,
        "desc": "Số lượng đặt vượt xa (tồn + tốc độ bán bình quân); "
                "đơn lớn hơn N lần tốc độ bán bình quân.",
        "thresholds": {"run_rate_multiplier": 3.0, "run_rate_horizon_days": 30},
    },
    "R8": {
        "name": "Đặt hàng đón giá đồng",
        "group": "Market",
        "severity": "xanh",
        "enabled": True,
        "desc": "Đơn lớn bất thường ngay trước biến động tăng giá đồng "
                "(theo điểm z-score).",
        "thresholds": {"zscore_threshold": 2.0, "window_days": 7,
                       "price_jump_pct": 0.03},
    },
    "R9": {
        "name": "Cọc < 15%",
        "group": "Payment",
        "severity": "do",
        "enabled": True,
        "desc": "Xuất hóa đơn/giao khi cọc dưới 15% tổng báo giá "
                "(ngoài diện trả chậm có bảo lãnh).",
        "thresholds": {"min_deposit_pct": DEPOSIT_MIN_PCT},
    },
    "R10": {
        "name": "Phát sinh theo chiết khấu cũ",
        "group": "Pricing",
        "severity": "vang",
        "enabled": True,
        "desc": "Đơn phát sinh áp khung chiết khấu đã hết hiệu lực / không tái duyệt.",
        "thresholds": {},
    },
}

ALL_RULE_IDS = list(RULE_REGISTRY.keys())

# Trạng thái xử lý exception (workflow Tab 3)
EXCEPTION_STATUSES = [
    "Open",
    "Đang rà soát",
    "Đã giải trình",
    "Xác nhận vi phạm",
    "Escalate BOM",
    "Đóng",
]

# Cột chuẩn của một exception (output rule engine)
EXCEPTION_COLUMNS = [
    "ma_exception", "rule_id", "rule_name", "severity", "doi_tuong_type",
    "doi_tuong_id", "kh_da", "gia_tri", "ngay_phat_hien", "ly_do",
    "status", "nguoi_xu_ly",
]
