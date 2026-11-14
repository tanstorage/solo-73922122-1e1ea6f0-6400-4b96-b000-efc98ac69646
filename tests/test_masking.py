"""核心遮盖算法测试：手算用例 + 暴力枚举交叉验证。"""

import random
import sys
from itertools import combinations
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.masking import find_hidden_cells, _forced_cells


# ---------------------------------------------------------------------------
# 暴力枚举：列出与公开值及行列合计相容的全部正整数赋值，
# 返回每个被遮盖格的可行取值集合。带节点预算，超限即跳过该用例。
# ---------------------------------------------------------------------------

class _BudgetExceeded(Exception):
    pass


def brute_value_sets(values, hidden, budget=1_500_000):
    n = len(values)
    m = len(values[0])
    cells = sorted(hidden)
    row_res = [sum(values[i][j] for j in range(m) if (i, j) in hidden)
               for i in range(n)]
    col_res = [sum(values[i][j] for i in range(n) if (i, j) in hidden)
               for j in range(m)]
    row_left = [sum(1 for j in range(m) if (i, j) in hidden) for i in range(n)]
    col_left = [sum(1 for i in range(n) if (i, j) in hidden) for j in range(m)]
    sets = {c: set() for c in cells}
    cur = [0] * len(cells)
    state = {"nodes": 0}

    def rec(k):
        state["nodes"] += 1
        if state["nodes"] > budget:
            raise _BudgetExceeded
        if k == len(cells):
            if all(r == 0 for r in row_res) and all(c == 0 for c in col_res):
                for idx, cell in enumerate(cells):
                    sets[cell].add(cur[idx])
            return
        i, j = cells[k]
        row_left[i] -= 1
        col_left[j] -= 1
        # 给本格赋 v，需为行/列中其余未赋值格各留至少 1
        hi = min(row_res[i] - row_left[i], col_res[j] - col_left[j])
        for v in range(1, hi + 1):
            row_res[i] -= v
            col_res[j] -= v
            cur[k] = v
            rec(k + 1)
            row_res[i] += v
            col_res[j] += v
        row_left[i] += 1
        col_left[j] += 1

    rec(0)
    return sets


def brute_solve(values, budget=1_500_000):
    """独立暴力求解：枚举候选格的所有子集，返回最优遮盖集合或 None。"""
    n = len(values)
    m = len(values[0])
    mandatory = {(i, j) for i in range(n) for j in range(m)
                 if values[i][j] in (1, 2)}
    candidates = sorted({(i, j) for i in range(n) for j in range(m)
                         if values[i][j] >= 3})
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            hidden = mandatory | set(combo)
            sets = brute_value_sets(values, hidden, budget)
            if all(len(sets[c]) >= 2 for c in hidden):
                return frozenset(hidden)
    return None


# ---------------------------------------------------------------------------
# 手算用例
# ---------------------------------------------------------------------------

def test_no_mandatory_returns_empty():
    assert find_hidden_cells([[0, 0], [0, 0]]) == frozenset()
    assert find_hidden_cells([[3, 4], [5, 6]]) == frozenset()
    assert find_hidden_cells([[0, 5, 3], [7, 0, 9], [4, 6, 0]]) == frozenset()


def test_single_one_no_solution():
    # 唯一的正数格被行合计唯一确定
    assert find_hidden_cells([[1, 0], [0, 0]]) is None


def test_all_ones_no_solution():
    # 行列合计全为 2 时，每个格子都只能是 1
    assert find_hidden_cells([[1, 1], [1, 1]]) is None


def test_all_twos_solution():
    # 行列合计全为 4，每格可取 1/2/3
    hidden = find_hidden_cells([[2, 2], [2, 2]])
    assert hidden == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_mandatory_forced_even_at_max_no_solution():
    # 第一行只有 1 一个正数，行合计即其本身
    assert find_hidden_cells([[1, 0], [3, 3]]) is None


def test_hide_all_solution():
    # 手算：必须遮盖 (0,0)；只有全部遮盖才可行
    hidden = find_hidden_cells([[1, 3], [3, 3]])
    assert hidden == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_zero_cells_stay_public():
    values = [[5, 1, 0], [2, 7, 3]]
    hidden = find_hidden_cells(values)
    assert hidden == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})
    assert (0, 2) not in hidden  # 零格公开
    assert (1, 2) not in hidden  # 该格被唯一确定，必须保持公开


def test_lexicographically_smallest_among_min_size():
    # 中心的 1 需要一个 2x2 遮盖块；字典序最小的追加是 (0,0),(0,1),(1,0)
    values = [[3, 3, 3],
              [3, 1, 3],
              [3, 3, 3]]
    hidden = find_hidden_cells(values)
    assert hidden == frozenset({(1, 1), (0, 0), (0, 1), (1, 0)})


def test_zero_column_makes_mandatory_unhideable():
    # 列合计公开后，(0,0) 被唯一确定为 1，无解
    assert find_hidden_cells([[1, 3], [3, 0]]) is None


def test_large_values_no_overflow():
    values = [[10**9, 1], [1, 10**9]]
    hidden = find_hidden_cells(values)
    assert hidden == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


# ---------------------------------------------------------------------------
# 与暴力枚举的随机交叉验证
# ---------------------------------------------------------------------------

def random_table(rng, n, m, lo, hi):
    return [[rng.randint(lo, hi) for _ in range(m)] for _ in range(n)]


@pytest.mark.parametrize("seed", range(60))
def test_forced_cells_match_brute(seed):
    rng = random.Random(seed)
    n = rng.choice([2, 2, 3, 3])
    m = rng.choice([2, 3, 3])
    values = random_table(rng, n, m, 0, 5)
    positive = {(i, j) for i in range(n) for j in range(m) if values[i][j] >= 1}
    mandatory = {c for c in positive if values[c[0]][c[1]] in (1, 2)}
    pool = sorted(positive - mandatory)
    keep = {c for c in pool if rng.random() < 0.5}
    hidden = mandatory | keep
    try:
        sets = brute_value_sets(values, hidden)
    except _BudgetExceeded:
        pytest.skip("枚举量过大")
    expected = {c for c in hidden if len(sets[c]) < 2}
    assert set(_forced_cells(values, hidden)) == expected


@pytest.mark.parametrize("seed", range(120))
def test_solver_matches_brute(seed):
    rng = random.Random(1000 + seed)
    n = rng.choice([2, 2, 2, 3, 3])
    m = rng.choice([2, 2, 3, 3])
    values = random_table(rng, n, m, 0, 4)
    try:
        expected = brute_solve(values)
    except _BudgetExceeded:
        pytest.skip("枚举量过大")
    assert find_hidden_cells(values) == expected


@pytest.mark.parametrize("seed", range(30))
def test_solver_4x4_validity(seed):
    rng = random.Random(2000 + seed)
    values = random_table(rng, 4, 4, 0, 3)
    hidden = find_hidden_cells(values)
    if hidden is None:
        try:
            assert brute_solve(values) is None
        except _BudgetExceeded:
            pytest.skip("枚举量过大")
        return
    # 用暴力枚举验证返回方案确实满足"每格至少两种取值"
    try:
        sets = brute_value_sets(values, hidden)
    except _BudgetExceeded:
        pytest.skip("枚举量过大")
    assert all(len(sets[c]) >= 2 for c in hidden)
    # 被遮盖的不能是零格
    for (i, j) in hidden:
        assert values[i][j] >= 1
