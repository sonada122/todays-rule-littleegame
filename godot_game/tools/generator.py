#!/usr/bin/env python3
"""《今天的规则》—— 谜题生成器（Stage 2）。

策略：**先定规则，再在规则约束下构造谜题**（而非先造谜题再贴规则）。
流程：
    1. 在 [w x h] 网格内随机放置 n 个箱子、n 个目标、1 个玩家、若干内墙；
    2. 用求解器求解；
    3. 保留"可解且难度落在目标区间"的候选，其余丢弃。

这是"生成 + 求解验证"的拒绝采样法：生成再多，进不了内容库的也必须
通过求解器——质量下限由求解器而非 LLM 守住。
"""
import random

import dsl
import solver


def _render(w, h, walls, targets, boxes, player):
    rows = []
    for y in range(h):
        line = []
        for x in range(w):
            c = (x, y)
            if c == player:
                line.append("+" if c in targets else "@")
            elif c in boxes:
                line.append("*" if c in targets else "$")
            elif c in walls:
                line.append("#")
            elif c in targets:
                line.append(".")
            else:
                line.append(" ")
        rows.append("".join(line))
    return rows


def generate_once(params, w, h, n_boxes, rng, max_interior_walls=4):
    interior = [(x, y) for x in range(1, w - 1) for y in range(1, h - 1)]
    if len(interior) < n_boxes * 2 + 1:
        return None
    p = dsl.normalize_params(params)
    all_cells = interior[:]
    rng.shuffle(all_cells)

    # 规则感知的目标放置：滑行箱子只能停在"紧邻障碍/边界"的格子，因此
    # 该规则下目标必须落在贴边内圈，否则几乎必然无解。其他规则目标可任意放。
    if p["box_slides"]:
        # 滑行箱只能停在紧邻障碍/边界的格子；这里提供两层候选：
        # 先试贴边内圈，再放宽到"与任意墙相邻"的格，提升生成成功率。
        ring = [c for c in all_cells
                if c[0] == 1 or c[0] == w - 2 or c[1] == 1 or c[1] == h - 2]
        target_pool = ring if len(ring) >= n_boxes else all_cells
    else:
        target_pool = all_cells
    if len(target_pool) < n_boxes:
        return None
    targets = set(target_pool[:n_boxes])

    rest = [c for c in all_cells if c not in targets]
    boxes = set(rest[:n_boxes])
    rest = rest[n_boxes:]
    if not rest:
        return None
    player = rng.choice(rest)

    walls = set()
    wall_pool = [c for c in interior
                 if c != player and c not in boxes and c not in targets]
    rng.shuffle(wall_pool)
    n_walls = min(max_interior_walls, max(0, len(wall_pool) // 4))
    for c in wall_pool[:rng.randint(0, n_walls)]:
        walls.add(c)

    lv = {"map": _render(w, h, walls, targets, boxes, player), "params": p}
    try:
        n = solver.solve(lv)
    except ValueError:
        return None
    if n is None or n == 0:
        return None
    return lv, n


def generate(params, w=7, h=7, n_boxes=2, seed=0, attempts=120,
             min_moves=1, max_moves=40):
    """返回第一个满足难度区间的关卡；若都不满足区间，返回最优的候选。"""
    rng = random.Random(seed)
    best = None
    for _ in range(attempts):
        res = generate_once(params, w, h, n_boxes, rng)
        if res is None:
            continue
        lv, n = res
        if min_moves <= n <= max_moves:
            return lv, n
        if best is None or n > best[1]:
            best = res
    return best


def generate_many(params, count, seed=0, **kw):
    out, seen, i, guard = [], set(), 0, 0
    while len(out) < count and guard < count * 50:
        res = generate(params, seed=seed + i, **kw)
        guard += 1
        i += 1
        if not res:
            continue
        lv, n = res
        key = "".join(lv["map"])
        if key in seen:
            continue
        seen.add(key)
        lv["_moves"] = n
        out.append(lv)
    return out
