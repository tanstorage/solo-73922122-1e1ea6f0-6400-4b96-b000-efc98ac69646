"""病例交叉表安全交付工具 —— FastAPI 网页应用。

页面：
  GET  /         上传页（文件或粘贴 CSV）
  POST /analyze  解析、遮盖并在浏览器中预览交付表
  POST /download 下载与预览同内容的 CSV
"""

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import re

from .csvutil import (InputError, decode_upload, delivery_rows,
                      parse_crosstab, render_delivery_csv)
from .masking import find_hidden_cells

BASE_DIR = Path(__file__).resolve().parent

_SAFE_FILENAME_RE = re.compile(r"[^\w.\-一-鿿]+")

app = FastAPI(title="病例交叉表安全交付工具")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

NO_SOLUTION_MESSAGE = (
    "无法生成满足要求的交付表：在保留行合计、列合计与总计的前提下，"
    "即使遮盖全部正数格，仍存在必须遮盖的格子会被唯一确定，"
    "无法保证每个被遮盖格都有至少两种相容取值。"
    "建议先合并地区或年龄段以降低稀疏度，再重新上传。"
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/analyze", response_class=HTMLResponse)
async def analyze(request: Request,
                  file: UploadFile | None = None,
                  csv_text: str = Form(default="")):
    # 优先使用上传文件；未上传时使用粘贴的文本
    raw = b""
    if file is not None and file.filename:
        raw = await file.read()
    if not raw and csv_text.strip():
        raw = csv_text.encode("utf-8")
    if not raw:
        return _input_error(request, ["请上传 CSV 文件，或在文本框中粘贴 CSV 内容。"])

    try:
        text = decode_upload(raw)
        tab = parse_crosstab(text)
    except InputError as exc:
        return _input_error(request, exc.messages)

    hidden = find_hidden_cells(tab.values)
    if hidden is None:
        return templates.TemplateResponse(
            request, "result.html",
            {"ok": False, "reason": NO_SOLUTION_MESSAGE},
        )

    mandatory = {(i, j) for i in range(tab.n_rows) for j in range(tab.n_cols)
                 if tab.values[i][j] in (1, 2)}
    extra = sorted(hidden - mandatory)
    extra_labels = [f"{tab.row_labels[i]} × {tab.col_labels[j]}" for (i, j) in extra]

    csv_content = render_delivery_csv(tab, hidden)
    header, body, footer = delivery_rows(tab, hidden)
    return templates.TemplateResponse(
        request, "result.html",
        {
            "ok": True,
            "header": header,
            "body": body,
            "footer": footer,
            "n_hidden": len(hidden),
            "n_mandatory": len(mandatory),
            "n_extra": len(extra),
            "extra_labels": extra_labels,
            "csv_content": csv_content,
            "filename": "masked_crosstab.csv",
        },
    )


@app.post("/download")
async def download(csv_content: str = Form(...),
                   filename: str = Form(default="masked_crosstab.csv")):
    # 清理文件名，避免响应头注入
    filename = _SAFE_FILENAME_RE.sub("_", filename).strip("._") or "masked_crosstab"
    if not filename.endswith(".csv"):
        filename += ".csv"
    # 带 BOM 的 UTF-8，便于 Excel 直接打开；内容与网页预览完全一致
    data = csv_content.encode("utf-8-sig")
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _input_error(request: Request, messages):
    return templates.TemplateResponse(
        request, "index.html",
        {"errors": messages},
        status_code=400,
    )
