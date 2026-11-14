"""合计差错定位测试：解析校验、手算用例与暴力枚举交叉验证。"""

import itertools
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.totals import (COL_TOTAL, GRAND_TOTAL, ROW_TOTAL, DeliveryTable,
                        InputError, field_label, is_feasible,
                        locate_total_errors, parse_delivery_csv,
                        total_fields)

GOOD = (
    "地区,0-17岁,18-64岁,65岁以上,合计\n"
    "甲区,*,*,0,6\n"
    "乙区,*,*,3,12\n"
    "丙区,4,6,8,18\n"
    "合计,11,14,11,36\n"
)


def _labels(tab, result):
    return [[field_label(tab, field) for field in combo]
            for combo in result.combos]


# ---------------------------------------------------------------------------
# 解析与校验
# ---------------------------------------------------------------------------

def test_parse_good():
    tab = parse_delivery_csv(GOOD)
    assert tab.corner == "地区"
    assert tab.col_labels == ["0-17岁", "18-64岁", "65岁以上"]
    assert tab.row_labels == ["甲区", "乙区", "丙区"]
    assert tab.cells == [[None, None, 0], [None, None, 3], [4, 6, 8]]
    assert tab.row_totals == [6, 12, 18]
    assert tab.col_totals == [11, 14, 11]
    assert tab.grand_total == 36


def test_parse_with_bom_blank_lines_and_named_masks():
    text = ("﻿地区,A,B,合计\n\n甲区,*,3,5\n乙区,4,*,9\n"
            "合计,7,7,13\n\n")
    tab = parse_delivery_csv(text)
    assert tab.cells == [[None, 3], [4, None]]


@pytest.mark.parametrize("text,fragment", [
    ("地区,A,B\n甲区,*,3\n乙区,4,*\n", "合计"),             # 缺合计行列
    ("地区,A,B,合计\n甲区,*,3,5\n乙区,4,*\n合计,7,7,13\n", "不一致"),
    ("地区,A,合计\n甲区,*,4\n乙区,4,9\n合计,7,7,7\n", "不一致"),  # 表头缺列
    ("地区,A,B,C,D,E,合计\n"
     "甲,*,*,*,*,*,9\n乙,*,*,*,*,*,9\n"
     "合计,*,*,*,*,*,18\n", "2~4 列"),                       # 5 列
    ("地区,A,B,合计\n甲区,*,3,5\n合计,7,7,13\n", "2~4 行"),  # 只有 1 行
    ("地区,A,B,合计\n甲区,1,4,5\n乙区,3,5,8\n合计,4,9,13\n", "1 或 2"),
    ("地区,A,B,合计\n甲区,2,3,5\n乙区,4,5,9\n合计,6,8,14\n", "1 或 2"),
    ("地区,A,B,合计\n甲区,-1,3,2\n乙区,4,5,9\n合计,3,8,12\n", "不是公开格"),
    ("地区,A,B,合计\n甲区,x,3,3\n乙区,4,5,9\n合计,4,8,12\n", "不是公开格"),
    ("地区,A,B,合计\n甲区,*,3,5\n乙区,4,*,9\n合计,7,7,%%\n", "总计应为整数"),
    ("地区,A,B,合计\n甲区,*,3,5\n乙区,4,*,9\n合计,7,七,13\n", "列合计应为整数"),
    ("地区,A,B,合计\n甲区,*,3,五\n乙区,4,*,9\n合计,7,7,13\n", "行合计应为整数"),
    ("地区,A,A,合计\n甲区,*,3,5\n乙区,4,*,9\n合计,7,7,13\n", "重复"),
    ("地区,A,B,合计\n甲区,*,3,5\n甲区,4,*,9\n合计,7,7,13\n", "重复"),
    ("地区,A,B,合计\n甲区,*,3,5\n乙区,4,*\n合计,7,7,13\n", "不一致"),
    ("地区,A,合计\n甲区,*,4\n乙区,4,9\n合计,7,13\n", "2~4 列"),  # 只有 1 列数据
    ("地区,A,B,合计\n甲区,1,3,4\n乙区,4,5,9\n合计,5,8,13\n", "1 或 2"),
])
def test_parse_invalid(text, fragment):
    with pytest.raises(InputError) as exc:
        parse_delivery_csv(text)
    assert any(fragment in msg for msg in exc.value.messages)


def test_parse_errors_never_include_cell_counts():
    with pytest.raises(InputError) as exc:
        parse_delivery_csv(
            "地区,A,合计\n甲区,3,4\n乙区,3,3\n合计,4,4\n")
    joined = "".join(exc.value.messages)
    # 规则说明中不含任何具体人数数字或隐藏值
    assert "2" not in joined.replace("1 或 2", "").replace("2~4", "")
    assert "3" not in joined


def test_parse_empty():
    with pytest.raises(InputError):
        parse_delivery_csv("  \n\n")


# ---------------------------------------------------------------------------
# 手算用例
# ---------------------------------------------------------------------------

def test_consistent_table_needs_no_check():
    tab = parse_delivery_csv(GOOD)
    result = locate_total_errors(tab)
    assert result.consistent
    assert result.minimum == 0
    assert result.combos == [()]


def test_wrong_grand_total_only():
    text = GOOD.replace("合计,11,14,11,36", "合计,11,14,11,37")
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 1
    assert _labels(tab, result) == [["总计"]]


def test_wrong_row_total():
    text = (
        "地区,A,B,合计\n"
        "甲区,*,3,6\n"      # 行合计应为 5
        "乙区,4,*,9\n"
        "合计,8,8,16\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 1
    assert _labels(tab, result) == [["甲区（行合计）"]]


def test_two_wrong_row_totals_listed_together():
    # 两个行合计同时抄错；单独更正一个字段不够，最少需要两个
    text = (
        "地区,A,B,合计\n"
        "甲区,*,3,5\n"
        "乙区,4,*,9\n"
        "合计,8,10,18\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 2
    assert _labels(tab, result) == [["甲区（行合计）", "乙区（行合计）"]]


def test_wrong_column_total():
    text = (
        "地区,A,B,合计\n"
        "甲区,*,3,7\n"
        "乙区,4,*,9\n"
        "合计,8,9,16\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 1
    assert _labels(tab, result) == [["B（列合计）"]]


def test_multiple_equivalent_fields_all_listed():
    # 第一个数据行全为 *，只更正任一个列合计即可让其余合计相容
    text = (
        "地区,A,B,C,合计\n"
        "甲区,*,*,*,9\n"
        "乙区,*,0,0,2\n"
        "合计,5,2,3,11\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 1
    assert _labels(tab, result) == [["A（列合计）"], ["B（列合计）"],
                                    ["C（列合计）"]]


def test_error_requires_two_fields_when_no_single_field_fits():
    # 公开格已超过行合计，只有同时更正该行合计与总计才能相容
    text = (
        "地区,A,B,合计\n"
        "甲区,0,3,4\n"
        "乙区,4,0,4\n"
        "合计,4,3,8\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 2
    assert _labels(tab, result) == [["甲区（行合计）", "总计"]]


def test_multiple_two_field_combos_all_listed():
    text = (
        "地区,A,B,合计\n"
        "甲区,0,4,4\n"
        "乙区,*,*,4\n"
        "合计,2,5,9\n"
    )
    tab = parse_delivery_csv(text)
    result = locate_total_errors(tab)
    assert result.minimum == 2
    assert _labels(tab, result) == [
        ["乙区（行合计）", "A（列合计）"],
        ["乙区（行合计）", "B（列合计）"],
        ["乙区（行合计）", "总计"],
        ["A（列合计）", "总计"],
        ["B（列合计）", "总计"],
    ]


def test_negative_hidden_need_is_infeasible():
    tab = parse_delivery_csv(
        "地区,A,B,合计\n甲区,*,3,1\n乙区,4,*,9\n合计,5,3,10\n")
    # 行合计 1 小于公开的 3，必须更正该行
    result = locate_total_errors(tab)
    assert result.minimum >= 1
    assert all(("甲区（行合计）" in combo) for combo in _labels(tab, result))


def test_combo_size_bound_and_all_fields_always_work():
    tab = parse_delivery_csv(GOOD)
    # 更正全部合计字段必然可行：只需 * 格取 1 即可
    everything = {field for field in total_fields(tab)}
    assert is_feasible(tab, everything)


def test_zero_hidden_cells_table():
    text = (
        "地区,A,B,合计\n"
        "甲区,3,4,7\n"
        "乙区,5,6,11\n"
        "合计,8,10,18\n"
    )
    tab = parse_delivery_csv(text)
    assert locate_total_errors(tab).consistent


# ---------------------------------------------------------------------------
# 暴力枚举交叉验证
# ---------------------------------------------------------------------------

def brute_feasible(tab, corrected):
    """穷举 * 格正整数取值（受合计上界约束），判定其余合计能否成立。"""
    n, m = tab.n_rows, tab.n_cols
    hidden = [(i, j) for i in range(n) for j in range(m)
              if tab.cells[i][j] is None]
    row_fixed = [(ROW_TOTAL, i) not in corrected for i in range(n)]
    col_fixed = [(COL_TOTAL, j) not in corrected for j in range(m)]
    grand_fixed = (GRAND_TOTAL, None) not in corrected

    bounds = []
    for (i, j) in hidden:
        upper = max(tab.row_totals + tab.col_totals
                    + [tab.grand_total, 4])
        if row_fixed[i]:
            upper = min(upper, tab.row_totals[i])
        if col_fixed[j]:
            upper = min(upper, tab.col_totals[j])
        if upper < 1:
            return False
        bounds.append(upper)

    for values in itertools.product(*[range(1, b + 1) for b in bounds]):
        grid = [[tab.cells[i][j] for j in range(m)] for i in range(n)]
        for (i, j), value in zip(hidden, values):
            grid[i][j] = value
        if any(row_fixed[i] and sum(grid[i]) != tab.row_totals[i]
               for i in range(n)):
            continue
        if any(col_fixed[j]
               and sum(grid[i][j] for i in range(n)) != tab.col_totals[j]
               for j in range(m)):
            continue
        if grand_fixed and sum(map(sum, grid)) != tab.grand_total:
            continue
        return True
    return False


def brute_locate(tab):
    fields = total_fields(tab)
    for size in range(len(fields) + 1):
        combos = [combo for combo in itertools.combinations(fields, size)
                  if brute_feasible(tab, set(combo))]
        if combos:
            return size, combos
    raise AssertionError("全放松必然可行")


def random_delivery_table(rng):
    while True:
        n, m = rng.randint(2, 3), rng.randint(2, 3)
        cells = [[None if rng.random() < 0.5 else rng.choice([0, 0, 3, 4])
                  for _ in range(m)] for _ in range(n)]
        if sum(v is None for row in cells for v in row) <= 4:
            break
    grid = [[rng.randint(1, 3) if cells[i][j] is None else cells[i][j]
             for j in range(m)] for i in range(n)]
    row_totals = [sum(grid[i]) for i in range(n)]
    col_totals = [sum(grid[i][j] for i in range(n)) for j in range(m)]
    grand = sum(row_totals)
    for _ in range(rng.randint(0, 3)):
        kind = rng.choice(["row", "col", "grand"])
        delta = rng.choice([-2, -1, 1, 2])
        if kind == "row":
            i = rng.randrange(n)
            row_totals[i] = max(0, row_totals[i] + delta)
        elif kind == "col":
            j = rng.randrange(m)
            col_totals[j] = max(0, col_totals[j] + delta)
        else:
            grand = max(0, grand + delta)
    return DeliveryTable("地区", [f"c{j}" for j in range(m)],
                         [f"r{i}" for i in range(n)], cells,
                         row_totals, col_totals, grand)


@pytest.mark.parametrize("seed", range(120))
def test_locator_matches_brute(seed):
    rng = random.Random(seed)
    tab = random_delivery_table(rng)
    expected_min, expected_combos = brute_locate(tab)
    result = locate_total_errors(tab)
    assert result.minimum == expected_min
    assert set(map(frozenset, result.combos)) == \
        set(map(frozenset, expected_combos))


@pytest.mark.parametrize("seed", range(40))
def test_feasibility_matches_brute(seed):
    rng = random.Random(5000 + seed)
    tab = random_delivery_table(rng)
    fields = total_fields(tab)
    combo = frozenset(rng.sample(fields, rng.randint(0, len(fields))))
    assert is_feasible(tab, combo) == brute_feasible(tab, set(combo))
