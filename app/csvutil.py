"""CSV 输入解析校验与交付 CSV 渲染。

输入格式（首行为年龄段、首列为地区的交叉表）：

    地区,0-17岁,18-64岁,65岁以上
    甲区,5,1,0
    乙区,2,7,3

要求：2~4 个数据行、2~4 个数据列；行标签互不重复、列标签互不重复；
数据单元格均为非负整数。左上角为角角标（可为空），原样保留到输出。
"""

import csv
import io
import re

from .masking import HIDE_MARK

MIN_DIM = 2
MAX_DIM = 4
MAX_FILE_BYTES = 256 * 1024  # 演示环境的合理上限

TOTAL_LABEL = "合计"
_INT_RE = re.compile(r"\d+")


class InputError(Exception):
    """输入非法。messages 为面向用户的中文原因列表（不含原始人数）。"""

    def __init__(self, messages):
        self.messages = list(messages)
        super().__init__("; ".join(self.messages))


class Crosstab:
    """解析后的交叉表。"""

    def __init__(self, corner, col_labels, row_labels, values):
        self.corner = corner
        self.col_labels = col_labels
        self.row_labels = row_labels
        self.values = values

    @property
    def n_rows(self):
        return len(self.row_labels)

    @property
    def n_cols(self):
        return len(self.col_labels)


def decode_upload(raw: bytes) -> str:
    if not raw:
        raise InputError(["CSV 内容为空，请上传文件或粘贴文本。"])
    if len(raw) > MAX_FILE_BYTES:
        raise InputError(["文件过大（上限 256 KB）。"])
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError(["文件编码无法识别，请使用 UTF-8 编码的 CSV。"])


def parse_crosstab(text: str) -> Crosstab:
    """解析并校验 CSV 文本，非法时抛出 InputError。"""
    text = text.lstrip("\ufeff")  # 粘贴的文本可能带有 BOM
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise InputError([f"CSV 解析失败：{exc}"])

    # 忽略完全空白的行（如文件末尾空行）
    rows = [[cell.strip() for cell in row] for row in rows]
    rows = [row for row in rows if any(cell != "" for cell in row)]
    if not rows:
        raise InputError(["CSV 内容为空，请上传文件或粘贴文本。"])

    errors = []
    n_data_rows = len(rows) - 1
    if not (MIN_DIM <= n_data_rows <= MAX_DIM):
        errors.append(f"数据行数应为 {MIN_DIM}~{MAX_DIM} 行（当前 {n_data_rows} 行）。")

    width = len(rows[0])
    n_data_cols = width - 1
    if not (MIN_DIM <= n_data_cols <= MAX_DIM):
        errors.append(f"数据列数应为 {MIN_DIM}~{MAX_DIM} 列（当前 {n_data_cols} 列）。")

    for r, row in enumerate(rows[1:], start=2):
        if len(row) != width:
            errors.append(
                f"第 {r} 行有 {len(row)} 个单元格，与表头的 {width} 个不一致。")
    if errors:
        raise InputError(errors)

    corner = rows[0][0]
    col_labels = rows[0][1:]
    row_labels = [row[0] for row in rows[1:]]

    for idx, label in enumerate(col_labels):
        if label == "":
            errors.append(f"第 1 行第 {idx + 2} 列的年龄段标签为空。")
    for idx, label in enumerate(row_labels):
        if label == "":
            errors.append(f"第 {idx + 2} 行第 1 列的地区标签为空。")

    dup_cols = sorted({x for x in col_labels if col_labels.count(x) > 1})
    if dup_cols:
        errors.append("列标签（年龄段）重复：" + "、".join(f"“{x}”" for x in dup_cols) + "。")
    dup_rows = sorted({x for x in row_labels if row_labels.count(x) > 1})
    if dup_rows:
        errors.append("行标签（地区）重复：" + "、".join(f"“{x}”" for x in dup_rows) + "。")

    values = []
    for r, row in enumerate(rows[1:], start=2):
        parsed_row = []
        for c, cell in enumerate(row[1:], start=2):
            if not _INT_RE.fullmatch(cell):
                errors.append(
                    f"第 {r} 行第 {c} 列的 “{cell}” 不是非负整数。")
                parsed_row.append(0)
            else:
                parsed_row.append(int(cell))
        values.append(parsed_row)
    if errors:
        raise InputError(errors)

    return Crosstab(corner, col_labels, row_labels, values)


def render_delivery_csv(tab: Crosstab, hidden) -> str:
    """渲染交付 CSV：保留行合计、列合计与总计，被遮盖格以 * 表示。"""
    n, m = tab.n_rows, tab.n_cols
    row_totals = [sum(tab.values[i]) for i in range(n)]
    col_totals = [sum(tab.values[i][j] for i in range(n)) for j in range(m)]
    grand = sum(row_totals)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([tab.corner, *tab.col_labels, TOTAL_LABEL])
    for i in range(n):
        cells = [HIDE_MARK if (i, j) in hidden else str(tab.values[i][j])
                 for j in range(m)]
        writer.writerow([tab.row_labels[i], *cells, str(row_totals[i])])
    writer.writerow([TOTAL_LABEL, *map(str, col_totals), str(grand)])
    return buf.getvalue()


def delivery_rows(tab: Crosstab, hidden):
    """与 render_delivery_csv 完全同内容的二维表（用于网页预览）。"""
    n, m = tab.n_rows, tab.n_cols
    row_totals = [sum(tab.values[i]) for i in range(n)]
    col_totals = [sum(tab.values[i][j] for i in range(n)) for j in range(m)]
    grand = sum(row_totals)

    header = [tab.corner, *tab.col_labels, TOTAL_LABEL]
    body = []
    for i in range(n):
        cells = [HIDE_MARK if (i, j) in hidden else str(tab.values[i][j])
                 for j in range(m)]
        body.append([tab.row_labels[i], *cells, str(row_totals[i])])
    footer = [TOTAL_LABEL, *map(str, col_totals), str(grand)]
    return header, body, footer
