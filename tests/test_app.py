"""FastAPI 网页集成测试。"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

client = TestClient(app)

GOOD = "地区,0-17岁,18-64岁,65岁以上\n甲区,5,1,0\n乙区,2,7,3\n丙区,4,6,8\n"
NO_SOLUTION = "地区,0-17岁,18-64岁\n甲区,1,0\n乙区,0,0\n"


def test_index_ok():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "病例交叉表" in resp.text


def test_analyze_with_pasted_text():
    resp = client.post("/analyze", data={"csv_text": GOOD})
    assert resp.status_code == 200
    # 预览包含合计行/列与遮盖标记
    assert "合计" in resp.text
    assert "*" in resp.text
    assert "下载同内容 CSV" in resp.text


def test_analyze_with_file_upload():
    resp = client.post(
        "/analyze",
        files={"file": ("table.csv", GOOD.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200
    assert "合计" in resp.text


def test_analyze_invalid_input_shows_reason():
    resp = client.post("/analyze", data={"csv_text": "地区,A,B\n甲,1,x\n乙,3,4\n"})
    assert resp.status_code == 400
    assert "非负整数" in resp.text


def test_analyze_empty_input():
    resp = client.post("/analyze", data={"csv_text": ""})
    assert resp.status_code == 400
    assert "请上传" in resp.text


def test_analyze_no_solution_explains_without_counts():
    resp = client.post("/analyze", data={"csv_text": NO_SOLUTION})
    assert resp.status_code == 200
    assert "无法生成" in resp.text
    # 不泄露原始人数
    assert ">1<" not in resp.text


def test_download_roundtrip_same_content():
    resp = client.post("/analyze", data={"csv_text": GOOD})
    assert resp.status_code == 200
    # 从预览页提取隐藏域中的 CSV 内容并请求下载
    marker = 'name="csv_content" value="'
    start = resp.text.index(marker) + len(marker)
    end = resp.text.index('"', start)
    csv_content = resp.text[start:end]
    dl = client.post("/download", data={"csv_content": csv_content,
                                        "filename": "masked_crosstab.csv"})
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("text/csv")
    assert "attachment" in dl.headers["content-disposition"]
    body = dl.content.decode("utf-8-sig")
    assert body == csv_content
    # 内容与预览一致：含合计、遮盖格
    assert "合计" in body
    assert "*" in body
    # 行列合计正确（甲区行合计 6，乙区 12，丙区 18，总计 36）
    assert body.strip().split("\n")[-1].endswith("36")


def test_download_appends_csv_extension():
    dl = client.post("/download", data={"csv_content": "a,b\n1,2\n",
                                        "filename": "result"})
    assert dl.status_code == 200
    assert "result.csv" in dl.headers["content-disposition"]


# ---------------------------------------------------------------------------
# 合计差错定位页面
# ---------------------------------------------------------------------------

DELIVERY_OK = (
    "地区,0-17岁,18-64岁,65岁以上,合计\n"
    "甲区,*,*,0,6\n"
    "乙区,*,*,3,12\n"
    "丙区,4,6,8,18\n"
    "合计,11,14,11,36\n"
)


def test_totals_page_ok():
    resp = client.get("/totals")
    assert resp.status_code == 200
    assert "合计差错定位" in resp.text


def test_totals_consistent_reports_no_check_needed():
    resp = client.post("/totals/check", data={"csv_text": DELIVERY_OK})
    assert resp.status_code == 200
    assert "无需核对" in resp.text
    # 不泄露隐藏人数或推测值
    assert "更正值" not in resp.text


def test_totals_wrong_grand_total_flags_field():
    bad = DELIVERY_OK.replace("合计,11,14,11,36", "合计,11,14,11,37")
    resp = client.post("/totals/check", data={"csv_text": bad})
    assert resp.status_code == 200
    assert "需要核对 1 个合计字段" in resp.text
    assert "总计" in resp.text
    # 页面只列字段，不给推测值
    assert "37" in resp.text  # 原表内容回显
    assert "应为" not in resp.text


def test_totals_file_upload():
    resp = client.post(
        "/totals/check",
        files={"file": ("delivery.csv", DELIVERY_OK.encode("utf-8"),
                        "text/csv")},
    )
    assert resp.status_code == 200
    assert "无需核对" in resp.text


def test_totals_lists_all_minimal_combinations():
    text = (
        "地区,A,B,C,合计\n"
        "甲区,*,*,*,9\n"
        "乙区,*,0,0,2\n"
        "合计,5,2,3,11\n"
    )
    resp = client.post("/totals/check", data={"csv_text": text})
    assert resp.status_code == 200
    assert "需要核对 1 个合计字段" in resp.text
    for label in ("A（列合计）", "B（列合计）", "C（列合计）"):
        assert label in resp.text


def test_totals_invalid_input_explains_reason():
    resp = client.post(
        "/totals/check",
        data={"csv_text": "地区,A,B,合计\n甲区,1,4,5\n乙区,3,5,8\n合计,4,9,13\n"},
    )
    assert resp.status_code == 400
    # 指出具体位置与规则，而不是回显该格的数值
    assert "第 1 行第 1 列" in resp.text
    assert "公开格只能为 0 或至少 3 的整数" in resp.text
    assert "当前值为" not in resp.text


def test_totals_missing_totals_row_and_column():
    resp = client.post(
        "/totals/check",
        data={"csv_text": "地区,A,B\n甲区,*,3\n乙区,4,*\n"},
    )
    assert resp.status_code == 400
    assert "合计" in resp.text


def test_totals_empty_input():
    resp = client.post("/totals/check", data={"csv_text": ""})
    assert resp.status_code == 400
    assert "请上传" in resp.text


def test_existing_flow_still_works_and_links_to_totals():
    resp = client.get("/")
    assert 'href="/totals"' in resp.text
    resp = client.post("/analyze", data={"csv_text": GOOD})
    assert resp.status_code == 200
    assert "下载同内容 CSV" in resp.text
