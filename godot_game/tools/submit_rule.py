#!/usr/bin/env python3
"""《今天的规则》—— 玩家投稿规则校验器（Stage 3）。

玩家用一组 DSL 参数投稿一条规则，本脚本复用同一套 DSL / 谜题生成器 /
求解器来判断该规则是否"合法且能产出可解关卡"：

    1. 参数是否合法（dsl.normalize_params）；
    2. 在该规则约束下能否生成至少一个可解关卡（generator + solver）；
    3. 若可解，给出难度与示例关卡（可直接回传前端做预览）。

用法:
    python tools/submit_rule.py --params '{"box_slides": true, "player_push_distance": 2}' --name "滑行冰面"
    python tools/submit_rule.py --file my_rule.json
"""
import argparse
import json
import sys

import dsl
import generator
import solver


def review(params, name="", desc="", seed=0, attempts=150):
    """返回 (ok: bool, payload: dict)。"""
    try:
        p = dsl.normalize_params(params)
    except ValueError as e:
        return False, {"reason": f"参数非法：{e}"}
    if dsl.is_trivial(p):
        return False, {"reason": "退化规则：所有参数均为默认值，不改变玩法"}

    # 在该规则约束下尝试生成可解关卡（1~2 个箱子）。
    # 单一种子可能因随机放置偶发无解，故用多种子轮询提升判定鲁棒性。
    best = None
    for base in (seed, seed + 101, seed + 202, seed + 303):
        for nb in (2, 1):
            res = generator.generate(p, w=7, h=7, n_boxes=nb, seed=base,
                                     attempts=attempts)
            if res:
                best = res
                break
        if best:
            break
    if not best:
        return False, {"reason": "该规则下未能生成可解关卡（可能自相矛盾）"}

    lv, n = best
    lv = dict(lv)
    lv["name"] = name or dsl.signature(p)
    lv["desc"] = desc or dsl.describe(p)
    lv["params"] = p
    lv["optimal_moves"] = n
    lv["difficulty"] = solver.grade(n)
    return True, {
        "accepted": True,
        "signature": dsl.signature(p),
        "level": lv,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", help="JSON 字符串形式的规则参数")
    ap.add_argument("--file", help="包含 params 的 JSON 文件")
    ap.add_argument("--name", default="")
    ap.add_argument("--desc", default="")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            obj = json.load(fh)
        params = obj.get("params", obj)
        name = args.name or obj.get("name", "")
        desc = args.desc or obj.get("desc", "")
    elif args.params:
        params = json.loads(args.params)
        name, desc = args.name, args.desc
    else:
        print("请用 --params 或 --file 提供规则", file=sys.stderr)
        sys.exit(2)

    ok, payload = review(params, name=name, desc=desc, seed=args.seed)
    print(json.dumps({"ok": ok, **payload}, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
