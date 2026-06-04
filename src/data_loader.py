"""Lớp ingest: đọc dữ liệu nguồn (CSV seed hoặc file upload) → DataFrame chuẩn hóa."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schema import ENTITIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Cột kiểu ngày cần parse cho từng bảng
DATE_COLUMNS = {
    "khung_ck": ["ngay_ban_hanh", "ngay_hieu_luc_tu", "ngay_hieu_luc_den"],
    "bao_gia": ["ngay_tao", "ngay_het_hieu_luc", "ngay_het_hieu_luc_goc"],
    "order": ["ngay_dat"],
    "coc": ["ngay"],
    "gia_dong": ["ngay"],
    "event_log": ["timestamp"],
}


def _parse_dates(name: str, df: pd.DataFrame) -> pd.DataFrame:
    for col in DATE_COLUMNS.get(name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_table(name: str, data_dir: Path | None = None) -> pd.DataFrame:
    """Đọc 1 bảng từ CSV. Trả DataFrame rỗng (đúng cột) nếu file thiếu."""
    data_dir = data_dir or DATA_DIR
    path = data_dir / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame(columns=ENTITIES.get(name, []))
    df = pd.read_csv(path)
    return _parse_dates(name, df)


def load_all(data_dir: Path | None = None) -> dict[str, pd.DataFrame]:
    """Đọc toàn bộ 11 bảng thành dict[name -> DataFrame]."""
    return {name: load_table(name, data_dir) for name in ENTITIES}


def validate_table(name: str, df: pd.DataFrame) -> list[str]:
    """Kiểm tra cột bắt buộc khi upload. Trả danh sách cột thiếu."""
    required = set(ENTITIES.get(name, []))
    return sorted(required - set(df.columns))


def read_upload(name: str, file) -> pd.DataFrame:
    """Đọc file upload (.csv/.xlsx) cho bảng `name`, parse ngày."""
    fname = getattr(file, "name", "").lower()
    if fname.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        df = pd.read_csv(file)
    return _parse_dates(name, df)


def data_status(data_dir: Path | None = None) -> pd.DataFrame:
    """Trạng thái nguồn dữ liệu: bảng | có file | số dòng | cập nhật cuối."""
    data_dir = data_dir or DATA_DIR
    rows = []
    for name in ENTITIES:
        path = data_dir / f"{name}.csv"
        if path.exists():
            stat = path.stat()
            rows.append({
                "bảng": name,
                "trạng_thái": "✅ kết nối",
                "số_dòng": sum(1 for _ in path.open(encoding="utf-8")) - 1,
                "cập_nhật_cuối": pd.Timestamp(stat.st_mtime, unit="s")
                .strftime("%Y-%m-%d %H:%M"),
            })
        else:
            rows.append({"bảng": name, "trạng_thái": "❌ thiếu",
                         "số_dòng": 0, "cập_nhật_cuối": "-"})
    return pd.DataFrame(rows)
