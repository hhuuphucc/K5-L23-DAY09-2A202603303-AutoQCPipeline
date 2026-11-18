# Báo cáo Day 09 — Trần Nguyễn Hữu Phúc, 2A202603303

## 1. Kết luận trước
Pipeline kết luận **Hold** (mã thoát 10). Vào 224 ảnh; bước 1 loại 22 ảnh (2 hỏng, 3 quá nhỏ, 8 trùng byte, 4 trùng gần đúng, 5 rò rỉ test) nên còn 202 ảnh; cả 202 ảnh được xuất ra `submission/export/clean_v1/` dưới dạng **bản nháp** (manifest ghi `decision=Hold`), chưa phải bản phát hành.
Lý do: không còn lỗi bắt buộc, nhưng 38/202 ảnh (18,8%) còn cảnh báo ngữ nghĩa chưa được người duyệt, vượt ngưỡng 10% của cửa chặn (`08_summary.json`).

## 2. Lỗi và phân việc
Lấy từ `02_error_list_v1` (có 149/224 ảnh có ít nhất một lỗi hoặc cảnh báo; 36 lỗi bắt buộc, 153 cảnh báo).

| Mã lỗi | Số ảnh/dòng | Ai sửa | Vì sao |
|---|---:|---|---|
| CORRUPT_IMAGE / BAD_SIZE | 2 / 3 ảnh | máy (xoá ảnh) | ảnh không dùng được, quy tắc rõ ràng |
| DUP_IMAGE_EXACT / DUP_IMAGE_NEAR | 8 / 4 ảnh | máy (xoá ảnh) | giữ ảnh đầu tiên, xoá bản sau |
| LEAK_TEST | 5 ảnh | máy (xoá ảnh) | rò rỉ làm sai số đo mAP |
| BAD_CLASS_ID / BAD_FORMAT / BOX_ZERO / DUP_BOX | 6 / 3 / 4 / 7 dòng | máy (`drop_line`, 20 dòng) | dòng hỏng cú pháp, xoá an toàn |
| BOX_OUT_OF_IMAGE | 8 dòng | máy (`clip_box`, 8 dòng) | cắt về trong ảnh, giữ nguyên lớp |
| BAD_CLASS_NAME | 1 file (`data.yaml`, 2 tên sai) | máy (`rename_classes`) | ghi lại đúng danh sách lớp dự án |
| MISSING_LABEL_FILE | 6 ảnh | **người** (`needs_label`) | máy không được bịa nhãn |
| POSSIBLE_MISSING / WRONG_CLASS / FALSE_POS / LOOSE_BOX | 52 / 18 / 27 / 24 ảnh | **người** | lỗi ngữ nghĩa, model có thể sai |
| EMPTY_LABEL, BOX_TINY, BOX_HUGE | 12 / 4 / 3 ảnh | **người** | cần nhìn ảnh mới biết là ảnh nền hay thiếu nhãn |

`05_review_queue.csv` có 125 ảnh. Thứ tự xếp theo trọng số trong cấu hình: 6 ảnh `NEEDS_LABEL` (điểm 10) ở đầu, rồi `WRONG_CLASS` (3), `MISSING` / `FALSE_POS` (2), `FIXED_DROP_LINE` (2), `LOOSE_BOX` (1,5), có nhân thêm theo `conf`. Ngân sách 80 ảnh phủ: 6/6 ảnh chưa có nhãn, 18/18 ảnh `WRONG_CLASS`, 50/52 ảnh `MISSING`, 12/23 ảnh `FALSE_POS` và chỉ 8/24 ảnh `LOOSE_BOX`. Còn 45 ảnh trong hàng đợi không ai xem, nên lỗi ngữ nghĩa nhẹ (box lỏng, box thừa) là phần chịu thiệt.

## 3. Calibration (2 ngưỡng)
Đo trên `data/calib` (39 ảnh) bằng `make calibrate`; chi tiết trong `submission/calibration/`.

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau) | Lý do (đánh đổi) |
|---|---|---|---|---|
| `duplicates.phash_dist` | 2 | 12 | `DUP_IMAGE_NEAR`: 1,00 / 0,50 → 1,00 / 0,67; `DUP_IMAGE_EXACT` giữ 1,00 / 1,00 | xoá ảnh là hành động không hoàn tác, nên ưu tiên precision. Precision giữ 1,00 trong cả dải 2–20; recall đứng yên từ 4 đến 14 nên chọn 12, cách xa mức 16 là nơi bắt đầu gộp nhầm |
| `second_opinion.conf` | 0.25 | 0.6 | `MISSING`: 0,50 / 1,00 → 0,57 / 1,00; `WRONG_CLASS`: 0,56 / 0,83 → 0,62 / 0,83; `LOOSE_BOX`: 0,29 / 0,40 → 0,20 / 0,20 | 0.6 là mức cao nhất mà recall `MISSING` còn 1,00 (từ 0.7 tụt còn 0,88). Bỏ sót lỗi tốn hơn một ảnh dư trong hàng đợi, nên không chọn 0.8 dù precision `WRONG_CLASS` đạt 1,00 |

**Chỗ calibration có thể đánh lừa.** Trên calib, `phash_dist` = 16 cho `DUP_IMAGE_NEAR` điểm cao nhất (precision 1,00, recall 0,83) vì calib chỉ có 30 ảnh khác nhau, không đủ để lộ gộp nhầm. Trên `data/raw`, mức 16 làm số ảnh rò rỉ test tăng từ 5 lên 11 và số cặp trùng gần đúng từ 4 lên 7. Tôi mở xem các cặp ở mức 16: `img_0011` với `img_0008` (tennis và trượt tuyết) rõ ràng là hai ảnh khác nhau, còn `img_0084` với `img_0074` thì là cùng một ảnh bị phóng to. Vậy mức 16 vừa gộp nhầm vừa bắt thêm được một cặp thật, và calib không cho biết điều đó. Ở mức 12, cả 4 cặp bị loại (khoảng cách phash 0, 0, 6, 10) đều là cặp trùng thật khi xem bằng mắt, và số ảnh bị loại ở bước 1 (22/224, gần 10%) là hợp lý.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được
(a) Chạy `python -m pipeline.run --budget 0 --work work/nb --reports work/rep_nb --export-dir work/exp_nb` (không có người duyệt): còn 6 lỗi bắt buộc `MISSING_LABEL_FILE`, kết luận **Rework**, mã thoát **20**, và log in "KHÔNG xuất"; thư mục `work/exp_nb` không được tạo. Vậy cửa chặn không cho dataset thiếu nhãn đi tiếp.

(b) Điểm mù:
1. **Ảnh trùng biến đổi mạnh.** Ở `phash_dist` = 12 pipeline bỏ sót cặp `img_0084` / `img_0074` (cùng ảnh, một bản bị phóng to, phash cách 16). Trên calib `DUP_IMAGE_NEAR` cũng chỉ đạt recall 0,67 (bỏ sót 2/6 ảnh).
2. **Box lỏng nhẹ.** `POSSIBLE_LOOSE_BOX` chỉ đạt precision / recall 0,20 / 0,20 ở `conf` = 0.6 và vẫn tệ ở mọi mức khác (cao nhất 0,38 / 0,60 ở 0.1). Box lệch ít (IoU ≥ 0,5 so với model) không bị cờ, và hàng đợi chỉ phủ 8/24 ảnh `LOOSE_BOX`.
3. **Cảnh báo giả nhiều.** `POSSIBLE_FALSE_POS` chỉ có precision 0,31 trên calib (5 lỗi thật, 11 cờ sai) vì nhãn người khác model ở những vật khó. Cờ này tốn lượt duyệt nhưng ít giá trị.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)
Chưa chạy (phần tùy chọn, chưa train trên Colab).

## 6. Quyết định và ghi chú AI
(a) Quyết định: **Hold**, chưa phát hành `clean_v1`. Để thành Release cần giảm số ảnh còn cảnh báo chưa duyệt từ 38 xuống ≤ 20 trên 202 ảnh (dưới 10%), tức người duyệt thêm ít nhất 18 ảnh, hoặc rà lại ngưỡng cảnh báo `LOOSE_BOX` / `FALSE_POS` vốn có precision thấp. Cũng cần người thật gán nhãn cho 6 ảnh chưa có file nhãn (ở lần chạy chính, bước duyệt mô phỏng đã gán).

(b) Dùng AI: có, Claude Code viết 4 module (`label_format`, `gate`, `autofix`, `second_opinion`) và các lệnh calibrate / chạy pipeline.
- Prompt chính: "viết cả 4 module theo thứ tự, thật kỹ, chi tiết" kèm docstring và test có sẵn trong repo.
- Cách kiểm: chạy `pytest` (79/79 xanh), chạy pipeline thật, mở xem các cặp ảnh bị cho là trùng, và đối chiếu số liệu báo cáo với `submission/reports/`.
- AI sai một lần: lúc ghi file bằng script, ký tự xuống dòng trong `autofix.py` bị chèn sai làm file không chạy được (SyntaxError); phát hiện nhờ `pytest` và sửa lại.
