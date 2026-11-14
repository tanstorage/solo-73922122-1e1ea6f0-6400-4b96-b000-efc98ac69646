"""遮盖交付表的合计差错定位。

质控员拿到一张已经遮盖好的「地区 × 年龄段」交付表时，公开格与 ``*``
格本身是可信的，需要核对的是行合计、列合计与总计是否抄错。本模块在
**保持公开格不变**、``*`` 格取正整数（≥ 1）的前提下，找出让其余合计
相容所需更正的最少合计字段数，并列出所有同样少、且可行的字段组合。

输入是交付表 CSV：表头最后一列为「合计」，最后一行以「合计」开头，
右下角为总计。数据区必须为 2~4 行 × 2~4 列；公开格只能为 0 或至少 3，
``*`` 表示被遮盖的正整数人数。

可行性模型
----------
把每个 ``*`` 格看作行节点到列节点的一条流边（下界 1、上界不限）。
公开格对行/列的贡献是固定常数；未被列入更正集合的行合计、列合计与
总计则分别约束源点→行、列→汇点、汇点→源点的流量。于是「其余合计
与某组正整数填法相容」等价于一个带下界的可行环流问题，用一次最大流
即可精确判定（整数容量，整数流即为整数填法）。

更正集合的可行性对集合包含关系单调：多放松一个合计字段只会增加可行
方案。因此从小到大枚举字段数量，第一个存在可行组合的数量即最少需要
更正的字段数；同一数量下所有可行的组合全部列出。
"""

import csv
import io
import re
from itertools import combinations

from .csvutil import InputError, MAX_DIM, MIN_DIM, TOTAL_LABEL
from .masking import HIDE_MARK

# 合计字段的三种类型：行合计、列合计、总计
ROW_TOTAL = "row"
COL_TOTAL = "col"
GRAND_TOTAL = "grand"

_NONNEG_INT_RE = re.compile(r"\d+")
_INT_RE = re.compile(r"-?\d+")


class DeliveryTable:
    """解析后的遮盖交付表。

    cells[i][j] 为 int（公开格）或 None（``*`` 遮盖格）；
    row_totals / col_totals / grand_total 为交付表中抄录的合计值。
    """

    def __init__(self, corner, col_labels, row_labels, cells,
                 row_totals, col_totals, grand_total):
        self.corner = corner
        self.col_labels = col_labels
        self.row_labels = row_labels
        self.cells = cells
        self.row_totals = row_totals
        self.col_totals = col_totals
        self.grand_total = grand_total
        # 解析阶段即算好公开格贡献，供可行性判定反复使用
        n, m = len(row_labels), len(col_labels)
        self._pub_row = [sum(v for v in cells[i] if v is not None)
                         for i in range(n)]
        self._pub_col = [sum(cells[i][j] for i in range(n)
                             if cells[i][j] is not None)
                         for j in range(m)]
        self._pub_total = sum(self._pub_row)

    @property
    def n_rows(self):
        return len(self.row_labels)

    @property
    def n_cols(self):
        return len(self.col_labels)


class TotalCheckResult:
    """合计差错定位结果。

    minimum 为最少需要更正的合计字段数；combos 为该数量下所有可行的
    字段组合（每个组合是字段元组的列表）。minimum == 0 表示原表相容。
    """

    def __init__(self, minimum, combos):
        self.minimum = minimum
        self.combos = combos

    @property
    def consistent(self):
        return self.minimum == 0


def parse_delivery_csv(text: str) -> DeliveryTable:
    """解析并校验交付表 CSV，非法时抛出 InputError。

    错误原因只包含位置与规则说明，绝不包含任何人数数值。
    """
    text = text.lstrip("﻿")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise InputError([f"CSV 解析失败：{exc}"])

    rows = [[cell.strip() for cell in row] for row in rows]
    rows = [row for row in rows if any(cell != "" for cell in row)]
    if not rows:
        raise InputError(["CSV 内容为空，请上传文件或粘贴文本。"])

    width = len(rows[0])
    errors = []
    for r, row in enumerate(rows, start=1):
        if len(row) != width:
            errors.append(
                f"第 {r} 行有 {len(row)} 个单元格，与表头的 {width} 个不一致。")
    if errors:
        raise InputError(errors)

    if rows[0][-1] != TOTAL_LABEL:
        errors.append("表头最后一列应为“合计”，用于放置行合计。")
    if rows[-1][0] != TOTAL_LABEL:
        errors.append("最后一行应以“合计”开头，用于放置列合计。")
    if errors:
        raise InputError(errors)

    n_rows = len(rows) - 2
    n_cols = width - 2
    if not (MIN_DIM <= n_rows <= MAX_DIM):
        errors.append(
            f"数据区应为 {MIN_DIM}~{MAX_DIM} 行（不含表头与合计行），"
            f"当前 {n_rows} 行。")
    if not (MIN_DIM <= n_cols <= MAX_DIM):
        errors.append(
            f"数据区应为 {MIN_DIM}~{MAX_DIM} 列（不含行标签与行合计列），"
            f"当前 {n_cols} 列。")
    if errors:
        raise InputError(errors)

    corner = rows[0][0]
    col_labels = rows[0][1:-1]
    row_labels = [row[0] for row in rows[1:-1]]

    for idx, label in enumerate(col_labels):
        if label == "":
            errors.append(f"表头第 {idx + 2} 列的年龄段标签为空。")
        elif label == TOTAL_LABEL:
            errors.append("数据列的标签不能为“合计”，以免与合计列混淆。")
    for idx, label in enumerate(row_labels):
        if label == "":
            errors.append(f"第 {idx + 2} 行的地区标签为空。")
        elif label == TOTAL_LABEL:
            errors.append("数据行的标签不能为“合计”，以免与合计行混淆。")
    dup_cols = sorted({x for x in col_labels if col_labels.count(x) > 1})
    if dup_cols:
        errors.append("列标签（年龄段）重复：" +
                      "、".join(f"“{x}”" for x in dup_cols) + "。")
    dup_rows = sorted({x for x in row_labels if row_labels.count(x) > 1})
    if dup_rows:
        errors.append("行标签（地区）重复：" +
                      "、".join(f"“{x}”" for x in dup_rows) + "。")
    if errors:
        raise InputError(errors)

    cells = []
    for i, row in enumerate(rows[1:-1], start=1):
        parsed_row = []
        for j, token in enumerate(row[1:-1], start=1):
            if token == HIDE_MARK:
                parsed_row.append(None)  # 遮盖格：正整数，具体取值未知
            elif not _NONNEG_INT_RE.fullmatch(token):
                errors.append(
                    f"数据区第 {i} 行第 {j} 列不是公开格："
                    "公开格只能为 0 或至少 3 的整数，遮盖格请用 * 表示。")
                parsed_row.append(0)
            else:
                value = int(token)
                if value in (1, 2):
                    errors.append(
                        f"数据区第 {i} 行第 {j} 列是公开的 1 或 2 人："
                        "公开格只能为 0 或至少 3 的整数，人数为 1 或 2 "
                        "的格子应遮盖为 *。")
                parsed_row.append(value)
        cells.append(parsed_row)

    row_totals = []
    for i, row in enumerate(rows[1:-1], start=1):
        token = row[-1]
        if not _INT_RE.fullmatch(token):
            errors.append(f"第 {i + 1} 行的行合计应为整数。")
            row_totals.append(0)
        else:
            row_totals.append(int(token))

    col_totals = []
    for j, token in enumerate(rows[-1][1:-1], start=1):
        if not _INT_RE.fullmatch(token):
            errors.append(f"第 {j + 1} 列的列合计应为整数。")
            col_totals.append(0)
        else:
            col_totals.append(int(token))

    grand_token = rows[-1][-1]
    if not _INT_RE.fullmatch(grand_token):
        errors.append("总计应为整数。")
        grand_total = 0
    else:
        grand_total = int(grand_token)

    if errors:
        raise InputError(errors)
    return DeliveryTable(corner, col_labels, row_labels, cells,
                         row_totals, col_totals, grand_total)


def total_fields(tab: DeliveryTable):
    """按行合计、列合计、总计的顺序返回全部合计字段。"""
    fields = [(ROW_TOTAL, i) for i in range(tab.n_rows)]
    fields += [(COL_TOTAL, j) for j in range(tab.n_cols)]
    fields.append((GRAND_TOTAL, None))
    return fields


def field_label(tab: DeliveryTable, field) -> str:
    """合计字段的展示名称。"""
    kind, idx = field
    if kind == ROW_TOTAL:
        return f"{tab.row_labels[idx]}（行合计）"
    if kind == COL_TOTAL:
        return f"{tab.col_labels[idx]}（列合计）"
    return "总计"


def locate_total_errors(tab: DeliveryTable) -> TotalCheckResult:
    """定位最少需要更正的合计字段，并列出同数量的全部可行组合。"""
    fields = total_fields(tab)
    # 更正集合越大约束越松；从小到大找到第一个有可行组合的数量即可。
    for size in range(len(fields) + 1):
        feasible = [combo for combo in combinations(fields, size)
                    if is_feasible(tab, set(combo))]
        if feasible:
            return TotalCheckResult(size, feasible)
    raise AssertionError("全部合计字段均可更正，必然存在可行组合")


def is_feasible(tab: DeliveryTable, corrected) -> bool:
    """其余合计（未被更正的字段）是否与某组正整数填法相容。

    corrected 为需要更正的字段集合；这些字段的值不参与约束，其余字段
    必须与 ``*`` 格的正整数填法一致。
    """
    n, m = tab.n_rows, tab.n_cols
    pub_row = tab._pub_row
    pub_col = tab._pub_col
    pub_total = tab._pub_total

    row_need = [tab.row_totals[i] - pub_row[i] for i in range(n)]
    col_need = [tab.col_totals[j] - pub_col[j] for j in range(m)]
    grand_need = tab.grand_total - pub_total
    corrected_rows = {i for (kind, i) in corrected if kind == ROW_TOTAL}
    corrected_cols = {j for (kind, j) in corrected if kind == COL_TOTAL}
    corrected_grand = (GRAND_TOTAL, None) in corrected

    # 未被更正的行/列/总计是精确流量；需求为负说明公开格已超过合计。
    for i in range(n):
        if i not in corrected_rows and row_need[i] < 0:
            return False
    for j in range(m):
        if j not in corrected_cols and col_need[j] < 0:
            return False
    if not corrected_grand and grand_need < 0:
        return False

    # 任一可行解中，单条遮盖边上的流量不会超过固定合计的需求总和；
    # 再加 n*m + 1 覆盖全放松时的下界 1。仅用于判定，不需要还原填法。
    fixed_bound = sum(max(0, row_need[i]) for i in range(n)
                      if i not in corrected_rows)
    fixed_bound += sum(max(0, col_need[j]) for j in range(m)
                       if j not in corrected_cols)
    if not corrected_grand:
        fixed_bound += max(0, grand_need)
    inf = fixed_bound + n * m + 1

    S, T = n + m, n + m + 1
    edges = []
    for i in range(n):
        if i in corrected_rows:
            edges.append((S, i, 0, inf))
        else:
            edges.append((S, i, row_need[i], row_need[i]))
    for i in range(n):
        for j in range(m):
            if tab.cells[i][j] is None:
                edges.append((i, n + j, 1, inf))
    for j in range(m):
        if j in corrected_cols:
            edges.append((n + j, T, 0, inf))
        else:
            edges.append((n + j, T, col_need[j], col_need[j]))
    if corrected_grand:
        edges.append((T, S, 0, inf))
    else:
        edges.append((T, S, grand_need, grand_need))

    return _circulation_feasible(edges, n + m + 2)


def _circulation_feasible(edges, n_nodes: int) -> bool:
    """带下界的可行环流判定（经典下界转最大流）。

    edges 为 (u, v, lower, upper)；环流中每个节点的流入等于流出。
    """
    balance = [0] * n_nodes
    for u, v, lower, upper in edges:
        if lower < 0 or lower > upper:
            return False
        balance[u] -= lower
        balance[v] += lower

    super_s, super_t = n_nodes, n_nodes + 1
    net = _MaxFlow(n_nodes + 2)
    need = 0
    for v, value in enumerate(balance):
        if value > 0:
            net.add_edge(super_s, v, value)
            need += value
        elif value < 0:
            net.add_edge(v, super_t, -value)
    for u, v, lower, upper in edges:
        if upper > lower:
            net.add_edge(u, v, upper - lower)
    return net.max_flow(super_s, super_t) == need


class _MaxFlow:
    """小规模 Dinic 最大流（整数容量）。"""

    def __init__(self, n):
        self.graph = [[] for _ in range(n)]

    def add_edge(self, u, v, cap):
        self.graph[u].append([v, cap, len(self.graph[v])])
        self.graph[v].append([u, 0, len(self.graph[u]) - 1])

    def max_flow(self, s, t):
        flow = 0
        n = len(self.graph)
        while True:
            level = [-1] * n
            level[s] = 0
            queue = [s]
            for u in queue:
                for v, cap, _ in self.graph[u]:
                    if cap > 0 and level[v] < 0:
                        level[v] = level[u] + 1
                        queue.append(v)
            if level[t] < 0:
                return flow
            cursor = [0] * n

            def push(u, limit):
                if u == t:
                    return limit
                while cursor[u] < len(self.graph[u]):
                    edge = self.graph[u][cursor[u]]
                    v, cap, rev = edge
                    if cap > 0 and level[v] == level[u] + 1:
                        sent = push(v, min(limit, cap))
                        if sent:
                            edge[1] -= sent
                            self.graph[v][rev][1] += sent
                            return sent
                    cursor[u] += 1
                return 0

            while True:
                sent = push(s, 1 << 200)
                if not sent:
                    break
                flow += sent
