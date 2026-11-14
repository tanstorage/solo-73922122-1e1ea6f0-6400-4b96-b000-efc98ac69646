"""病例交叉表遮盖核心算法。

规则（与需求一一对应）：
  * 值为 1 或 2 的格子必须遮盖；值为 0 的格子必须公开；
  * 从其余正数格（值 >= 3）中追加最少数量的遮盖；
  * 追加数量相同时，把追加格坐标按（行、列）顺序排列，取字典序最小的方案；
  * 交付表保留行合计、列合计与总计；每个被遮盖格在与公开数值及合计
    相容的正整数赋值中，至少有两种不同取值。

理论要点
--------
把被遮盖格看作二部图（行节点—列节点）上的边。公开格取值固定，行/列合计
固定，则被遮盖格的所有相容赋值 = 运输多面体 {x >= 1, 行和/列和守恒} 的整数点。
以真实赋值 t 为初始可行流（每条被遮盖边先预流下界 1），其余可行流与 t 之差
恰好是残量图中的环流。因此对被遮盖格 e=(i,j)：

  * e 能取到 t_e + 1  <=>  残量图（删去 e 的两条弧）中存在 C_j -> R_i 路径；
  * e 能取到 t_e - 1  <=>  t_e >= 2 且残量图中存在 R_i -> C_j 路径。

e 被唯一确定（违反交付要求）当且仅当两个方向都不可行。该判定只需两次可达性
查询，全部在整数上进行，无需任何浮点运算。

单调性：若某格在"全部正数格都遮盖"时仍被唯一确定，则它在任何更小的遮盖集合
中（只要被遮盖）也被唯一确定——因为可行集合只会缩小。因此：
  * 必须遮盖格（1/2）若在最大遮盖下被唯一确定 => 整体无解；
  * 在最大遮盖下被唯一确定的候选格（>=3）永远不能进入方案。
"""

from itertools import combinations

# 交付表中被遮盖格的显示标记
HIDE_MARK = "*"


def find_hidden_cells(values):
    """计算需要遮盖的格子集合。

    参数:
        values: n x m 的非负整数矩阵（list[list[int]]）。

    返回:
        frozenset[(i, j)] 应遮盖的坐标（0 起始，按行优先排序后可展示）；
        若无任何方案满足条件则返回 None。
    """
    n = len(values)
    m = len(values[0])
    mandatory = {(i, j) for i in range(n) for j in range(m)
                 if values[i][j] in (1, 2)}
    if not mandatory:
        # 没有值为 1/2 的格子：无需任何遮盖，原表即可交付。
        return frozenset()

    positive = {(i, j) for i in range(n) for j in range(m)
                if values[i][j] >= 1}

    # 最大遮盖（所有正数格）下仍被唯一确定的格子
    forced_at_max = set(_forced_cells(values, positive))
    if forced_at_max & mandatory:
        return None  # 必须遮盖的格子无法避免被反推 => 无解

    # 可追加遮盖的候选格：值 >= 3 且在最大遮盖下不被唯一确定
    candidates = sorted(positive - mandatory - forced_at_max)

    # 按追加数量从小到大、同数量按坐标字典序枚举，首个可行即所求
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            hidden = mandatory | set(combo)
            if not _forced_cells(values, hidden):
                return frozenset(hidden)
    return None


def _forced_cells(values, hidden):
    """返回 hidden 中被唯一确定（只有一种相容正整数取值）的格子列表。

    values: 原始非负整数矩阵；hidden: 被遮盖格坐标集合（需为可行情形，
    即至少存在一种相容赋值——真实表本身就是其一）。
    """
    n = len(values)
    m = len(values[0])
    S = n + m          # 源点编号
    T = n + m + 1      # 汇点编号

    row_sum = [0] * n  # 各行被遮盖格真值之和
    col_sum = [0] * m
    row_deg = [0] * n  # 各行被遮盖格数量
    col_deg = [0] * m
    for (i, j) in hidden:
        row_sum[i] += values[i][j]
        col_sum[j] += values[i][j]
        row_deg[i] += 1
        col_deg[j] += 1
    # 预流每条被遮盖边下界 1 之后，行/列节点剩余的供需量
    rem_row = [row_sum[i] - row_deg[i] for i in range(n)]
    rem_col = [col_sum[j] - col_deg[j] for j in range(m)]

    forced = []
    for (ei, ej) in hidden:
        # 构建删去格子 (ei, ej) 两条弧后的残量图邻接表（只保留容量 >= 1 的弧）
        adj = [[] for _ in range(n + m + 2)]
        for (i, j) in hidden:
            if i == ei and j == ej:
                continue
            u, v = i, n + j
            adj[u].append(v)                 # 正向弧：容量无限
            if values[i][j] >= 2:
                adj[v].append(u)             # 反向弧：容量 = 真值 - 1 >= 1
        for i in range(n):
            if rem_row[i] >= 1:
                adj[i].append(S)             # R_i -> S（S 无出弧，自然终止）
        for j in range(m):
            if rem_col[j] >= 1:
                adj[T].append(n + j)         # T -> C_j（T 无入弧）

        can_increase = _reachable(adj, n + ej, ei)
        can_decrease = values[ei][ej] >= 2 and _reachable(adj, ei, n + ej)
        if not can_increase and not can_decrease:
            forced.append((ei, ej))
    return forced


def _reachable(adj, src, dst):
    """有向图可达性（DFS）。"""
    seen = bytearray(len(adj))
    seen[src] = 1
    stack = [src]
    while stack:
        u = stack.pop()
        for w in adj[u]:
            if not seen[w]:
                if w == dst:
                    return True
                seen[w] = 1
                stack.append(w)
    return False
