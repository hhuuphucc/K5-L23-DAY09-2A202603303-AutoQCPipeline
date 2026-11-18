"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


def _name(ds, c):
    return ds.classes[c] if 0 <= c < len(ds.classes) else str(c)


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]
    conf_t, min_area, fp_conf = so["conf"], so["min_area_px"], so["fp_conf"]
    iou_missing, iou_match, iou_loose = so["iou_missing"], so["iou_match"], so["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []

    for p in ds.image_files():
        stem = p.stem
        rows = preds.get(stem)
        lines = ds.read_label_lines(stem)
        if rows is None or lines is None:            # model chưa nhìn ảnh này / ảnh chưa có file nhãn (check khác báo): bỏ qua
            continue
        size = ds.image_size(stem)
        if not size:                                 # ảnh hỏng: không tính được diện tích px
            continue
        W, H = size
        labels = ds.valid_boxes(stem)                # (cls, cx, cy, w, h) — dòng hỏng đã bị bỏ

        # ---- A) từ phía model: vật model tin chắc mà nhãn không phủ đúng
        for r in rows:
            cls, conf, cx, cy, w, h = r
            cls = int(cls)
            if conf < conf_t or (w * W) * (h * H) < min_area:
                continue
            box = (cx, cy, w, h)
            cands = [(iou_xywh(box, l[1:]), l[0]) for l in labels]
            cands = [(v, c) for v, c in cands if v >= iou_missing]
            if not cands:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {_name(ds, cls)} (conf {conf:.2f}) mà nhãn không có box", extra={"conf": conf, "class": cls}))
                continue
            same = [v for v, c in cands if c == cls]
            if same:
                best = max(same)
                if best < iou_loose:
                    issues.append(Issue("second_opinion", WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"box {_name(ds, cls)} lỏng/lệch so với model (IoU {best:.2f}, conf {conf:.2f})", extra={"conf": conf, "iou": round(best, 4), "class": cls}))
                continue                              # nhãn đúng lớp đã phủ vật này: không cờ
            other = max(cands, key=lambda t: t[0])    # chỉ còn nhãn KHÁC lớp
            if other[0] >= iou_match:
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"nhãn {_name(ds, other[1])} nhưng model thấy {_name(ds, cls)} (IoU {other[0]:.2f}, conf {conf:.2f})",
                                    extra={"conf": conf, "iou": round(other[0], 4), "label_class": other[1], "model_class": cls}))
            # IoU trong [iou_missing, iou_match) với lớp khác: mơ hồ, không cờ

        # ---- B) từ phía nhãn: box nhãn không khớp vật nào model thấy (không lọc diện tích)
        ref = [tuple(r[2:6]) for r in rows if r[1] >= fp_conf]
        for ln, text in lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError:
                continue
            if not 0 <= cls < len(ds.classes):
                continue
            if all(iou_xywh((cx, cy, w, h), b) < iou_missing for b in ref):
                issues.append(Issue("second_opinion", WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box {_name(ds, cls)} ở dòng {ln} không khớp vật nào model thấy", line=ln, extra={"class": cls}))
    return issues
