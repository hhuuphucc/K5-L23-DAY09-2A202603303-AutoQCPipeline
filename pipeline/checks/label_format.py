"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    lf = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = lf["overflow_tol"], lf["min_box_px"], lf["max_box_frac"], lf["dup_box_iou"]
    n_classes = len(ds.classes)
    issues = []

    for p in ds.label_files():
        stem = p.stem
        lines = ds.read_label_lines(stem) or []          # (số dòng GỐC, nội dung); dòng trống đã bị bỏ nhưng số dòng không lệch
        size = ds.image_size(stem)                       # None nếu ảnh không có / không mở được -> bỏ qua kiểm px
        kept = []                                        # các dòng hợp lệ đã duyệt: (cls, cx, cy, w, h) — để so DUP_BOX

        for ln, text in lines:
            # 1) cú pháp: không đúng 5 cột số (hoặc nan/inf, id không nguyên)
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng không hợp lệ ({e}): {text.strip()[:60]!r}", line=ln))
                continue

            # 2) id lớp ngoài 0..n-1 (âm cũng sai) -> bỏ dòng, không kiểm hình học
            if not 0 <= cls < n_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_classes - 1}", line=ln, extra={"class_id": cls}))
                continue

            # 3) box rỗng
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"box không có diện tích (w={w}, h={h})", line=ln))
                continue

            # 4) tràn ảnh: mép nào vượt [0,1] nhiều hơn dung sai thì báo, ghi mức tràn lớn nhất
            overflow = max(0.0, -(cx - w / 2), (cx + w / 2) - 1.0, -(cy - h / 2), (cy + h / 2) - 1.0)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}", line=ln, extra={"overflow": round(overflow, 6)}))

            # 5) box lặp: cùng lớp với một dòng TRƯỚC ĐÓ (hợp lệ) và IoU cao; báo ở dòng sau
            cur = (cx, cy, w, h)
            twin = next((k for k in kept if k[0] == cls and iou_xywh(k[1:], cur) > dup_iou), None)
            if twin is not None:
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng box cùng lớp (IoU {iou_xywh(twin[1:], cur):.2f})", line=ln, extra={"iou": round(iou_xywh(twin[1:], cur), 4)}))
            kept.append((cls, *cur))

            # 6) cảnh báo kích thước
            if size:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {min_px}px", line=ln, extra={"short_px": round(short_px, 2)}))
            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.0%} diện tích ảnh", line=ln, extra={"area": round(w * h, 4)}))
    return issues
