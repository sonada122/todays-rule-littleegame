#!/usr/bin/env python3
"""《今天的规则》—— 内容管线（Stage 2）。

把"规则生成 → 谜题生成 → 求解验证 → 难度分级 → 每日队列"串成一条
可重复运行的生产线：

    rules = rule_gen.sample_rules(N)           # 规则创意（未来可换成 LLM）
    for rule in rules:
        levels = generator.generate_many(...)  # 在规则约束下构造谜题
        keep only levels that pass solver      # 求解器质量下限
    assemble daily_queue.json                  # 每日一关，全球同款

用法:
    python tools/pipeline.py --days 14 --seed 20261005
"""
import argparse
import json
import os
import sys
from collections import deque

import dsl
import generator
import rule_gen
import solver

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _make_day(i, days, rule, seed, attempts_per_rule):
    """为第 i 天生成一关；产不出则返回 None。"""
    target = "easy" if i < 3 else ("medium" if i < days - 3 else "hard")
    band = {"easy": (1, 5), "medium": (6, 12), "hard": (13, 40)}[target]
    n_boxes = 1 if i < 3 else 2
    size = 7
    # 先按目标难度区间尝试，再放宽区间、缩小网格/箱数兜底
    plans = [(band, size, n_boxes), ((1, 80), size, n_boxes), ((1, 80), 7, 1)]
    for k, (bnd, sz, nb) in enumerate(plans):
        res = generator.generate(
            rule.params, w=sz, h=sz, n_boxes=nb,
            seed=seed + i * 100 + k, attempts=attempts_per_rule,
            min_moves=bnd[0], max_moves=bnd[1])
        if res:
            lv, ld = res
            lv = dict(lv)
            lv["params"] = rule.params
            lv["id"] = i + 1
            lv["day"] = i + 1
            lv["rule_id"] = rule.rule_id
            lv["name"] = rule.name
            lv["desc"] = rule.desc
            lv["optimal_moves"] = ld
            lv["difficulty"] = solver.grade(ld)
            return lv
    return None


def build_daily_queue(days=14, seed=0, attempts_per_rule=40):
    """保证产出恰好 days 天：某条规则产不出就换下一条规则重试。"""
    # 多取一些候选规则备用
    rules = rule_gen.sample_rules(days * 3, seed=seed)
    queue = []
    ri = 0
    while len(queue) < days and ri < len(rules):
        rule = rules[ri]
        ri += 1
        lv = _make_day(len(queue), days, rule, seed, attempts_per_rule)
        if lv is None:
            continue
        queue.append(lv)
    return queue


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=20261005)
    ap.add_argument("--out", default=os.path.join(ROOT, "daily_queue.json"))
    ap.add_argument("--pool", default=os.path.join(ROOT, "levels_generated.json"))
    args = ap.parse_args()

    queue = build_daily_queue(days=args.days, seed=args.seed)

    # 每日队列
    payload = {"seed": args.seed, "days": len(queue), "items": queue}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    # 内容池（可与队列相同结构，供引擎直接加载）
    with open(args.pool, "w", encoding="utf-8") as fh:
        json.dump(queue, fh, ensure_ascii=False, indent=2)

    print(f"生成 {len(queue)} 天关卡：")
    dist = {}
    for it in queue:
        dist[it["difficulty"]] = dist.get(it["difficulty"], 0) + 1
        print(f"  Day {it['day']:>2}  {it['name']:<10} "
              f"sig={dsl.signature(it['params']):<18} "
              f"最优解={it['optimal_moves']:>3} 步  [{it['difficulty']}]")
    print(f"\n难度分布：{dist}")
    print(f"写入 {args.out}")
    print(f"写入 {args.pool}")


if __name__ == "__main__":
    main()
