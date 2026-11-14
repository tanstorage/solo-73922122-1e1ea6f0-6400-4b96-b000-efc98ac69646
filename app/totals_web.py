"""合计差错定位页面（质控员核查交付表用）。"""

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .csvutil import InputError, decode_upload
from .totals import field_label, locate_total_errors, parse_delivery_csv

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router = APIRouter()


@router.get("/totals", response_class=HTMLResponse)
async def totals_index(request: Request):
    return templates.TemplateResponse(request, "totals_index.html")


@router.post("/totals/check", response_class=HTMLResponse)
async def totals_check(request: Request,
                       file: UploadFile | None = None,
                       csv_text: str = Form(default="")):
    raw = b""
    if file is not None and file.filename:
        raw = await file.read()
    if not raw and csv_text.strip():
        raw = csv_text.encode("utf-8")
    if not raw:
        return _input_error(
            request, ["请上传 CSV 文件，或在文本框中粘贴 CSV 内容。"])

    try:
        text = decode_upload(raw)
        tab = parse_delivery_csv(text)
    except InputError as exc:
        return _input_error(request, exc.messages)

    result = locate_total_errors(tab)
    combos = [[field_label(tab, field) for field in combo]
              for combo in result.combos]

    return templates.TemplateResponse(
        request, "totals_result.html",
        {
            "tab": tab,
            "consistent": result.consistent,
            "minimum": result.minimum,
            "combos": combos,
            "n_combos": len(combos),
        },
    )


def _input_error(request: Request, messages):
    return templates.TemplateResponse(
        request, "totals_index.html",
        {"errors": messages},
        status_code=400,
    )
