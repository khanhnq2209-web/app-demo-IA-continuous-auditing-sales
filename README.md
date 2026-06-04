# Giám sát Liên tục Quy trình Bán hàng Dự án (Dây & Cáp điện)

Web app **continuous monitoring** phát hiện & cảnh báo rủi ro trong quy trình bán
hàng dự án: `Khung CK → Thẩm định DA → TGĐ duyệt → Cọc/Công nợ → Đặt đơn/Giao →
Thanh toán`. Rule engine tự động sinh **Exceptions** theo 10 rule, hiển thị qua 3
tab Streamlit với biểu đồ **Plotly** màu RAG.

> Dữ liệu mẫu mô hình **1 công ty với 11 chi nhánh / đại lý** (DL01–DL11), có cài
> sẵn vi phạm cho cả 10 rule để demo.

## Cài đặt & chạy

```bash
pip install -r requirements.txt
python scripts/generate_seed_data.py     # sinh dữ liệu mẫu vào data/
streamlit run app.py                      # mở http://localhost:8501
```

Chạy test rule engine:

```bash
python -m pytest tests/ -v
```

## Kiến trúc

```
Nguồn dữ liệu (CSV/Excel)
   → data_loader.py     (ingest, chuẩn hóa schema)
   → rules.py           (Rule Engine: R1..R10, áp ngưỡng từ config)
   → app.py             (Streamlit: 3 tab + Plotly charts)
   → alerts.py          (Alert dispatcher — STUB/log, routing theo config)
```

| File | Vai trò |
|------|---------|
| `src/schema.py` | Single source of truth: schema 11 bảng, bảng màu RAG, registry 10 rule + ngưỡng mặc định |
| `src/rules.py` | Rule engine thuần pandas (test độc lập, không phụ thuộc Streamlit) |
| `src/data_loader.py` | Đọc CSV/upload → DataFrame; validate cột |
| `src/config_manager.py` | Lưu/đọc cấu hình rule & alert routing (JSON) + ghi audit |
| `src/store.py` | Lưu trạng thái workflow exception (khóa ổn định qua các lần chạy) |
| `src/audit.py` | Audit trail append-only (`logs/audit_log.jsonl`) |
| `src/alerts.py` | Định tuyến & "gửi" cảnh báo (stub) → `logs/alert_log.jsonl` |
| `src/charts.py` | Mọi biểu đồ Plotly (scorecard, heatmap, funnel, Sankey, overlay giá đồng…) |
| `app.py` | UI Streamlit: sidebar + Config / Monitoring / Exceptions |
| `scripts/generate_seed_data.py` | Sinh dữ liệu giả lập 11 bảng + vi phạm cài sẵn |

## 10 Rule

| ID | Tên | Mức | Đối tượng |
|----|-----|-----|-----------|
| R1 | Vượt phân quyền / CK & thiếu lưu vết duyệt | 🔴 | BG |
| R2 | Tỷ lệ dây dân dụng trong đơn dự án | 🔴 | đơn |
| R3 | Vượt hạn mức / trả chậm thiếu bảo lãnh | 🔴 | KH + đơn |
| R4 | Hiệu lực & thời điểm đặt đơn | 🔴 | đơn |
| R5 | Dự án ma / dưới ngưỡng | 🔴 | DA |
| R6 | Quy trình không trôi đúng mạch (skip/đảo bước) | 🟡 | đơn |
| R7 | Channel stuffing (tồn đại lý) | 🟡 | đơn |
| R8 | Đặt hàng đón giá đồng (z-score) | 🟢 | đơn |
| R9 | Cọc < 15% | 🔴 | đơn |
| R10 | Phát sinh theo chiết khấu cũ | 🟡 | đơn |

Ngưỡng từng rule chỉnh được trong **Tab Config → Ngưỡng rule** (mọi thay đổi ghi
audit `before→after`).

## 3 Tab

- **⚙️ Config** — Rule Registry (on/off, mức), ngưỡng editable, Alert Routing,
  ma trận phân quyền, Data Source (upload / tạo lại dữ liệu mẫu), Audit trail.
- **📊 Monitoring** (BOM) — Scorecard 🔴🟡🟢 + tổng giá trị rủi ro + delta 30d,
  RAG heatmap (Rule × khu vực), biểu đồ theo rule, xu hướng exception, top vi phạm.
- **🚨 Exceptions** (KTNB) — bảng exception, panel chi tiết + dữ liệu gốc, workflow
  trạng thái (`Open → Đang rà soát → Đã giải trình / Xác nhận vi phạm → Escalate
  BOM → Đóng`), gán người xử lý, export Excel/CSV.

**Phân quyền xem:** chọn vai trò ở sidebar — *BOM/TGĐ* chỉ thấy Monitoring;
*KTNB/Admin* thấy cả 3 tab.

## Ghi chú triển khai

- **Cảnh báo** hiện ở chế độ **stub** (ghi `logs/alert_log.jsonl`, không gửi thật).
  Tích hợp SMTP / Telegram / Zalo bằng cách thay hàm `_send()` trong `src/alerts.py`.
- Dữ liệu là **synthetic**. Thay bằng dữ liệu thật qua upload (Tab Config → Data
  Source) hoặc đẩy CSV đúng schema vào `data/`.
- Một số điểm cần chốt nghiệp vụ còn liệt kê ở `doc/requirement_giam_sat_ban_hang_du_an.md` (Phụ lục).
