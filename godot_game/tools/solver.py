#!/usr/bin/env python3
"""《今天的规则》—— 关卡求解 / 校验器（Stage 2）。"""
import json
import sys
from collections import deque

import dsl

DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def parse(level):
    grid = level["map"]
    h = len(grid)
    w = len(grid[0])
    walls, targets, boxes, player = set(), set(), set(), None
    for y, row in enumerate(grid):
        if len(row) != w:
            raise ValueError(f"第 {y} 行宽度 {len(row)} != {w}")
        for x, ch in enumerate(row):
            c = (x, y)
            if ch == "#":
                walls.add(c)
            elif ch == ".":
                targets.add(c)
            elif ch == "$":
                boxes.add(c)
            elif ch == "*":
                boxes.add(c); targets.add(c)
            elif ch == "@":
                player = c
            elif ch == "+":
                player = c; targets.add(c)
            elif ch == " ":
                pass
            else:
                raise ValueError(f"非法字符 {ch!r} 于 {c}")
    if player is None:
        raise ValueError("缺少玩家 @")
    if len(boxes) != len(targets):
        raise ValueError(f"箱子数 {len(boxes)} != 目标数 {len(targets)}")
    if not boxes:
        raise ValueError("至少需要 1 个箱子")
    return w, h, frozenset(walls), frozenset(targets), frozenset(boxes), player


def solve(level, limit=400_000):
    w, h, walls0, targets, boxes0, player0 = parse(level)
    p = dsl.params_from_level(level)
    pull = p["player_can_pull"]

    def inb(c):
        return 0 <= c[0] < w and 0 <= c[1] < h

    start = (player0, boxes0, walls0)
    dist = {start: 0}
    q = deque([start])
    while q:
        pos, boxes, walls = q.popleft()
        d0 = dist[(pos, boxes, walls)]
        if boxes == targets:
            return d0
        for dx, dy in DIRS:
            d = (dx, dy)
            t = (pos[0] + dx, pos[1] + dy)
            if not inb(t):
                continue
            new_walls = walls
            if t in walls:
                if p["player_ignores_walls"]:
                    pass
                elif p["player_swap_with_wall"]:
                    if t[0] == 0 or t[1] == 0 or t[0] == w - 1 or t[1] == h - 1:
                        continue
                    new_walls = frozenset((walls - {t}) | {pos})
                else:
                    continue
            if t in boxes:
                avail, cur = 0, t
                while True:
                    nxt = (cur[0] + dx, cur[1] + dy)
                    if not inb(nxt) or nxt in new_walls or nxt in boxes:
                        break
                    cur = nxt
                    avail += 1
                move = avail if p["box_slides"] else min(avail, p["player_push_distance"])
                if move == 0:
                    continue
                nb = frozenset((boxes - {t}) | {(t[0] + dx * move, t[1] + dy * move)})
            else:
                nb = boxes
            np = t
            # 拉箱：玩家离开后，其身后的箱子跟到玩家原来的格子
            if pull:
                back = (pos[0] - dx, pos[1] - dy)
                if back in nb and back not in new_walls:
                    nb = frozenset((nb - {back}) | {pos})
            st = (np, nb, new_walls)
            if st not in dist:
                dist[st] = d0 + 1
                if len(dist) > limit:
                    return None
                q.append(st)
    return None


def grade(moves):
    if moves is None:
        return "invalid"
    if moves <= 5:
        return "easy"
    if moves <= 12:
        return "medium"
    return "hard"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "levels.json"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("items", data.get("days", data.get("levels", [])))
    ok = True
    for lv in data:
        try:
            n = solve(lv)
        except Exception as e:  # noqa: BLE001
            print(f"[ERR ] #{str(lv.get('id','?')):>3} {str(lv.get('name','')):<12} {e}")
            ok = False
            continue
        if n is None:
            print(f"[FAIL] #{str(lv.get('id','?')):>3} {str(lv.get('name','')):<12} 无解或超上限")
            ok = False
        else:
            print(f"[ OK ] #{str(lv.get('id','?')):>3} {str(lv.get('name','')):<12} "
                  f"sig={dsl.signature(dsl.params_from_level(lv)):<18} "
                  f"最优解={n:>3} 步 ({grade(n)})")
    print("\n全部通过 ✅" if ok else "\n存在问题 ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
