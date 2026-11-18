# Giải thích chi tiết mã nguồn 4 Module AutoQC Pipeline (Day 09)

Tài liệu này giải thích cặn kẽ từng dòng, từng khối lệnh và logic xử lý của 4 module cốt lõi do sinh viên triển khai, phục vụ việc ôn tập và bảo vệ bài lab theo yêu cầu của [RULES.md](../RULES.md).

---

## 1. Module `pipeline/checks/label_format.py` (Kiểm tra cú pháp dòng nhãn YOLO)

File này duyệt qua từng dòng trong file `.txt` của mỗi ảnh để kiểm tra 6 loại bất thường cú pháp và hình học:

### 1. Đọc cấu hình và khởi tạo (Dòng 27–32)
```python
def run(ds, cfg):
    lf = cfg["label_format"]
    tol, min_px, max_frac, dup_iou = lf["overflow_tol"], lf["min_box_px"], lf["max_box_frac"], lf["dup_box_iou"]
    n_classes = len(ds.classes)
    issues = []
```
- **Ý nghĩa**: Lấy các ngưỡng cấu hình từ `configs/pipeline.yaml` thay vì viết cứng giá trị:
  - `overflow_tol`: Dung sai cho phép khi mép box tràn ra ngoài mép ảnh ($0.002$).
  - `min_box_px`: Cạnh ngắn tối thiểu của box tính theo pixel ($12\text{px}$).
  - `max_box_frac`: Tỉ lệ diện tích tối đa so với ảnh ($0.95$).
  - `dup_box_iou`: Ngưỡng IoU để coi hai box cùng lớp là trùng nhau ($0.9$).
  - `n_classes`: Số lượng lớp của dự án ($4$ lớp: car, person, truck, bus).

### 2. Duyệt từng file nhãn và bảo toàn số dòng gốc (Dòng 33–37)
```python
    for p in ds.label_files():
        stem = p.stem
        lines = ds.read_label_lines(stem) or []
        size = ds.image_size(stem)
        kept = []
```
- `lines`: Trả về danh sách `(số dòng gốc, nội dung)`. Kể cả khi file có dòng trống ở giữa, số dòng gốc vẫn không bị lệch.
- `size`: Lấy `(rộng, cao)` pixel của ảnh để phục vụ việc kiểm tra kích thước pixel. Nếu ảnh hỏng hoặc không có ảnh, hàm trả về `None` để tránh lỗi khi nhân toạ độ.
- `kept`: Danh sách lưu các box hợp lệ trước đó để đối chiếu trùng lặp `DUP_BOX`.

### 3. Kiểm tra lỗi cú pháp `BAD_FORMAT` (Dòng 41–45)
```python
        for ln, text in lines:
            try:
                cls, cx, cy, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue("label_format", ERROR, "BAD_FORMAT", stem, f"dòng không hợp lệ ({e}): {text.strip()[:60]!r}", line=ln))
                continue
```
- **Ý nghĩa**: Gọi hàm `parse_yolo_line` để kiểm tra xem dòng có đúng 5 cột số thực không, có chứa `nan`/`inf` hay ID lớp không phải số nguyên hay không.
- Sử dụng `try/except` để bắt `ValueError`. Khi gặp lỗi, lệnh `continue` lập tức bỏ qua dòng này, không thực hiện tiếp các bước kiểm tra hình học phía sau để tránh crash script.

### 4. Kiểm tra ID lớp lạ `BAD_CLASS_ID` (Dòng 48–50)
```python
            if not 0 <= cls < n_classes:
                issues.append(Issue("label_format", ERROR, "BAD_CLASS_ID", stem, f"id lớp {cls} ngoài 0..{n_classes - 1}", line=ln, extra={"class_id": cls}))
                continue
```
- Dự án chỉ có 4 lớp ($0..3$). Bất kỳ ID nào $< 0$ hoặc $\ge 4$ (ví dụ: lớp $93$, lớp $-1$) đều bị coi là lỗi bắt buộc (`ERROR`).

### 5. Kiểm tra box rỗng `BOX_ZERO` (Dòng 53–55)
```python
            if w <= 0 or h <= 0:
                issues.append(Issue("label_format", ERROR, "BOX_ZERO", stem, f"box không có diện tích (w={w}, h={h})", line=ln))
                continue
```
- Box có chiều rộng hoặc chiều cao $\le 0$ thì không có diện tích $\rightarrow$ báo lỗi `ERROR`.

### 6. Kiểm tra tràn ảnh `BOX_OUT_OF_IMAGE` (Dòng 58–60)
```python
            overflow = max(0.0, -(cx - w / 2), (cx + w / 2) - 1.0, -(cy - h / 2), (cy + h / 2) - 1.0)
            if overflow > tol:
                issues.append(Issue("label_format", ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}", line=ln, extra={"overflow": round(overflow, 6)}))
```
- Toạ độ 4 mép box:
  - Mép trái: $cx - w/2$ (nếu $< 0$ thì mức tràn là $-(cx - w/2)$).
  - Mép phải: $cx + w/2$ (nếu $> 1$ thì mức tràn là $(cx + w/2) - 1$).
  - Mép trên: $cy - h/2$ và mép dưới: $cy + h/2$.
- Lấy giá trị tràn lớn nhất qua hàm `max(...)`. Nếu mức tràn vượt quá dung sai `tol` ($0.002$) thì báo lỗi `ERROR`.

### 7. Kiểm tra trùng lặp box `DUP_BOX` (Dòng 63–67)
```python
            cur = (cx, cy, w, h)
            twin = next((k for k in kept if k[0] == cls and iou_xywh(k[1:], cur) > dup_iou), None)
            if twin is not None:
                issues.append(Issue("label_format", ERROR, "DUP_BOX", stem, f"trùng box cùng lớp (IoU {iou_xywh(twin[1:], cur):.2f})", line=ln, extra={"iou": round(iou_xywh(twin[1:], cur), 4)}))
            kept.append((cls, *cur))
```
- So khớp box hiện tại với các box hợp lệ đã duyệt trước đó trong cùng file: Nếu cùng class và có $\text{IoU} > 0.9$ thì báo lỗi `DUP_BOX` tại **dòng sau** (để giữ lại dòng trước và xoá dòng sau khi autofix).

### 8. Cảnh báo box quá nhỏ / quá lớn (Dòng 70–75)
```python
            if size:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_px:
                    issues.append(Issue("label_format", WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {min_px}px", line=ln, extra={"short_px": round(short_px, 2)}))
            if w * h > max_frac:
                issues.append(Issue("label_format", WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.0%} diện tích ảnh", line=ln, extra={"area": round(w * h, 4)}))
```
- `BOX_TINY`: Cạnh ngắn tính bằng pixel $< 12\text{px}$.
- `BOX_HUGE`: Diện tích chiếm trên $95\%$ khung hình.
- Cả hai đều mang mức độ `WARN` (cảnh báo để người kiểm tra, không tự ý xoá vì có thể là vật thể ở xa hoặc chụp cận cảnh).

---

## 2. Module `pipeline/steps/gate.py` (Cửa chặn Release / Hold / Rework)

Module này quyết định trạng thái phát hành của bộ dữ liệu:

```python
def decide(issues, image_stems, cfg, reviewed=frozenset()):
    stems = set(image_stems)
    reviewed = set(reviewed)
    ratio_hold = cfg["gate"]["warn_ratio_hold"]
    n_images = len(stems)

    # 1. Đếm tất cả lỗi bắt buộc (ERROR)
    n_errors = sum(1 for i in issues if i.severity == ERROR)

    # 2. Đếm số lượng ảnh còn cảnh báo (WARN) chưa được người duyệt
    warn_images = {i.image for i in issues if i.severity == WARN and i.image in stems and i.image not in reviewed}
    n_warn_images = len(warn_images)
    ratio = round(n_warn_images / n_images, 4) if n_images else 0
```
- **Quy tắc 1**: Lỗi `ERROR` tính trên toàn bộ tập lỗi, **kể cả ảnh đã được duyệt trong `reviewed`** (người duyệt không thể biến một lỗi cú pháp hay ảnh hỏng thành hợp lệ).
- **Quy tắc 2**: Cảnh báo `WARN` được tính theo **đầu ảnh** (mỗi ảnh chỉ tính một lần bất kể số lượng cảnh báo). Bỏ qua những ảnh nằm trong tập `reviewed`.

### Cây quyết định:
```python
    if n_errors:
        decision = "Rework"
        reasons = [f"còn {n_errors} lỗi bắt buộc chưa xử lý: trả về bước sửa/duyệt"]
    elif n_images and n_warn_images / n_images >= ratio_hold:
        decision = "Hold"
        reasons = [f"{n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo chưa được người duyệt, >= ngưỡng {ratio_hold:.0%}: giữ lại để người xem"]
    else:
        decision = "Release"
        reasons = [f"không còn lỗi bắt buộc; {n_warn_images}/{n_images} ảnh ({ratio:.1%}) còn cảnh báo, dưới ngưỡng {ratio_hold:.0%}"]
```
1. **Rework** (mã thoát 20): Còn $\ge 1$ lỗi bắt buộc. Dataset **không được phép xuất**.
2. **Hold** (mã thoát 10): Không còn lỗi bắt buộc, nhưng tỉ lệ ảnh còn cảnh báo $\ge 10\%$. Dataset được xuất ra dưới dạng **bản nháp** để thử nghiệm.
3. **Release** (mã thoát 0): Hết lỗi bắt buộc và tỉ lệ ảnh còn cảnh báo $< 10\%$.

---

## 3. Module `pipeline/steps/autofix.py` (Tự động sửa lỗi an toàn)

Module này sửa trực tiếp trên bản sao làm việc `work/run/ds/` và ghi nhật ký vào `03_fixes.csv`:

### 1. Phân loại mã lỗi
```python
DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_IMAGE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
```

### 2. Hàm cắt mép box `_clip`
```python
def _clip(cls, cx, cy, w, h):
    x1, x2 = max(0.0, cx - w / 2), min(1.0, cx + w / 2)
    y1, y2 = max(0.0, cy - h / 2), min(1.0, cy + h / 2)
    nw, nh = x2 - x1, y2 - y1
    if nw <= MIN_SIDE or nh <= MIN_SIDE:
        return None
    return f"{cls} {_num((x1 + x2) / 2)} {_num((y1 + y2) / 2)} {_num(nw)} {_num(nh)}"
```
- Cắt các toạ độ vượt biên về khoảng $[0, 1]$.
- Nếu box nằm hẳn ngoài ảnh (sau khi cắt diện tích $\le 0$) $\rightarrow$ trả về `None` để xoá dòng thay vì lưu box rỗng.

### 3. Các hành động sửa:
- **`remove_image`**: Xoá cả ảnh và file nhãn bằng `unlink()`. Ưu tiên thực hiện đầu tiên để các lỗi theo dòng của ảnh đó ở sau được bỏ qua êm thuận.
- **`rename_classes`**: Ghi đè key `names` trong file `data.yaml` cho chuẩn 4 lớp của dự án.
- **`needs_label`**: Với ảnh thiếu file nhãn (`MISSING_LABEL_FILE`), máy **không được tạo file nhãn rỗng** (vì rỗng là ảnh nền), chỉ ghi log chuyển người duyệt.
- **`drop_line` & `clip_box`**: Gom lỗi theo `per_file[stem][line_no]`. Đọc file và sửa theo số dòng gốc một lần duy nhất, tránh làm lệch số dòng khi xoá nhiều dòng trong cùng một file.

---

## 4. Module `pipeline/checks/second_opinion.py` (Ý kiến thứ hai từ model YOLO26L)

So sánh nhãn hiện tại với dự đoán từ model mạnh hơn để phát hiện lỗi ngữ nghĩa:

### 1. Lọc dự đoán của model
- Lọc các dự đoán có độ tin cậy $\ge \text{conf}$ (đã calibrate là $0.6$) và diện tích pixel $\ge 600\text{px}^2$.

### 2. So khớp dự đoán với nhãn:
- Tìm các box nhãn có $\text{IoU} \ge 0.3$ (`iou_missing`) với box của model:
  1. **`POSSIBLE_MISSING`**: Model thấy vật với độ tin cậy cao mà nhãn không có bất kỳ box nào.
  2. **`POSSIBLE_LOOSE_BOX`**: Nhãn có đúng lớp đó nhưng $\text{IoU} < 0.5$ (`iou_loose`) $\rightarrow$ box bị vẽ lệch hoặc quá rộng/hẹp.
  3. **`POSSIBLE_WRONG_CLASS`**: Không có nhãn cùng lớp, nhưng lại có nhãn khác lớp có $\text{IoU} \ge 0.5$ (`iou_match`) $\rightarrow$ cùng vị trí nhưng gán sai tên lớp (ví dụ: xe tải gán thành bus).

### 3. Kiểm tra thừa nhãn (`POSSIBLE_FALSE_POS`)
- Đối chiếu ngược từ nhãn về model: Nếu có một box trong nhãn mà không khớp với bất kỳ dự đoán nào của model (ngưỡng `fp_conf = 0.1`) $\rightarrow$ cảnh báo nghi ngờ box vẽ thừa trên nền trống.
