#!/usr/bin/env python3
"""《今天的规则》—— 规则生成器（Stage 2）。

A. 模板生成器（离线、确定性）：在 DSL 参数空间内枚举/采样"有意思"的组合，
   给出人类可读命名与描述。无 LLM 时先把管线跑通，也作为 LLM 输出兜底。
B. LLM 适配层（可插拔）：把系统提示词 + 参数 schema 交给大模型，要求严格
   JSON 返回。本文件只定义接口与本地校验，不绑定厂商——真正调用由宿主注入。

LLM 只产出"参数组合 + 文案"，参数一律经 dsl 校验，非法即丢。
"""
import itertools
import random

import dsl


def all_params():
    out = []
    for gw, pull, sw, sl in itertools.product([False, True], repeat=4):
        for dist in range(1, 6):
            p = {"player_ignores_walls": gw,
                 "player_can_pull": pull,
                 "player_swap_with_wall": sw,
                 "box_slides": sl,
                 "player_push_distance": dist}
            if dsl.is_trivial(p):
                continue
            out.append(dsl.normalize_params(p))
    return out


def name_for(params):
    p = dsl.normalize_params(params)
    tags = []
    if p["player_ignores_walls"]:
        tags.append("穿墙")
    if p["player_can_pull"]:
        tags.append("拉箱")
    if p["player_swap_with_wall"]:
        tags.append("换位")
    if p["box_slides"]:
        tags.append("滑行")
    if p["player_push_distance"] > 1:
        tags.append(f"推力x{p['player_push_distance']}")
    return "·".join(tags) if tags else "经典"


def make_rule(params, rule_id=None):
    p = dsl.normalize_params(params)
    return dsl.RuleSpec(
        rule_id=rule_id or dsl.signature(p),
        name=name_for(p),
        desc=dsl.describe(p),
        params=p,
    )


def sample_rules(count, seed=0, distinct_signature=True):
    rng = random.Random(seed)
    space = all_params()
    rng.shuffle(space)
    seen, picked = set(), []
    for p in space:
        sig = dsl.signature(p)
        if distinct_signature and sig in seen:
            continue
        seen.add(sig)
        picked.append(make_rule(p))
        if len(picked) >= count:
            break
    return picked


# ---------- B. LLM 适配层 ----------

SYSTEM_PROMPT = """你是《今天的规则》这款解谜游戏的"规则设计师"。
你只输出 JSON，不输出任何解释文字。

规则必须由以下确定性参数组合而成（这就是玩法的全部）：
{schema}

输出格式（严格 JSON 数组，每个元素一条规则）：
[
  {{"rule_id": "snake_case", "name": "4-8字中文名",
    "desc": "一句话说明玩法，语气简洁有趣",
    "params": {{...只看上面的参数...}}}}
]

约束：
1. 每条规则的 params 必须完整合法，只能使用 schema 中列出的字段；
2. 不要生成全部参数都是默认值的退化规则；
3. 名字要短、好记、有画面感；描述不超过 40 字；
4. 优先组合出"反直觉但仍可玩"的规则。
"""

SCHEMA_DOC = """- player_ignores_walls: bool，玩家可穿过墙壁
- player_can_pull: bool，玩家离开相邻箱子时箱子跟随移动（拉箱）
- player_swap_with_wall: bool，朝内侧墙移动时与墙换位
- player_push_distance: int 1..5，一次推动箱子的最大格数
- box_slides: bool，箱子被推后滑行到撞墙才停"""


def build_prompt(count=10, theme=""):
    prompt = SYSTEM_PROMPT.format(schema=SCHEMA_DOC)
    if theme:
        prompt += f"\n本次主题倾向：{theme}\n"
    prompt += f"\n请生成 {count} 条规则。"
    return prompt


def validate_llm_rules(payload):
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    if isinstance(payload, dict):
        payload = payload.get("rules", [])
    out = []
    for item in payload or []:
        try:
            p = dsl.normalize_params(item.get("params", {}))
            if dsl.is_trivial(p):
                continue
            out.append(dsl.RuleSpec(
                rule_id=str(item.get("rule_id") or dsl.signature(p)),
                name=str(item.get("name") or name_for(p)),
                desc=str(item.get("desc") or dsl.describe(p)),
                params=p,
            ))
        except (ValueError, AttributeError, TypeError):
            continue
    return out


if __name__ == "__main__":
    print(f"参数空间（非退化）：{len(all_params())} 组\n")
    for r in sample_rules(8, seed=7):
        print(f"- [{r.name}] {r.desc}")
        print(f"    {r.params}\n")
