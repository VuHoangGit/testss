# Pipeline OCR — prompt 3 tầng, mỗi trang một lượt gọi

Tài liệu mô tả cách backend số hoá tài liệu (`backend/app/services/ocr_service.py`)
và các quyết định kỹ thuật đi kèm. Đọc khi sửa prompt OCR, thêm loại tài liệu mới
hoặc đánh giá chất lượng OCR.

## 1. Kiến trúc lai (hybrid) — không đưa ảnh cho LLM đọc nếu đã có chữ

| Loại trang | Cách xử lý | Số lượt gọi AI |
|---|---|---|
| PDF có lớp text (PDF sinh từ Word, xuất từ hệ thống…) | `pypdfium2` trích thẳng, không gọi AI | 0 |
| PDF scan (trang không có lớp text) | `pypdfium2` render ảnh 200 DPI → model đọc | 1/trang |
| Ảnh chụp / ảnh scan (png/jpeg/webp/gif) | model đọc trực tiếp | 1 |
| Trích xuất trường dữ liệu (cuối mọi lượt OCR) | 1 lượt gọi trên văn bản đã có | 1 |

Lý do: LLM giỏi *hiểu bố cục* nhưng yếu hơn OCR chuyên dụng ở bảng dày đặc,
chữ nhỏ, hoá đơn nhiều cột. Lớp text có sẵn luôn chính xác và miễn phí — chỉ
dùng LLM cho phần nó làm tốt: đọc ảnh scan, dựng bảng, trích dữ liệu.

## 2. Prompt 3 tầng

1. **Tầng 1 — system prompt** (`OCR_SYSTEM_PROMPT`): 10 luật bắt buộc, dùng chung
   cho mọi trang. Quan trọng nhất là luật 2 (giữ nguyên số tiền / ngày tháng /
   số CCCD, không đổi định dạng), luật 3 (không đọc được thì ghi `[?]` /
   `[mất chữ]`) và luật 10 (cấm bịa để lấp chỗ trống). Thiếu ba luật này model
   sẽ tự tin điền số sai — kiểu lỗi nguy hiểm nhất với tài liệu pháp lý/kế toán.
2. **Tầng 2 — user prompt mỗi trang** (`build_page_prompt`): số trang/tổng số,
   loại tài liệu, ngôn ngữ, thuật ngữ riêng (tên công ty, mã sản phẩm) — chỉ để
   nhận đúng chữ, không được thêm vào nội dung.
3. **Tầng 3 — trích xuất có cấu trúc** (`EXTRACTION_PROMPT`): JSON schema **cố
   định**, danh sách khoá nằm trong `STRUCTURED_FIELDS`. Client có thể dựa vào
   khoá này; model không được tự nghĩ khoá mới. Trường không chắc chắn được khai
   vào `truong_khong_chac_chan` thay vì đoán lặng lẽ.

Mọi lượt gọi đều `temperature = 0` — model không được "sáng tạo" số liệu.

## 3. Mỗi trang một lượt gọi

- Biết chính xác lỗi ở trang nào; một trang hỏng chỉ mất trang đó (có cảnh báo),
  không làm hỏng cả tài liệu.
- Tài liệu dài không bị cắt cụt giữa chừng.
- Giới hạn `OCR_MAX_PAGES` (mặc định 20) chặn tài liệu quá dài; phần dư bị bỏ và
  có cảnh báo nêu rõ số trang đã số hoá.
- Ảnh gửi AI: render 200 DPI (`OCR_DPI`), cạnh dài ≤ 2000px, PNG (tự chuyển JPEG
  quality 90 nếu vượt 4MB). Nhỏ hơn 200 DPI mất dấu tiếng Việt và chữ nhỏ; lớn
  hơn 2000px chỉ tốn token.

## 4. Hậu kiểm bằng máy — không tin model tuyệt đối

`post_checks()` chạy sau khi có văn bản + dữ liệu trích xuất, trả danh sách cảnh
báo (tiếng Anh — UI app đang tiếng Anh) cho người dùng đối soát:

- Đếm số chỗ `[?]` / `[mất chữ]` → "check them against the original page".
- Regex ngày tháng, báo ngày không hợp lệ (`45/13/2025`).
- Tổng tiền AI trích không xuất hiện nguyên văn trong nội dung → nghi sai.
- Mã số không giống CCCD (12) / CMND (9) / MST (10 hoặc 13).
- Số tiền dài bất thường.

Cảnh báo hiện ở đầu card kết quả trong tab AI của app. **Chữ do AI đọc vẫn cần
người xác nhận** với tài liệu tiền bạc/pháp lý.

## 5. Hợp đồng API

`POST /api/v1/ai/ocr/{document_id}` (body tuỳ chọn):

```json
{ "doc_type": "hoá đơn", "language": "tiếng Việt", "glossary": "Công ty ABC" }
```

Trả về:

```json
{
  "text": "--- Trang 1 ---\n…",
  "key_values": { "so_hieu": "01/HĐ", "tong_tien": "1250000 VND" },
  "pages": [{ "page": 1, "text": "…", "source": "text-layer" }],
  "data": {
    "loai_tai_lieu": null, "so_hieu": null, "ngay_ban_hanh": null,
    "cac_ben": [], "tong_tien": { "so": null, "don_vi": "VND" },
    "thoi_han": null, "dieu_khoan_chinh": [], "truong_khong_chac_chan": []
  },
  "warnings": ["1 spot(s) marked as unreadable ([?]/[lost text]) — …"]
}
```

`key_values` là dạng phẳng của `data` (giữ tương thích client cũ). Tài liệu 1
trang không chèn mốc `--- Trang N ---` để bản xuất `.docx` sạch.

Credit: một lượt OCR trừ **50 credit** bất kể số trang (đã chặn bằng
`OCR_MAX_PAGES`); AI lỗi toàn bộ thì hoàn credit, lỗi lẻ từng trang thì không.

## 6. Model vision — `deepseek-v4-pro` (đã kiểm chứng)

Gateway thật của dự án là `https://dev-gw.vtvlive.vn` (litellm, tương thích
Anthropic Messages). Kết quả kiểm chứng 05/11/2026 với key trong `backend/.env`:

| Model | Block ảnh | Ghi chú |
|---|---|---|
| `glm-5.3` (model văn bản đang dùng) | ❌ 400 | `messages.content.type is invalid, allowed values: ['text']` |
| `glm-4.6v`, `glm-4.5v`, `glm-4v-plus` | ❌ 403 | key không được cấp quyền các model này |
| **`deepseek-v4-pro`** | ✅ 200 | đọc được trang scan, giữ dấu tiếng Việt, theo đúng luật prompt |

Đo trên 1 PDF thật (2 trang rasterize thành ảnh, không lớp text), so với bản
text-layer gốc: **trang 1 khớp 99,3% · trang 2 khớp 99,6%**, ~15 giây/trang,
trích schema cũng đúng (để null + tự khai `truong_khong_chac_chan`).

⇒ `backend/.env` đã đặt `OCR_VISION_MODEL=deepseek-v4-pro`. Trang scan dùng model
này, mọi tác vụ văn bản (chat/dịch/trích xuất) vẫn dùng `ANTHROPIC_MODEL` cho rẻ.

Nếu key đổi/quyền đổi, lỗi sẽ chỉ đúng nguyên nhân:

> Model 'glm-5.3' cannot read images (text only), so scanned pages cannot be OCR'd.
> Set OCR_VISION_MODEL in .env to a vision-capable model.

Đường nâng cấp dài hạn (chưa làm): cài Tesseract (vie) / PaddleOCR lấy chữ thô +
toạ độ, LLM chỉ dựng bảng và trích Key-Value — chính xác hơn với bảng dày đặc,
hoá đơn nhiều cột, chữ viết tay và rẻ hơn nhiều so với gửi ảnh.

## 7. Giới hạn đã biết

- Vẫn là LLM đọc ảnh: bảng rất dày, chữ viết tay, hoá đơn nhiều cột vẫn có thể
  sai. Muốn chính xác hơn nữa phải cắm OCR engine chuyên dụng (PaddleOCR /
  Tesseract) lấy chữ thô + toạ độ, LLM chỉ dựng cấu trúc.
- Chưa lưu ảnh trang gốc để người dùng bấm đối chiếu (cần lưu file render vào
  storage) — bước tiếp theo nếu cần đối soát trực quan.
- Few-shot theo mẫu tài liệu (đưa 1 trang mẫu vào prompt) chưa làm; đây là cách
  tăng chất lượng rõ nhất với tài liệu cùng mẫu, làm khi có tài liệu thật.
- Chưa chạy thử bộ mẫu khó: bảng dày nhiều cột, hoá đơn, chữ ký tay, bản scan
  mờ/nghiêng. Nên lấy 3–5 trang như vậy chạy thử rồi mới tin tuyệt đối.
- Mỗi trang scan là 1 lượt gọi ~15 giây; tài liệu 20 trang mất vài phút (request
  đồng bộ, chưa có job nền).

## 8. Cách kiểm tra nhanh

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_ocr_service.py -q
```

Test phủ: prompt có đủ luật, mỗi trang một lượt gọi, trang text-layer không gọi
AI, giới hạn số trang, một trang lỗi không làm hỏng cả file, temperature = 0,
schema cố định, hậu kiểm ngày/số tiền/mã số, render PDF thật bằng pypdfium2.

## 9. Xuất Word (`.docx`) — giữ cấu trúc, không phải chữ thô

`POST /api/v1/ai/ocr/{id}/word` trả `.docx` dựng bởi
`backend/app/services/docx_service.py`. Bản cũ chỉ đổ từng dòng thành paragraph
"Normal" nên `##` của model và bảng Markdown hiện ra dưới dạng ký tự thô, file
không có outline level ⇒ mục lục (References → Table of Contents) và Navigation
Pane đều rỗng. Bản mới parse lại khối Markdown rồi ghi bằng style thật của Word:

| Trong văn bản OCR | Trong file .docx |
|---|---|
| `#` … `######` | Heading 1…6 (**có outline level** ⇒ dựng được mục lục) |
| `\| a \| b \|` + `\|---\|---\|` | table thật (Table Grid), hàng đầu đậm + lặp lại khi sang trang, tôn trọng `:---:` |
| `- ` / `* ` / `+ ` | List Bullet (lồng theo thụt đầu dòng) |
| `1. ` / `1) ` | List Number (lồng nhau) |
| `**đậm**`, `*nghiêng*`, `` `code` `` | run có định dạng tương ứng |
| `> trích dẫn` | style Quote |
| `Hình 1.` / `Bảng 2:` | style Caption (Word dựng được Table of Figures) |
| `--- Trang N ---` | ngắt trang (không để mốc chữ thô) |
| `[chữ ký tay]`, `[?]`, `[mất chữ]` | in nghiêng xám để dễ soi lại bản gốc |

Thêm: khổ A4 (thay Letter mặc định), chân trang đánh số trang (field `PAGE`),
`core_properties.title` = tên file gốc, và **mục lục tự động** (field `TOC
\o "1-3"`) đặt ở đầu file khi tài liệu có ≥ 2 tiêu đề. Field được bật cờ
`w:updateFields` (phải đứng trước `w:compat` trong `settings.xml` — sai thứ tự
là Word báo file hỏng) nên Word tính lại mục lục ngay khi mở.

### Trang PDF có lớp text: pdfium + dựng lại đoạn văn

Luồng OCR dùng `ai_service.extract_pdf_pages_markdown` (luồng dịch/tóm tắt vẫn
dùng `extract_pdf_pages` để văn bản gửi model không lẫn dấu Markdown). Ba quyết
định, mỗi cái ứng với một lỗi thấy trên bản xuất Word thật:

**1. Chữ lấy bằng `pypdfium2`, không phải `pypdf`.** `pypdf` tự chèn dấu cách khi
khe hở giữa hai ký tự rộng hơn dấu cách, nên với văn bản căn đều hai bên
(justify) hoặc có kerning nó chèn vào giữa từ: *"video ch ất lượng"*, *"công
đoạ n"*, *"th ời gian"*. pdfium (engine của Chrome) trả đúng chữ.

**2. Dấu cách dựng lại từ toạ độ.** pdfium lại bỏ mất dấu cách ở chỗ PDF đặt nó
bằng dịch con trỏ thay vì vẽ glyph: *"sựphát triển"*, *"dựán"*, *"dữliệu"*. Đo
trên tài liệu thật (cỡ 12) với **hộp rộng** của pdfium (`get_charbox(i,
loose=True)` — hộp tiến glyph, không phải hộp mực):

| Loại khe hở | Khe hở ÷ cỡ chữ |
|---|---|
| giữa hai chữ trong cùng một từ | ≤ 0.041 |
| chỗ pdfium bỏ mất dấu cách | 0.147–0.149 |

⇒ ngưỡng `_WORD_GAP_RATIO = 0.09`, cách đều hai mức. Hộp mực (`loose=False`) cho
0.05–0.23 ngay giữa các chữ trong một từ nên **không** dùng được. Glyph `U+FFFE`
(unicode không có bảng) được đổi thành `-` — PDF dùng nó cho dấu gạch nối:
*"Non￾Linear"* → *"Non-Linear"*.

**3. Mỗi dòng thị giác không phải một đoạn.** Xuất thẳng từng dòng sang Word thì
mỗi dòng thành một paragraph, câu bị chặt giữa chừng. `_lines_to_markdown` gom
lại theo toạ độ:

| Dấu hiệu | Kết luận |
|---|---|
| dòng trước chạm mép phải của cột (chữ tự xuống dòng) | nối vào đoạn đang mở |
| dòng trước hụt mép phải > max(12pt, 2% mép cột) | đoạn mới |
| cách dòng > 1.35 × nhịp dòng thường | đoạn mới |
| dòng bắt đầu bằng `- ` `* ` `• ` `1. ` `\|` `>` | đoạn mới (gạch đầu dòng vẫn nhận dòng nối tiếp) |
| dòng cuối kết thúc bằng `-` | nối liền, giữ gạch nối |
| dòng chỉ có `•` (PDF vẽ dấu bằng lượt chữ riêng) | gắn vào dòng chữ cùng dòng kẻ, cùng cột |

Tiêu đề suy từ **cỡ chữ trang đó** so với cỡ chữ thân của **chính trang đó** —
không phải của cả tài liệu: có trang được vẽ qua phép biến đổi tỉ lệ (CV thiết
kế bằng Canva) nên pdfium báo cỡ 170–440 thay vì 12, lấy cỡ chuẩn toàn tài liệu
thì cả trang thành heading.

| Tỉ lệ so với thân | Cấp |
|---|---|
| ≥ 1.7× | `#` (Heading 1) |
| ≥ 1.3× | `##` (Heading 2) |
| ≥ 1.12× | `###` (Heading 3) |

Dòng dài hơn 200 ký tự không nâng thành tiêu đề (dễ là đoạn văn bị ngắt dòng).
Văn bản **không** có `#` nào thì đoán theo mẫu hành chính VN: `CHƯƠNG/PHẦN …` →
Heading 1, `Điều N …` → Heading 2 (chỉ đoán khi không có marker sẵn).

**Dịch cấp cho có gốc** (`docx_service._promote_heading_levels`): sau khi có
marker, cấp nông nhất luôn được dịch lên `#` (Heading 1). Lý do: model OCR chỉ
ghi `##`/`###`, còn tài liệu một cỡ tiêu đề thì suy ra toàn cấp 2 — giữ nguyên
sẽ làm cả cây outline lùi một cấp và mục lục Word sai thứ bậc. Tương quan giữa
các cấp không đổi. Prompt OCR (`_OCR_RULES` luật 6) cũng yêu cầu model đánh `#`
cho tiêu đề lớn nhất của tài liệu, để phần lớn trường hợp không cần dịch.

Giới hạn đã biết (đo trên Proposal.pdf 10 trang và một CV 2 cột):

- Đoạn vắt qua **chân trang** vẫn thành hai đoạn (xử lý từng trang riêng).
- PDF nhiều cột: thứ tự đọc theo luồng chữ của PDF, có thể đọc hết cột trái rồi
  mới sang cột phải thay vì xen kẽ từng dòng.
- Emoji và glyph không có bảng unicode bị pdfium bỏ (CV mất 📞, ✉️); PDF có mật
  khẩu hoặc pdfium lỗi thì quay về đường `pypdf` cũ (chữ thô, không cấu trúc).
- Tiêu đề cùng cỡ chữ thân nhưng in đậm, hoặc bảng có chữ to, vẫn bị đoán sai cấp.

Test: `tests/test_docx_service.py`, `tests/test_pdf_markdown_extraction.py`.
