"""Test pipeline OCR: prompt 3 tầng, mỗi trang 1 lượt gọi, hậu kiểm, schema cố định."""

import io

import pytest

from app.services import ai_service, ocr_service


@pytest.fixture()
def no_structured_ai(monkeypatch):
    """Chặn lượt gọi trích xuất để test chỉ đếm lượt OCR trang."""

    def fake_extract(text: str):
        return ocr_service.empty_structured(), []

    monkeypatch.setattr(ocr_service, "extract_structured", fake_extract)


# ---------------------------------------------------------------------------
# Tầng 1 + 2 — prompt


def test_system_prompt_contains_mandatory_rules():
    prompt = ocr_service.OCR_SYSTEM_PROMPT
    # Những luật quyết định chất lượng: không đổi số liệu, đánh dấu chỗ mù, cấm bịa
    assert "31/12/2025" in prompt
    assert "[?]" in prompt
    assert "[mất chữ]" in prompt
    assert "TUYỆT ĐỐI không bịa" in prompt
    assert "Markdown table" in prompt
    assert "chữ ký tay" in prompt
    assert "10. " in prompt  # đủ 10 luật


def test_page_prompt_includes_position_and_glossary():
    prompt = ocr_service.build_page_prompt(
        2,
        7,
        ocr_service.OcrOptions(doc_type="hợp đồng", glossary="Công ty TNHH ABC"),
    )
    assert "Trang 2/7" in prompt
    assert "hợp đồng" in prompt
    assert "Công ty TNHH ABC" in prompt
    assert "không được thêm vào nội dung" in prompt


def test_page_prompt_without_glossary_has_no_glossary_line():
    prompt = ocr_service.build_page_prompt(1, 1, ocr_service.OcrOptions())
    assert "Thuật ngữ riêng" not in prompt
    assert "Trang 1/1" in prompt


def test_vision_call_uses_system_prompt_and_temperature_zero(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "Nội dung trang"}]}

    monkeypatch.setattr(ai_service, "post_anthropic", fake_post)

    text = ocr_service._read_page_with_vision(b"png-bytes", "image/png", "prompt")

    assert text == "Nội dung trang"
    assert captured["temperature"] == 0
    assert captured["system"] == ocr_service.OCR_SYSTEM_PROMPT
    content = captured["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"


# ---------------------------------------------------------------------------
# Luồng trang PDF


def test_pdf_text_layer_pages_skip_ai(monkeypatch, no_structured_ai):
    """Trang có lớp text dùng luôn; chỉ trang scan mới gửi AI."""
    monkeypatch.setattr(
        ai_service, "extract_pdf_pages_markdown", lambda data: ["Trang 1 có chữ", ""]
    )
    monkeypatch.setattr(
        ocr_service, "_render_pdf_pages", lambda data, indexes, dpi: {1: (b"png", "image/png")}
    )
    vision_calls: list[str] = []

    def fake_vision(png, media_type, prompt):
        vision_calls.append(prompt)
        return "Trang 2 đọc từ ảnh"

    monkeypatch.setattr(ocr_service, "_read_page_with_vision", fake_vision)

    outcome = ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")

    assert [page.source for page in outcome.pages] == ["text-layer", "vision"]
    assert [page.text for page in outcome.pages] == ["Trang 1 có chữ", "Trang 2 đọc từ ảnh"]
    assert len(vision_calls) == 1
    assert "Trang 2/2" in vision_calls[0]
    # Nhiều trang → chèn mốc trang trong văn bản gộp
    assert "--- Trang 1 ---" in outcome.text
    assert "--- Trang 2 ---" in outcome.text


def test_pdf_pages_are_capped_by_max_pages(monkeypatch, no_structured_ai):
    monkeypatch.setattr(
        ai_service, "extract_pdf_pages_markdown", lambda data: [f"trang {i}" for i in range(1, 6)]
    )
    options = ocr_service.OcrOptions(max_pages=2)

    outcome = ocr_service.ocr_document_bytes(b"%PDF", "application/pdf", options=options)

    assert len(outcome.pages) == 2
    assert any("only the first 2 were processed" in warning for warning in outcome.warnings)


def test_failed_page_does_not_break_whole_document(monkeypatch, no_structured_ai):
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: ["", ""])
    monkeypatch.setattr(
        ocr_service,
        "_render_pdf_pages",
        lambda data, indexes, dpi: {0: (b"png", "image/png"), 1: (b"png", "image/png")},
    )

    def fake_vision(png, media_type, prompt):
        if "Trang 1/2" in prompt:
            raise ai_service.AIServiceError("model quá tải")
        return "Trang 2 ok"

    monkeypatch.setattr(ocr_service, "_read_page_with_vision", fake_vision)

    outcome = ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")

    assert outcome.pages[0].text == ocr_service.EMPTY_PAGE_MARKER
    assert outcome.pages[1].text == "Trang 2 ok"
    assert any("Page 1: could not be read" in warning for warning in outcome.warnings)


def test_blank_document_skips_structured_extraction(monkeypatch):
    """Không có chữ nào → không tốn thêm 1 lượt gọi AI để trích trường."""
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: [""])
    monkeypatch.setattr(
        ocr_service,
        "_render_pdf_pages",
        lambda data, indexes, dpi: {0: (b"png", "image/png")},
    )
    monkeypatch.setattr(
        ocr_service,
        "_read_page_with_vision",
        lambda png, media_type, prompt: ocr_service.EMPTY_PAGE_MARKER,
    )
    calls: list[str] = []
    monkeypatch.setattr(
        ocr_service, "extract_structured", lambda text: calls.append(text) or ({}, [])
    )

    outcome = ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")

    assert calls == []
    assert outcome.structured == ocr_service.empty_structured()
    assert any("No readable text was found" in warning for warning in outcome.warnings)


def test_all_pages_failing_raises_ai_error(monkeypatch, no_structured_ai):
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: ["", ""])
    monkeypatch.setattr(
        ocr_service,
        "_render_pdf_pages",
        lambda data, indexes, dpi: {0: (b"png", "image/png"), 1: (b"png", "image/png")},
    )

    def fake_vision(png, media_type, prompt):
        raise ai_service.AIServiceError("hỏng")

    monkeypatch.setattr(ocr_service, "_read_page_with_vision", fake_vision)

    with pytest.raises(ai_service.AIServiceError):
        ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")


def test_render_failure_is_reported_as_warning(monkeypatch, no_structured_ai):
    """Trang render lỗi chỉ mất trang đó; trang còn lại vẫn OCR bình thường."""
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: ["", ""])
    # Chỉ dựng được trang 1 → trang 2 thiếu ảnh
    monkeypatch.setattr(
        ocr_service,
        "_render_pdf_pages",
        lambda data, indexes, dpi: {0: (b"png", "image/png")},
    )
    monkeypatch.setattr(
        ocr_service, "_read_page_with_vision", lambda png, media_type, prompt: "Trang 1 ok"
    )

    outcome = ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")

    assert outcome.pages[0].text == "Trang 1 ok"
    assert outcome.pages[1].text == ocr_service.EMPTY_PAGE_MARKER
    assert any("Page 2: could not render an image" in warning for warning in outcome.warnings)


def test_render_library_error_is_reported(monkeypatch, no_structured_ai):
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: ["", ""])
    monkeypatch.setattr(
        ocr_service,
        "_render_pdf_pages",
        lambda data, indexes, dpi: (_ for _ in ()).throw(
            ai_service.AIServiceError("pdfium lỗi")
        ),
    )

    with pytest.raises(ai_service.AIServiceError):
        ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")


def test_image_document_is_one_vision_page(monkeypatch, no_structured_ai):
    captured: list[str] = []

    def fake_vision(png, media_type, prompt):
        captured.append(media_type)
        return "Nội dung ảnh"

    monkeypatch.setattr(ocr_service, "_read_page_with_vision", fake_vision)

    outcome = ocr_service.ocr_document_bytes(b"\x89PNG", "image/jpg")

    assert captured == ["image/jpeg"]  # chuẩn hoá image/jpg → image/jpeg
    assert len(outcome.pages) == 1
    assert outcome.pages[0].text == "Nội dung ảnh"
    # 1 trang → không chèn mốc trang, bản xuất Word sạch
    assert outcome.text == "Nội dung ảnh"


def test_unsupported_mime_type_raises_friendly_error():
    with pytest.raises(ai_service.AIServiceError) as error:
        ocr_service.ocr_document_bytes(b"data", "application/msword", "hop-dong.doc")
    assert "Supported: PDF and images" in str(error.value)


def test_render_pdf_pages_outputs_png():
    """Render thật bằng pypdfium2 — bắt lỗi thiếu thư viện/đường dẫn API."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)  # A4
    buffer = io.BytesIO()
    writer.write(buffer)

    rendered = ocr_service._render_pdf_pages(buffer.getvalue(), [0], 200)

    data, media_type = rendered[0]
    assert media_type == "image/png"
    assert data.startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# Tầng 3 — trích xuất có cấu trúc


def test_structured_extraction_fills_fixed_schema(monkeypatch):
    raw = """```json
    {"so_hieu": "01/HĐ-2025", "ngay_ban_hanh": "31/12/2025",
     "cac_ben": [{"vai_tro": "Bên A", "ten": "Cty ABC", "ma_so": 101234567}],
     "tong_tien": {"so": 1250000, "don_vi": "VND"},
     "dieu_khoan_chinh": ["Điều 1", "Điều 2"],
     "khoa_la": "bỏ đi"}
    ```"""
    monkeypatch.setattr(ai_service, "request_anthropic", lambda *a, **k: raw)

    structured, warnings = ocr_service.extract_structured("Nội dung hợp đồng")

    assert set(structured) == set(ocr_service.STRUCTURED_FIELDS)  # khoá cố định
    assert structured["so_hieu"] == "01/HĐ-2025"
    assert structured["ngay_ban_hanh"] == "31/12/2025"
    assert structured["cac_ben"][0]["ma_so"] == "101234567"
    assert structured["tong_tien"] == {"so": "1250000", "don_vi": "VND"}
    assert structured["dieu_khoan_chinh"] == ["Điều 1", "Điều 2"]
    assert "khoa_la" not in structured
    assert warnings == []


def test_structured_extraction_reports_uncertain_fields(monkeypatch):
    monkeypatch.setattr(
        ai_service,
        "request_anthropic",
        lambda *a, **k: '{"truong_khong_chac_chan": ["tong_tien", "ngay_ban_hanh"]}',
    )

    _, warnings = ocr_service.extract_structured("Nội dung")

    assert warnings == [
        "The AI is unsure about: tong_tien",
        "The AI is unsure about: ngay_ban_hanh",
    ]


def test_structured_extraction_invalid_json_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(ai_service, "request_anthropic", lambda *a, **k: "Xin lỗi, tôi không rõ.")

    structured, warnings = ocr_service.extract_structured("Nội dung")

    assert structured == ocr_service.empty_structured()
    assert any("not valid JSON" in warning for warning in warnings)


def test_structured_extraction_uses_temperature_zero(monkeypatch):
    captured: dict[str, object] = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "{}"}]}

    monkeypatch.setattr(ai_service, "post_anthropic", fake_post)
    ocr_service.extract_structured("Nội dung")

    assert captured["temperature"] == 0


# ---------------------------------------------------------------------------
# Hậu kiểm


def test_post_checks_flags_unreadable_markers():
    text = "Số hợp đồng: [?]\nNgày: 01/02/2025\nĐoạn sau [mất chữ]."

    warnings = ocr_service.post_checks(text, ocr_service.empty_structured())

    assert any("2 spot(s) marked as unreadable" in warning for warning in warnings)


def test_post_checks_flags_invalid_date():
    text = "Ngày ký: 45/13/2025"

    warnings = ocr_service.post_checks(text, ocr_service.empty_structured())

    assert any("Suspicious date format" in warning for warning in warnings)


def test_post_checks_flags_total_not_present_in_text():
    text = "Tổng cộng: 1.250.000 VND"
    structured = ocr_service.empty_structured()
    structured["tong_tien"] = {"so": "999000", "don_vi": "VND"}

    warnings = ocr_service.post_checks(text, structured)

    assert any("does not appear verbatim" in warning for warning in warnings)


def test_post_checks_accepts_total_present_in_text():
    text = "Thành tiền: 1.250.000 VND"
    structured = ocr_service.empty_structured()
    structured["tong_tien"] = {"so": "1250000", "don_vi": "VND"}

    warnings = ocr_service.post_checks(text, structured)

    assert not any("does not appear verbatim" in warning for warning in warnings)


def test_post_checks_flags_odd_tax_id_length():
    structured = ocr_service.empty_structured()
    structured["cac_ben"] = [{"vai_tro": "Bên A", "ten": "Cty ABC", "ma_so": "12345"}]

    warnings = ocr_service.post_checks("Bên A: Cty ABC, MST 12345", structured)

    assert any("does not look like a national ID" in warning for warning in warnings)


def test_post_checks_clean_document_has_no_warning():
    text = "Số hợp đồng: 01/HĐ\nNgày: 31/12/2025\nTổng: 1.250.000 VND"
    structured = ocr_service.empty_structured()
    structured["tong_tien"] = {"so": "1250000", "don_vi": "VND"}

    assert ocr_service.post_checks(text, structured) == []
