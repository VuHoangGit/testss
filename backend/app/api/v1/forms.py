"""API danh sách và xử lý biểu mẫu có logo."""

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from app.api.deps import CurrentUser
from app.api.v1.ai import _attachment_header
from app.core.config import get_settings
from app.services import form_service

router = APIRouter(prefix="/forms", tags=["forms"])


@router.get("/templates")
def list_templates(current: CurrentUser) -> list[dict[str, object]]:
    del current
    return form_service.list_templates(get_settings().form_templates_dir)


@router.get("/templates/{template_name}/preview")
def preview_template(current: CurrentUser, template_name: str) -> Response:
    del current
    try:
        preview = form_service.create_template_preview(
            get_settings().form_templates_dir,
            template_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=preview,
        media_type="application/pdf",
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/templates/{template_name}/page-image")
def page_image(
    current: CurrentUser,
    template_name: str,
    page: int = 0,
) -> Response:
    """Render 1 trang biểu mẫu thành PNG để làm nền kéo thả logo (WYSIWYG)."""
    del current
    if page < 0:
        raise HTTPException(status_code=422, detail="Số trang không hợp lệ")
    try:
        png, page_count, page_width, page_height = form_service.render_page_png(
            get_settings().form_templates_dir,
            template_name,
            page_number=page,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "X-Page-Count": str(page_count),
            "X-Page-Width-Pt": f"{page_width:.2f}",
            "X-Page-Height-Pt": f"{page_height:.2f}",
            "Access-Control-Expose-Headers": "X-Page-Count, X-Page-Width-Pt, X-Page-Height-Pt",
        },
    )


@router.get("/preview-document")
def preview_document(
    current: CurrentUser,
    template_name: str,
    page: int = 0,
) -> Response:
    """Return the first document page as a PNG background for positioning."""
    return page_image(
        current=current,
        template_name=template_name,
        page=page,
    )


@router.post("/process")
async def process_form(
    current: CurrentUser,
    logos: Annotated[list[UploadFile] | None, File()] = None,
    logo: Annotated[UploadFile | None, File()] = None,
    logo_placements: Annotated[str | None, Form()] = None,
    template_names: Annotated[list[str] | None, Form()] = None,
    template_name: str | None = None,
    x: Annotated[float, Form(ge=0.0, le=1.0)] = 0.82,
    y: Annotated[float, Form(ge=0.0, le=1.0)] = 0.04,
    is_watermark: Annotated[bool, Form()] = False,
    password: Annotated[str | None, Form()] = None,
) -> Response:
    del current
    uploaded_logos = logos or ([logo] if logo is not None else [])
    if not uploaded_logos:
        raise HTTPException(status_code=422, detail="Cần ít nhất một logo")
    for uploaded_logo in uploaded_logos:
        if uploaded_logo.content_type not in {"image/png", "image/jpeg"}:
            raise HTTPException(status_code=415, detail="Logo chỉ hỗ trợ PNG hoặc JPEG")

    try:
        logo_payloads: list[bytes] = []
        for uploaded_logo in uploaded_logos:
            logo_payloads.append(await uploaded_logo.read())

        placements: list[dict[str, object]] = []
        if logo_placements:
            try:
                placements = json.loads(logo_placements)
            except json.JSONDecodeError as exc:
                raise ValueError("logo_placements không hợp lệ") from exc
        if placements and len(placements) != len(logo_payloads):
            raise ValueError("Số logo và số vị trí phải bằng nhau")

        logo_items: list[tuple[bytes, float, float, float, float]] = []
        for index, logo_bytes in enumerate(logo_payloads):
            if placements:
                logo_x = float(placements[index].get("x", x))
                logo_y = float(placements[index].get("y", y))
                logo_w = float(placements[index].get("w", 0) or 0)
                logo_h = float(placements[index].get("h", 0) or 0)
            else:
                logo_x = x
                logo_y = y
                logo_w = 0.0
                logo_h = 0.0
            logo_items.append((logo_bytes, logo_x, logo_y, logo_w, logo_h))

        names = template_names or ([template_name] if template_name else [])
        if not names:
            raise ValueError("Cần ít nhất một template_name hoặc template_names")
        output_bytes, output_name = form_service.create_output_zip(
            configured_dir=get_settings().form_templates_dir,
            template_names=names,
            logo_bytes=logo_payloads[0],
            x=x,
            y=y,
            is_watermark=is_watermark,
            password=password,
            logo_placements=logo_items,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        for uploaded_logo in uploaded_logos:
            await uploaded_logo.close()

    return Response(
        content=output_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": _attachment_header(output_name),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
