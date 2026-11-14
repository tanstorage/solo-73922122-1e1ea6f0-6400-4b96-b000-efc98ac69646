"""CSV 解析校验与交付渲染测试。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.csvutil import (InputError, decode_upload, delivery_rows,
                         parse_crosstab, render_delivery_csv)

GOOD = "地区,0-17岁,18-64岁,65岁以上\n甲区,5,1,0\n乙区,2,7,3\n"


def test_parse_good():
    tab = parse_crosstab(GOOD)
    assert tab.corner == "地区"
    assert tab.col_labels == ["0-17岁", "18-64岁", "65岁以上"]
    assert tab.row_labels == ["甲区", "乙区"]
    assert tab.values == [[5, 1, 0], [2, 7, 3]]


def test_parse_with_bom_and_blank_lines():
    tab = parse_crosstab("﻿地区,A,B\n\n甲,1,2\n乙,3,4\n\n")
    assert tab.values == [[1, 2], [3, 4]]


def test_parse_4x4_ok():
    text = "角落,a,b,c,d\nr1,1,2,3,4\nr2,4,3,2,1\nr3,0,0,5,5\nr4,9,9,9,9\n"
    tab = parse_crosstab(text)
    assert tab.n_rows == 4 and tab.n_cols == 4


@pytest.mark.parametrize("text,fragment", [
    ("地区,A\n甲,1\n", "2~4"),                              # 只有 1 列
    ("地区,A,B,C,D,E\n甲,1,2,3,4,5\n乙,1,2,3,4,5\n", "2~4"),  # 5 列
    ("地区,A,B\n甲,1,2\n", "2~4"),                          # 只有 1 行
    ("地区,A,B\nr1,1,2\nr2,1,2\nr3,1,2\nr4,1,2\nr5,1,2\n", "2~4"),  # 5 行
    ("地区,A,A\n甲,1,2\n乙,3,4\n", "重复"),                 # 列标签重复
    ("地区,A,B\n甲,1,2\n甲,3,4\n", "重复"),                 # 行标签重复
    ("地区,A,B\n甲,1,x\n乙,3,4\n", "非负整数"),             # 非数字
    ("地区,A,B\n甲,1,-2\n乙,3,4\n", "非负整数"),            # 负数
    ("地区,A,B\n甲,1,2.0\n乙,3,4\n", "非负整数"),           # 小数
    ("地区,A,B\n甲,1,\n乙,3,4\n", "非负整数"),              # 空格
    ("地区,A,B\n甲,1,2\n乙,3,4,5\n", "不一致"),             # 列数不齐
    ("地区,A,\n甲,1,2\n乙,3,4\n", "为空"),                # 列标签空
    ("地区,A,B\n,1,2\n乙,3,4\n", "为空"),                  # 行标签空
])
def test_parse_invalid(text, fragment):
    with pytest.raises(InputError) as exc:
        parse_crosstab(text)
    assert any(fragment in msg for msg in exc.value.messages)


def test_decode_empty_and_bad_encoding():
    with pytest.raises(InputError):
        decode_upload(b"")
    with pytest.raises(InputError):
        decode_upload(b"\xff\xfe\x00\x01")


def test_render_delivery_csv_with_totals():
    tab = parse_crosstab(GOOD)
    hidden = {(0, 0), (0, 1), (1, 0), (1, 1)}
    csv_text = render_delivery_csv(tab, hidden)
    assert csv_text == (
        "地区,0-17岁,18-64岁,65岁以上,合计\n"
        "甲区,*,*,0,6\n"
        "乙区,*,*,3,12\n"
        "合计,7,8,3,18\n"
    )


def test_delivery_rows_matches_csv():
    tab = parse_crosstab(GOOD)
    hidden = {(0, 1), (1, 0)}
    header, body, footer = delivery_rows(tab, hidden)
    csv_text = render_delivery_csv(tab, hidden)
    lines = [line.split(",") for line in csv_text.strip().split("\n")]
    assert lines[0] == header
    assert lines[1:-1] == body
    assert lines[-1] == footer
