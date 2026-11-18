"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}       # sửa = xoá dòng
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}                                          # sửa = cắt box về trong ảnh
REMOVE_IMAGE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
MIN_SIDE = 1e-6                                                            # box sau khi cắt nhỏ hơn mức này = không còn diện tích


def _num(v):
    """Ghi số gọn: 6 chữ số thập phân, bỏ số 0 thừa ('0.925000' -> '0.925')."""
    t = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def _clip(cls, cx, cy, w, h):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box nằm hẳn ngoài ảnh (không còn diện tích)."""
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= MIN_SIDE or nh <= MIN_SIDE:
        return None
    return f"{cls} {_num((x1 + x2) / 2)} {_num((y1 + y2) / 2)} {_num(nw)} {_num(nh)}"


def _fix_rec(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def fix(ds, issues, cfg):
    fixes = []
    errors = [i for i in issues if i.severity == ERROR]          # cảnh báo là việc của người: không đụng

    # ---- 1) xoá ảnh (+ nhãn) trước, để mọi issue còn lại của ảnh đó bị bỏ qua êm
    removed = set()
    for i in errors:
        if i.code in REMOVE_IMAGE_CODES and i.image not in removed:
            removed.add(i.image)
            img = ds.image_path(i.image)
            before = img.name if img else "(ảnh không còn)"
            if img:
                img.unlink()
            lab = ds.label_path(i.image)
            if lab.exists():
                lab.unlink()
            ds._size_cache.pop(i.image, None)
            fixes.append(_fix_rec(i.image, None, "remove_image", before, f"đã xoá ảnh + nhãn ({i.code})"))

    # ---- 2) tên lớp trong data.yaml: ghi lại đúng danh sách của dự án (một lần dù có nhiều issue)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        old = ds.yaml_names()
        data = {}
        if ds.yaml_path.exists():
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
        data["names"] = {k: n for k, n in enumerate(cfg["classes"])}
        ds.yaml_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        fixes.append(_fix_rec("data.yaml", None, "rename_classes", str([old[k] for k in sorted(old)]), str(list(cfg["classes"]))))

    # ---- 3) ảnh chưa có nhãn: máy không bịa nhãn (cũng không tạo file rỗng) -> chuyển người gán
    seen_missing = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen_missing:
            seen_missing.add(i.image)
            fixes.append(_fix_rec(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # ---- 4) lỗi theo dòng: gom theo file, quyết định cho từng dòng GỐC, rồi ghi lại MỘT lần
    per_file = defaultdict(lambda: defaultdict(set))             # stem -> số dòng gốc -> {mã lỗi}
    for i in errors:
        if (i.code in DROP_CODES or i.code in CLIP_CODES) and i.line is not None and i.image not in removed:
            per_file[i.image][i.line].add(i.code)

    for stem in sorted(per_file):
        path = ds.label_path(stem)
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        out, changed = [], False
        for n, text in enumerate(raw, 1):                        # n = số dòng gốc (dòng trống vẫn đếm)
            codes = per_file[stem].get(n)
            if not codes or not text.strip():
                out.append(text)
                continue
            if codes & DROP_CODES:                               # có lỗi phải xoá thì xoá, không cắt thêm
                fixes.append(_fix_rec(stem, n, "drop_line", text.strip(), "(xoá dòng)"))
                changed = True
                continue
            try:
                new = _clip(*parse_yolo_line(text))
            except ValueError:                                   # dòng hỏng mà không có issue tương ứng: để nguyên
                out.append(text)
                continue
            if new is None:
                fixes.append(_fix_rec(stem, n, "drop_line", text.strip(), "(xoá dòng: box nằm hẳn ngoài ảnh)"))
            else:
                fixes.append(_fix_rec(stem, n, "clip_box", text.strip(), new))
                out.append(new)
            changed = True
        if changed:
            body = chr(10).join(out) + chr(10) if out else ""
            path.write_bytes(body.encode("utf-8"))
    return fixes
