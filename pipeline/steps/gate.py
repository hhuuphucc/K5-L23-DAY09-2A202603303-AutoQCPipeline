"""BƯỚC 4 — Cửa chặn: quyết định Release / Hold / Rework.   ★

Test:  pytest tests/test_gate.py -q

Cây quyết định Day 07 (slide Day 09: "Lỗi bắt buộc chặn pipeline; lỗi cảnh báo chuyển người xem"):

  còn ≥ 1 lỗi bắt buộc (severity ERROR)                          -> "Rework"
  không còn lỗi bắt buộc, nhưng tỉ lệ ẢNH còn cảnh báo
      >= cfg["gate"]["warn_ratio_hold"]                          -> "Hold"
  còn lại                                                        -> "Release"

Tỉ lệ cảnh báo = (số ẢNH khác nhau có ≥ 1 cảnh báo) / (tổng số ảnh).  Chú ý:
- chỉ đếm issue có `image` nằm trong `image_stems` (bỏ "<dataset>", "data.yaml");
- bỏ qua ảnh nằm trong `reviewed` (người đã xem, cảnh báo của ảnh đó coi như đã xử lý) — nhưng LỖI BẮT BUỘC thì không bao giờ được bỏ qua;
- mẫu số là số ảnh, không phải số issue.

Trả về dict: decision, n_errors, n_warn_images, n_images, warn_ratio (làm tròn 4 chữ số), reasons (list[str], giải thích bằng tiếng Việt, có số liệu).
"""
from ..common import ERROR, WARN  # noqa: F401


def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    ratio_hold = cfg["gate"]["warn_ratio_hold"]
    n_images = len(stems)

    # lỗi bắt buộc: đếm MỌI issue ERROR (kể cả ảnh đã duyệt, kể cả lỗi cấp dataset như data.yaml)
    n_errors = sum(1 for i in issues if i.severity == ERROR)
    # cảnh báo: chỉ tính ảnh còn trong lô, chưa được người duyệt; mỗi ảnh đếm một lần
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n_warn_images = len(warn_images)
    ratio = round(n_warn_images / n_images, 4) if n_images else 0

    if n_errors:
        decision = "Rework"
        reasons = [f"còn {n_errors} lỗi bắt buộc chưa xử lý: trả về bước sửa/duyệt"]
    elif n_images and n_warn_images / n_images >= ratio_hold:
        decision = "Hold"
        reasons = [f"{n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa được người duyệt, >= ngưỡng {ratio_hold:.0%}: giữ lại để người xem"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, dưới ngưỡng {ratio_hold:.0%}"]
    return dict(decision=decision, n_errors=n_errors, n_warn_images=n_warn_images, n_images=n_images, warn_ratio=ratio, reasons=reasons)
