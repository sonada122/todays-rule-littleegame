#!/usr/bin/env python3
"""《今天的规则》—— 规则 DSL（Stage 2 单一事实来源）。

一条"规则"不是一个形容词，而是一组【确定性参数】。LLM 未来只负责
生成这些参数的组合与命名，游戏逻辑/求解器完全按参数执行，从而保证
"可控、可解、可复现"。这是整条内容管线的地基。

参数空间（当前）：
    player_ignores_walls   bool   玩家可穿过墙壁
    player_can_pull        bool   玩家离开相邻箱子时，箱子跟随移动（拉箱）
    player_swap_with_wall  bool   朝内侧墙移动时与墙换位
    player_push_distance   int    一次推动箱子的最大格数 (1..5)
    box_slides             bool   箱子被推后滑行至撞墙才停

组合数 2*2*2*5*2 = 80（过滤退化后 79），从阶段一的 5 条命名规则扩展而来。

注意：早期版本用过 player_ignores_boxes（玩家穿箱而过），但该机制会使
箱子无法被移动、谜题必然无解，属于退化设计，已废弃并替换为 player_can_pull。
"""
from dataclasses import dataclass

DEFAULT_PARAMS = {
    "player_ignores_walls": False,
    "player_can_pull": False,
    "player_swap_with_wall": False,
    "player_push_distance": 1,
    "box_slides": False,
}

VALID_KEYS = set(DEFAULT_PARAMS)
INT_KEYS = {"player_push_distance"}

# 阶段一的 5 条命名规则的等价参数（向后兼容）
NAMED_RULES = {
    "classic": {},
    "ghost": {"player_ignores_walls": True},
    "strong": {"player_push_distance": 2},
    "swap": {"player_swap_with_wall": True},
    "ice": {"box_slides": True},
    "pull": {"player_can_pull": True},
}


@dataclass
class RuleSpec:
    rule_id: str
    name: str
    desc: str
    params: dict

    def as_dict(self):
        return {"rule_id": self.rule_id, "name": self.name,
                "desc": self.desc, "params": dict(self.params)}


def normalize_params(raw):
    """把不完整/带别名的参数字典补全为完整合法参数。"""
    params = dict(DEFAULT_PARAMS)
    if raw:
        for k, v in raw.items():
            if k not in VALID_KEYS:
                raise ValueError(f"未知规则参数: {k!r}")
            params[k] = v
    _validate(params)
    return params


def _validate(params):
    for k, v in params.items():
        if k in INT_KEYS:
            if isinstance(v, bool) or not isinstance(v, int) or not (1 <= v <= 5):
                raise ValueError(f"{k} 必须是 1..5 的整数，得到 {v!r}")
        else:
            if not isinstance(v, bool):
                raise ValueError(f"{k} 必须是布尔值，得到 {v!r}")


def params_from_level(level):
    """从关卡字典解析参数：优先 params，其次命名规则 id。"""
    if "params" in level and level["params"]:
        return normalize_params(level["params"])
    rule = level.get("rule", "classic")
    if rule not in NAMED_RULES:
        raise ValueError(f"未知命名规则: {rule!r}")
    return normalize_params(NAMED_RULES[rule])


def params_key(params):
    p = normalize_params(params)
    return "|".join(f"{k}={p[k]}" for k in sorted(DEFAULT_PARAMS))


def signature(params):
    """参数的可读签名，例如 ghost+swap。"""
    p = normalize_params(params)
    tags = []
    if p["player_ignores_walls"]:
        tags.append("ghost")
    if p["player_can_pull"]:
        tags.append("pull")
    if p["player_swap_with_wall"]:
        tags.append("swap")
    if p["box_slides"]:
        tags.append("ice")
    if p["player_push_distance"] > 1:
        tags.append(f"push{p['player_push_distance']}")
    return "+".join(tags) if tags else "classic"


def is_trivial(params):
    """明显不改变玩法的退化组合（用于过滤无趣规则）。"""
    p = normalize_params(params)
    return (not p["player_ignores_walls"] and not p["player_can_pull"]
            and not p["player_swap_with_wall"] and not p["box_slides"]
            and p["player_push_distance"] == 1)


def describe(params):
    """根据参数生成一句人类可读的规则描述（供模板/兜底使用）。"""
    p = normalize_params(params)
    parts = []
    if p["player_ignores_walls"]:
        parts.append("你可以自由穿过墙壁")
    if p["player_can_pull"]:
        parts.append("当你离开一个相邻的箱子时，它会跟你走一格")
    if p["player_swap_with_wall"]:
        parts.append("朝内侧的墙移动时会与它交换位置")
    if p["player_push_distance"] > 1:
        parts.append(f"你一次可以推动箱子最多 {p['player_push_distance']} 格")
    if p["box_slides"]:
        parts.append("箱子一旦被推动就滑行到撞上障碍才停")
    body = "；".join(parts) if parts else "箱子只能推一格，不能拉"
    return body + "。把每个箱子推到目标点上。"
