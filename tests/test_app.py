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
