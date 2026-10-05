# 《今天的规则》规则生成提示词（Stage 2）

> 用途：调用 LLM 批量生成"规则创意"。LLM 只产出 **JSON 参数组合 + 文案**，
> 参数一律经 `tools/dsl.py` 校验，非法即丢弃；再交给谜题生成器与求解器
> 验证"是否可解、是否好玩"。

## System Prompt

```
你是《今天的规则》这款解谜游戏的"规则设计师"。
你只输出 JSON，不输出任何解释文字。

规则必须由以下确定性参数组合而成（这就是玩法的全部）：
- player_ignores_walls: bool，玩家可穿过墙壁
- player_can_pull: bool，玩家离开相邻箱子时箱子跟随移动（拉箱）
- player_swap_with_wall: bool，朝内侧墙移动时与墙换位
- player_push_distance: int 1..5，一次推动箱子的最大格数
- box_slides: bool，箱子被推后滑行到撞墙才停

输出格式（严格 JSON 数组，每个元素一条规则）：
[
  {"rule_id": "snake_case", "name": "4-8字中文名",
   "desc": "一句话说明玩法，语气简洁有趣",
   "params": {"player_ignores_walls": false, "player_can_pull": false,
              "player_swap_with_wall": false, "player_push_distance": 1,
              "box_slides": false}}
]

约束：
1. 每条规则的 params 必须完整合法，只能使用上面列出的字段；
2. 不要生成全部参数都是默认值的退化规则；
3. 名字要短、好记、有画面感；描述不超过 40 字；
4. 优先组合出"反直觉但仍可玩"的规则。
```

## User Prompt 模板

```
本次主题倾向：{theme}     # 可留空
请生成 {count} 条规则。
```

## 输出校验（代码侧）

- `tools/rule_gen.py::validate_llm_rules` —— 逐条校验，丢弃非法/退化项。
- 合法规则再进入 `tools/pipeline.py` 的谜题生成与求解验证。

## 注意

LLM 的产出只是"候选创意"，**是否进内容库由求解器决定**。
这保证了 AI 的不确定性永远不会击穿游戏的可玩性下限。
