# 今天的规则 · 完整工程（阶段一 → 三）

一款"每日一规则"的网格解谜游戏。玩家每关面对一条会改变玩法的特殊规则
（穿墙、拉箱、换位、滑行、多格推力……），先读懂规则，再利用规则解开谜题。

> **设计原则**：AI 只负责"创意生成"，程序负责"确定性验证"。
> 求解器是内容质量的守卫——任何不可解的候选一律丢弃。

## 操作

| 按键 | 作用 |
| --- | --- |
| 方向键 / WASD | 移动（碰到箱子即推动） |
| R | 重开本关 |
| 空格 / 回车 | 过关后进入下一关；全部通关后进入结算界面 |
| Esc | 备用重开键 |

- **全部通关**后进入结算界面，显示总步数，由玩家选择：空格/回车 从头再玩、R 重玩最后一关、Esc 停留。
- **窗口可自由缩放**，采用等比缩放（`canvas_items` + `keep`），网格与文字自适应，规则说明全宽换行。

---

## 一、游戏客户端（Godot 4.2+）

1. 安装 Godot 4.2+（标准版）。
2. `Import` → 选择 `project.godot` → 按 **F5**。
3. 引擎自动加载 `daily_queue.json`（回退 `levels_generated.json` / `levels.json`）。

`scripts/game.gd` 是一个纯数据驱动的 **规则 DSL 解释器**：每关自带
`params` 规则参数，引擎不再硬编码任何规则。

## 二、内容管线（Python，`tools/`）

| 文件 | 职责 |
| --- | --- |
| `dsl.py` | 规则参数 schema / 校验 / 命名映射（单一事实来源） |
| `solver.py` | BFS 求解 / 校验可解性 / 难度分级（与引擎语义一致） |
| `generator.py` | 规则约束下的谜题生成（拒绝采样，规则感知放置） |
| `rule_gen.py` | 模板规则生成 + LLM 输出校验 |
| `llm_client.py` | **真实 LLM 调用**（OpenAI 兼容接口，失败自动回退模板） |
| `mock_llm_server.py` | 本地 mock LLM 服务（无 key 时端到端自测） |
| `pipeline.py` | 生成→验证→分级→每日队列，保证产出 N 天 |
| `submit_rule.py` | **玩家投稿规则校验**（复用 DSL + 生成器 + 求解器） |
| `share_card.py` | 生成分享卡片 PNG |

### 规则参数空间（79 种非退化组合）

| 参数 | 类型 | 含义 |
| --- | --- | --- |
| `player_ignores_walls` | bool | 玩家可穿过墙壁 |
| `player_can_pull` | bool | 离开相邻箱子时箱子跟随移动（拉箱） |
| `player_swap_with_wall` | bool | 朝内侧墙移动时与墙换位 |
| `player_push_distance` | int 1..5 | 一次推动箱子的最大格数 |
| `box_slides` | bool | 箱子被推后滑行到撞墙才停 |

### 常用命令

```bash
cd tools
python pipeline.py --days 14 --seed 20261005       # 生产每日内容
python solver.py ../daily_queue.json               # 校验全部可解
python submit_rule.py --params '{"box_slides": true}' --name "滑行"   # 校验投稿
python share_card.py --day 1 --out share_day1.png  # 生成分享卡片

# 真实 LLM（配置任一 OpenAI 兼容服务）
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat
python llm_client.py --count 10 --theme "冰与火"
```

## 三、阶段三：LLM 接入 / 后端 / 投稿

### 1. 真实 LLM 调用（`llm_client.py`）

- 对接任意 **OpenAI 兼容** Chat Completions 接口（OpenAI / DeepSeek / 通义 / 本地 vLLM / mock）。
- LLM 只产出"JSON 参数组合 + 文案"，经 `rule_gen.validate_llm_rules` 校验，非法即丢。
- 无 key 或调用失败时**自动回退**模板生成器，内容管线永不中断。
- `mock_llm_server.py` 提供本地 mock，用于无 key 端到端验证。

### 2. 后端（`server/app.py`，纯标准库 + SQLite）

| 接口 | 说明 |
| --- | --- |
| `GET /api/today?device_id=` | 当天关卡（全球同款）+ 连续签到 + 今日是否已通关 |
| `GET /api/level/{day}` | 指定关卡；未解锁的未来关卡返回 403（防偷看） |
| `POST /api/progress` | 上报某天通关步数（body: device_id/day/moves） |
| `GET /api/progress?device_id=` | 历史进度 + 连续签到天数 streak |
| `GET /api/share/{day}.png` | 生成并返回当天分享卡片 |

```bash
python server/app.py --port 8080
```

赛季起始日 `SEASON_START=2026-10-05` 对应 Day 1（可在 `app.py` 调整）。

### 3. 玩家投稿（`submit_rule.py`）

玩家用一组 DSL 参数投稿规则，系统复用**同一套** DSL / 生成器 / 求解器判断：

1. 参数是否合法；
2. 该规则下能否生成至少一个可解关卡；
3. 若可解，返回难度与示例关卡（供前端预览）。

### 4. 客户端 ↔ 后端对接（本次新增）

`scripts/net.gd`（Autoload 节点名 `Net`）封装了所有网络交互：

- **设备标识**：首次运行生成 `device_id` 并持久化到 `user://config.cfg`；
- **每日挑战**：`Net.fetch_today()` 拉取当天关卡 + 连续签到；
- **进度同步**：每日挑战通关后 `Net.post_progress(day, moves)` 上报；
- **投稿**：`Net.submit_rule(params, name, desc)` 提交规则校验；
- **离线可玩**：后端不可达时自动回退本地 `daily_queue.json`，游戏照常玩，
  联网后按 D 重试、进度会在下次通关时补报。

游戏内按键扩展：

| 按键 | 作用 |
| --- | --- |
| D | 进入 / 重连"今日挑战"（后端每日关卡） |
| T | 打开"投稿规则"界面（←→ 调参、回车提交校验） |
| Esc | 结算页 / 投稿页返回 |

结算页现在区分「练习模式全部通关」与「今日挑战完成」，后者显示连续签到
天数并提示断签。

### 5. 分享卡片中文字体（本次新增）

分享卡片曾依赖系统 CJK 字体，生产机器未必安装。现将字体**随项目打包**：

```bash
python tools/fetch_font.py            # 生成子集字体（约 4MB）
python tools/fetch_font.py --full     # 或直接拷贝完整字体（约 20MB）
```

- `fetch_font.py` 优先使用本地 CJK 字体，否则联网下载 Noto Sans SC；
- 用 fontTools 做**可变字体实例化 + 子集化**（ASCII + GB2312 常用字 +
  中文标点），把 ~20MB 压到 ~4MB；
- 产物 `assets/fonts/NotoSansSC-Subset.ttf` 随包分发；
- `share_card.py` 优先加载该字体，回退系统字体，最后回退 DejaVu。

### 6. 后端投稿接口（本次新增）

`POST /api/submit_rule`（body: `{params, name, desc}`）复用同一套
DSL / 生成器 / 求解器校验玩家投稿：合法返回 `{ok:true, signature, level}`，
退化或非法返回 `{ok:false, reason}`（HTTP 422）。

---

## 目录结构

```
godot_game/
├── project.godot
├── scenes/Main.tscn
├── scripts/
│   ├── game.gd                # 数据驱动的规则 DSL 解释器 + 每日/结算/投稿 UI
│   └── net.gd                 # 网络层（Autoload "Net"）：后端对接 / 离线回退
├── assets/fonts/
│   └── NotoSansSC-Subset.ttf  # 随包子集中文字体（分享卡片用）
├── levels.json                # 手工关卡（兜底）
├── daily_queue.json           # 每日队列（管线产出）
├── levels_generated.json      # 内容池（管线产出）
├── prompts/
│   └── rule_system_prompt.md  # LLM 规则生成提示词模板
├── requirements.txt
├── server/
│   └── app.py                 # 后端：每日分发/进度/断签/分享卡片/投稿校验
└── tools/
    ├── dsl.py  solver.py  generator.py  rule_gen.py
    ├── llm_client.py  mock_llm_server.py
    ├── pipeline.py  submit_rule.py  share_card.py  fetch_font.py
    └── ...
```

## 依赖

- 客户端：Godot 4.2+
- 工具链 / 后端：Python 3.10+，`pip install -r requirements.txt`
  （`requests` + `Pillow`；后端仅用标准库）

## 后续可扩展

- 前端结算页 / 投稿 UI 接入后端接口（当前后端已就绪，客户端为本地版）。
- 分享卡片接入中文字体（生产环境）。
- 把"每日固定一关"扩展为"每周规则季"。
