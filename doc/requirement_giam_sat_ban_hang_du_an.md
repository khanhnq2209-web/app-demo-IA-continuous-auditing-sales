# Requirement — Web App Giám sát Liên tục Quy trình Bán hàng Dự án (Dây & Cáp điện)

**Phiên bản:** 1.1 (cập nhật theo flow chi tiết + chốt Plotly)
**Nền tảng:** Streamlit (Python) · **Lớp visual:** Plotly
**Đối tượng sử dụng:** Phòng Kiểm toán nội bộ (chi tiết exception) + BOM/TGĐ (giám sát RAG cấp cao)
**Mục tiêu:** Giám sát liên tục (continuous monitoring) rủi ro trong quy trình `Khung CK → Thẩm định DA → TGĐ duyệt → Cọc/Công nợ → Đặt đơn/Giao → Thanh toán`, tự động phát hiện và cảnh báo vi phạm rule.

---

## 1. Quy trình chuẩn (rút từ flow) & các điểm kiểm soát

| # | Phòng ban | Hoạt động | Control point |
|---|-----------|-----------|---------------|
| 1 | KD Dự án 🟢 | Nhận & thông báo khung chiết khấu (CMB) đến đại lý | khung CK chuẩn |
| 2 | KD Dự án 🟢 | Thẩm định DA theo Phiếu thông tin DA (≥100tr); đề xuất CK theo khung đã ban hành | giá trị DA ≥100tr; CK ≤ khung |
| 3 | **TGĐ 🔴** | Phê duyệt CK qua Zalo: DA ≥100tr · không gia hạn hiệu lực · không duyệt phát sinh theo CK cũ · hiệu lực BG 60 ngày | **điểm control trọng yếu** |
| 4 | Kế toán 🟡 | Xác nhận cọc đủ **15%** tổng BG; kiểm tra thanh toán & công nợ trước xuất HĐ | cọc ≥15%; check công nợ |
| 5 | KD Dự án 🟢 | Nhận đặt đơn **≥7 ngày trước** BG hết hiệu lực; nhận xác nhận công nợ; vận chuyển | đặt đơn ≥7d trước hạn |
| 6 | Kế toán 🟡 | Nhận thanh toán trước xuất HĐ, hoặc trả chậm ≤60 ngày **nếu có bảo lãnh/ký quỹ**; trừ cọc vào đơn cuối | trả chậm có điều kiện |

> Các ngưỡng nghiệp vụ chốt: **DA ≥100tr · cọc ≥15% · hiệu lực BG 60 ngày (không gia hạn) · đặt đơn ≥7d trước hạn · trả chậm ≤60d chỉ khi có bảo lãnh/ký quỹ · không phát sinh theo CK cũ.**

---

## 2. Kiến trúc tổng thể

```
Nguồn dữ liệu (ERP/Excel/DB)
        │
        ▼
[Lớp ingest] → chuẩn hóa schema → staging
        │
        ▼
[Rule Engine] (rules.py) → áp ngưỡng từ Config → sinh Exceptions
        │
        ├──────────────┬──────────────────┐
        ▼              ▼                  ▼
   [Tab Config]   [Tab Monitoring]   [Tab Exceptions]   ← Streamlit UI
                  └─ Plotly charts ─┘
        │
        ▼
[Alert dispatcher] → Email / Telegram / Zalo (theo routing)
```

Rule engine tách module riêng (`rules.py`) để test độc lập. Mọi biểu đồ dùng **Plotly** (`st.plotly_chart`), không dùng chart mặc định của Streamlit — đáp ứng yêu cầu trực quan/màu mè + tương tác (hover, zoom, drill).

---

## 3. Nguồn dữ liệu đầu vào

| Bảng | Trường chính | Rule |
|------|--------------|------|
| `khung_ck` (CMB) | mã khung, mức CK, ngày hiệu lực/ban hành | R1, R10 |
| `bao_gia` | mã BG, ngày tạo, hiệu lực (60d), KH, dự án, người duyệt, kênh duyệt (Zalo?), giá trị, %CK | R1, R2, R4, R10 |
| `order` | mã đơn, mã BG nguồn, ngày đặt, KH, đại lý, giá trị | R1, R3, R4, R6, R7 |
| `order_line` | mã đơn, SKU, phân loại (dân dụng/dự án), SL, giá trị | R2 |
| `cong_no` (AR) | KH, dư nợ, hạn mức, có bảo lãnh/ký quỹ (Y/N), hạn trả chậm | R3 |
| `coc` | mã BG/đơn, số tiền cọc, % trên tổng BG, ngày | R9 |
| `du_an_master` | tên DA, địa chỉ, mã, chủ đầu tư, giá trị DA | R5 |
| `ma_tran_phan_quyen` | vai trò, hạn mức giá trị, hạn mức CK | R1 |
| `ton_kho_dai_ly` | đại lý, SKU, tồn, tốc độ bán bình quân | R7 |
| `gia_dong` | ngày, giá đồng | R8 |
| `event_log` | mã đơn, bước, timestamp, user, chứng từ kèm | R6 |

---

## 4. Catalog Rule (10 rule)

| ID | Tên | Logic phát hiện | Ngưỡng mặc định | Mức | Nhóm |
|----|-----|-----------------|-----------------|-----|------|
| **R1** | Vượt phân quyền / CK & thiếu lưu vết duyệt | đề xuất CK > khung CMB HOẶC người duyệt vượt hạn mức; duyệt chỉ có Zalo, không chứng từ chính thức | theo khung & ma trận | 🔴 | Authorization |
| **R2** | Tỷ lệ dây dân dụng trong đơn dự án | `value(SKU dân dụng)/value(đơn)` | >30% (>35% theo size band) | 🔴 | Pricing leakage |
| **R3** | Vượt hạn mức / trả chậm thiếu bảo lãnh | `(dư nợ+đơn)/hạn mức`; trả chậm >60d; trả chậm mà thiếu bảo lãnh/ký quỹ | cảnh báo >85%, vi phạm >100%; thiếu bảo lãnh | 🔴 | Credit |
| **R4** | Hiệu lực & thời điểm đặt đơn | BG hết hạn vẫn phát sinh đơn; đơn đặt <7 ngày trước hết hạn; có gia hạn hiệu lực (bị cấm) | <7d trước hạn; quá hạn; gia hạn | 🔴 | Quote validity |
| **R5** | Dự án ma / dưới ngưỡng | master thiếu trường bắt buộc; trùng tên/địa chỉ; giá trị DA <100tr vẫn nhận giá dự án | thiếu field / trùng / <100tr | 🔴 | Master data |
| **R6** | Quy trình không trôi đúng mạch | bỏ/đảo bước control (gồm thiếu xác nhận cọc, thiếu check công nợ trước xuất HĐ) | skip / sai thứ tự | 🟡 | Process |
| **R7** | Channel stuffing (tồn đại lý) | SL đặt ≫ (tồn + tốc độ bán bình quân) | đơn > N× run-rate (N=3) | 🟡 | Channel |
| **R8** | Đặt hàng đón giá đồng | đơn lớn bất thường ngay trước biến động giá đồng | z-score & lệch xu hướng giá | 🟢 | Market |
| **R9** | Cọc < 15% | xuất HĐ/giao khi cọc <15% tổng BG (ngoài diện trả chậm có bảo lãnh) | cọc < 15% | 🔴 | Payment |
| **R10** | Phát sinh theo chiết khấu cũ | đơn phát sinh áp khung CK đã hết hiệu lực / không tái duyệt | dùng CK cũ | 🟡 | Pricing |

**RAG:** 🔴 cao, xử lý/giải trình ngay · 🟡 cần rà soát · 🟢 thông tin phân tích.
**Output exception:** `mã · rule · đối tượng (BG/đơn) · KH/DA · giá trị · ngày phát hiện · mức · trạng thái`.

---

## 5. Layout giao diện — 3 Tab

### Sidebar (chung)
`khoảng ngày` · `nhân viên KD` · `khu vực` · `nhóm SP` · `khách hàng/đại lý` · `mức độ (RAG)` · nút **Run rules / Refresh**.

### TAB 1 — CONFIG
```
┌ Rule Registry: [bảng] Rule | On/Off | Ngưỡng (editable) | Mức | Sửa lần cuối ┐
│   - chỉnh ngưỡng (number_input/slider) · toggle bật-tắt                      │
├ Alert Routing: Rule → Vai trò → Kênh (Email/Telegram/Zalo) → Tần suất         │
│   VD: R1,R3,R4,R5,R9 (🔴) → TGĐ + Trưởng KTNB → Email+Telegram realtime        │
│       tất cả → KTNB → digest hàng ngày                                        │
├ User & Role: quản lý quyền xem tab/khu vực · upload ma trận phân quyền (Excel) │
├ Data Source: trạng thái kết nối · lần cập nhật cuối · upload file             │
└ (mọi thay đổi ngưỡng ghi log: user, time, cũ→mới)                            ┘
```

### TAB 2 — MONITORING (cho BOM — Plotly, RAG màu)
```
┌ Scorecard: [🔴 N][🟡 N][🟢 N] + delta 30d + tổng giá trị rủi ro             ┐
├ RAG Heatmap: hàng=Rule(R1..R10) × cột=kỳ/khu vực · click ô → lọc Exceptions  │
├ Grid biểu đồ theo rule (xem §6)                                              │
├ Xu hướng exception theo thời gian (mức độ)                                   │
└ Top vi phạm theo nhân viên KD / khu vực                                      ┘
```
Phong cách: ít chữ, màu RAG khớp màu flow, mỗi chart có chú giải 1 dòng.

### TAB 3 — EXCEPTIONS (cho Kiểm toán)
```
┌ Bộ lọc nhanh: mức · rule · trạng thái · ngày                                 ┐
├ Bảng Exception: mã|rule|đối tượng|KH/DA|giá trị|ngày|mức|status → chọn dòng   │
├ Panel chi tiết: dữ liệu gốc + lý do trigger · lịch sử trạng thái · ghi chú KT │
├ Workflow trạng thái (xem dưới) · gán người xử lý · Export Excel/PDF          │
└──────────────────────────────────────────────────────────────────────────┘
```
```
Open → Đang rà soát → ┬─ Đã giải trình (đóng, lưu lý do)
                      └─ Xác nhận vi phạm → Escalate BOM → Đóng
```

---

## 6. Đặc tả Plotly (lớp visual)

Import: `import plotly.express as px` · `import plotly.graph_objects as go` · `from plotly.subplots import make_subplots`.
Render: `st.plotly_chart(fig, use_container_width=True)` · template `plotly_white`.
Bảng màu RAG nhất quán (khớp màu flow): `{"do":"#E03C32","vang":"#FFD301","xanh":"#7BB662"}`.

| Widget | Plotly | Ghi chú |
|--------|--------|---------|
| Scorecard 🔴🟡🟢 | `go.Indicator` (number+delta) | 3 KPI, delta vs 30 ngày trước |
| RAG heatmap rule×kỳ | `px.imshow` / `go.Heatmap` | colorscale rời rạc theo RAG; `customdata` để drill |
| Tỷ lệ sử dụng tín dụng — R3 | `px.bar` (ngang) | màu theo ngưỡng 85/100%; vạch `add_vline` |
| Phân bố tỷ lệ dây dân dụng — R2 | `px.histogram` / `go.Box` | `add_vline` mốc 30% |
| Funnel hiệu lực BG — R4 | `go.Funnel` hoặc stacked `px.bar` | đã lấy vs còn lại theo BG |
| Luồng order & bước skip — R6 | `go.Sankey` | trực quan bước bị bỏ/đảo |
| Overlay giá đồng × khối lượng — R8 | `make_subplots(secondary_y=True)` | line (giá đồng) + bar (KL đơn) |
| Xu hướng exception | `px.area` / `px.line` | stack theo mức độ |
| Top vi phạm KD/khu vực | `px.bar` | sort giảm dần |

Tương tác: bật `hovertemplate` rõ ràng (mã đối tượng, giá trị, ngưỡng); dùng `st.session_state` lưu lựa chọn filter; cân nhắc `plotly_events` để click chart → lọc Tab 3.

---

## 7. Cảnh báo & Phi chức năng

| Hạng mục | Yêu cầu |
|----------|---------|
| Routing | Rule → vai trò → kênh (Email/Telegram/Zalo) → tần suất (realtime 🔴 / digest ngày / tuần) |
| Chống nhiễu | gộp digest cùng rule; không gửi lại exception đã đóng |
| Phân quyền xem | BOM: Tab 2 · KTNB: cả 3 tab · cấu hình rule: KTNB/admin |
| Audit trail | log mọi thay đổi ngưỡng / trạng thái / cảnh báo (user, time, before→after) |
| Tần suất chạy | rule engine theo lịch (hàng đêm) + nút chạy tay |
| Hiệu năng | batch + `st.cache_data` cho dữ liệu đã tính |
| Truy vết | snapshot dữ liệu gốc tại thời điểm phát hiện |

---

## 8. Roadmap

| Phase | Phạm vi |
|-------|---------|
| **1 (MVP)** | R1–R5, R9 (dữ liệu nội bộ sẵn) · 3 tab cơ bản · Plotly core (scorecard, heatmap, R3/R4) · cảnh báo Email |
| **2** | R6 (event log), R7, R10 · Sankey · workflow đầy đủ · Telegram/Zalo |
| **3** | R8 (overlay giá đồng), phân tích z-score/xu hướng · tinh chỉnh dashboard BOM |

---

## Phụ lục — Cần làm rõ với nghiệp vụ

1. **R2:** tỷ lệ dây dân dụng tính theo *giá trị* hay *số lượng*? Size band 30% vs 35% chia theo tiêu chí nào?
2. **R5:** danh sách trường "bắt buộc" của master DA để định nghĩa "dự án ma"?
3. **R6:** chuỗi bước control chuẩn của một order (để phát hiện skip/đảo)?
4. **R7:** lấy tồn kho & tốc độ bán đại lý từ đâu?
5. **R9:** cọc 15% kiểm tại thời điểm nào — trước xuất HĐ hay trước giao? Đơn cuối trừ cọc xử lý ra sao?
6. **R10:** định nghĩa chính xác "phát sinh theo chiết khấu cũ"?
7. **R1/Zalo:** có hệ thống lưu vết phê duyệt chính thức (ngoài Zalo) không? Nếu không → cờ thiếu chứng từ áp ra sao?
8. **Phân quyền:** ma trận hạn mức theo vai trò đã ở dạng cấu trúc (Excel) chưa?
