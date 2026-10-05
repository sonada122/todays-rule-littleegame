extends Node2D
## 《今天的规则》—— 核心原型（Stage 3.2：接入后端）
## 更新：
##   1. 结算界面 / 每日挑战 / 投稿界面 接入后端接口（经 Autoload `Net`）；
##   2. 离线可玩：后端不可达时自动回退本地 daily_queue.json；
##   3. 每日挑战通关后上报进度，结算页显示连续签到（断签提示）。

const MARGIN := 24.0
const TOP_BAND := 104.0
const BOTTOM_BAND := 124.0

enum { FLOOR, WALL, TARGET }
enum { PLAY, ALL_CLEAR, SUBMIT }

const DEFAULT_PARAMS := {
	"player_ignores_walls": false,
	"player_can_pull": false,
	"player_swap_with_wall": false,
	"player_push_distance": 1,
	"box_slides": false,
}

const NAMED_RULES := {
	"classic": {},
	"ghost": {"player_ignores_walls": true},
	"strong": {"player_push_distance": 2},
	"swap": {"player_swap_with_wall": true},
	"ice": {"box_slides": true},
	"pull": {"player_can_pull": true},
}

# 投稿界面的可调参数定义
const PARAM_DEFS := [
	{"key": "player_ignores_walls", "label": "穿墙：玩家可穿过墙壁", "kind": "bool"},
	{"key": "player_can_pull", "label": "拉箱：离开时拖动相邻箱子", "kind": "bool"},
	{"key": "player_swap_with_wall", "label": "换位：与内侧墙交换位置", "kind": "bool"},
	{"key": "player_push_distance", "label": "推力：一次最多推动格数", "kind": "int"},
	{"key": "box_slides", "label": "滑行：箱子推到撞墙才停", "kind": "bool"},
]

var levels: Array = []
var level_index := 0
var state := PLAY

var grid: Array = []
var boxes: Array = []
var player := Vector2i.ZERO
var params: Dictionary = {}
var rule_name := ""
var rule_desc := ""
var width := 0
var height := 0
var moves := 0
var won := false
var level_moves := {}

# 每日挑战 / 后端
var practice_levels: Array = []
var daily_level: Dictionary = {}
var daily_ready := false
var playing_daily := false
var today_day := 0
var streak := 0
var today_cleared := false
var net_msg := "正在连接每日挑战…"

# 投稿界面
var submit_params: Dictionary = {}
var submit_sel := 0
var submit_status := ""
var submit_preview: Dictionary = {}
var submit_busy := false

var font: Font
var _tile := 64.0
var _origin := Vector2.ZERO
var _uiscale := 1.0
var _top_band := TOP_BAND
var _bottom_band := BOTTOM_BAND

func _ready() -> void:
	font = ThemeDB.fallback_font
	submit_params = DEFAULT_PARAMS.duplicate()
	practice_levels = _load_levels()
	levels = practice_levels
	load_level(0)
	if get_viewport():
		get_viewport().size_changed.connect(_on_resize)
	var net := get_node_or_null("/root/Net")
	if net:
		net.today_result.connect(_on_today)
		net.progress_result.connect(_on_progress)
		net.submit_result.connect(_on_submit)
		net.fetch_today()

func _on_resize() -> void:
	queue_redraw()

func _load_levels() -> Array:
	for path in ["res://daily_queue.json", "res://levels_generated.json", "res://levels.json"]:
		if FileAccess.file_exists(path):
			var f := FileAccess.open(path, FileAccess.READ)
			if f == null:
				continue
			var parsed = JSON.parse_string(f.get_as_text())
			if typeof(parsed) == TYPE_DICTIONARY and parsed.has("items"):
				parsed = parsed["items"]
			if typeof(parsed) == TYPE_ARRAY and not parsed.is_empty():
				return parsed
	push_error("未找到任何关卡数据")
	return []

func _resolve_params(lv: Dictionary) -> Dictionary:
	var p := DEFAULT_PARAMS.duplicate()
	if lv.has("params") and typeof(lv["params"]) == TYPE_DICTIONARY:
		for k in lv["params"].keys():
			if p.has(k):
				p[k] = lv["params"][k]
	elif lv.has("rule") and NAMED_RULES.has(str(lv["rule"])):
		for k in NAMED_RULES[str(lv["rule"])].keys():
			p[k] = NAMED_RULES[str(lv["rule"])][k]
	return p

func load_level(idx: int) -> void:
	if levels.is_empty():
		return
	level_index = wrapi(idx, 0, levels.size())
	var lv: Dictionary = levels[level_index]
	params = _resolve_params(lv)
	rule_name = str(lv.get("name", ""))
	rule_desc = str(lv.get("desc", ""))
	var data: Array = lv["map"]
	height = data.size()
	width = String(data[0]).length()
	grid = []
	boxes = []
	moves = 0
	won = false
	for y in range(height):
		var line := String(data[y])
		var row := []
		for x in range(width):
			var ch := line[x]
			var t := FLOOR
			match ch:
				"#": t = WALL
				".": t = TARGET
				"*": t = TARGET; boxes.append(Vector2i(x, y))
				"$": boxes.append(Vector2i(x, y))
				"+": t = TARGET; player = Vector2i(x, y)
				"@": player = Vector2i(x, y)
				_: pass
			row.append(t)
		grid.append(row)
	queue_redraw()

# ---------------- 后端回调 ----------------

func _on_today(data: Dictionary, from_server: bool) -> void:
	if from_server and data.has("level"):
		daily_level = data["level"]
		daily_ready = true
		today_day = int(data.get("day", 0))
		streak = int(data.get("streak", 0))
		today_cleared = bool(data.get("cleared_today", false))
		net_msg = "在线 · 今日挑战已就绪（按 D 进入）"
	else:
		daily_ready = false
		net_msg = "离线模式 · 使用本地关卡（按 D 重试连接）"
	queue_redraw()

func _on_progress(ok: bool, data: Dictionary) -> void:
	if ok:
		streak = int(data.get("streak", streak))
		today_cleared = true
		net_msg = "进度已同步 · 连续签到 %d 天" % streak
	else:
		net_msg = "进度同步失败（离线，稍后自动重试）"
	queue_redraw()

func _on_submit(ok: bool, data: Dictionary) -> void:
	submit_busy = false
	if ok and bool(data.get("accepted", false)):
		submit_status = "✅ 通过！" + str(data.get("signature", "")) + " 可生成可解关卡"
		submit_preview = data.get("level", {})
	else:
		submit_status = "❌ " + str(data.get("reason", "被拒绝"))
		submit_preview = {}
	queue_redraw()

# ---------------- 输入 ----------------

func _unhandled_input(event: InputEvent) -> void:
	if state == SUBMIT:
		_submit_input(event)
		return

	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_R, KEY_ESCAPE:
				if state == ALL_CLEAR:
					state = PLAY
					load_level(levels.size() - 1)
				else:
					load_level(level_index)
				return
			KEY_D:
				_enter_daily()
				return
			KEY_T:
				state = SUBMIT
				submit_status = ""
				submit_preview = {}
				queue_redraw()
				return

	if state == ALL_CLEAR:
		if event.is_action_pressed("ui_accept"):
			if playing_daily:
				_enter_daily()
			else:
				level_moves.clear()
				state = PLAY
				load_level(0)
		return

	if event.is_action_pressed("ui_left"):
		_do_move(Vector2i(-1, 0))
	elif event.is_action_pressed("ui_right"):
		_do_move(Vector2i(1, 0))
	elif event.is_action_pressed("ui_up"):
		_do_move(Vector2i(0, -1))
	elif event.is_action_pressed("ui_down"):
		_do_move(Vector2i(0, 1))
	elif event.is_action_pressed("ui_accept") and won:
		if playing_daily:
			var net := get_node_or_null("/root/Net")
			if net and today_day > 0:
				net.post_progress(today_day, moves)
			state = ALL_CLEAR
			queue_redraw()
		elif level_index >= levels.size() - 1:
			state = ALL_CLEAR
			queue_redraw()
		else:
			load_level(level_index + 1)

func _enter_daily() -> void:
	var net := get_node_or_null("/root/Net")
	if not daily_ready:
		net_msg = "重新连接中…"
		if net:
			net.fetch_today()
		queue_redraw()
		return
	playing_daily = true
	levels = [daily_level]
	level_moves.clear()
	state = PLAY
	load_level(0)

func _exit_daily() -> void:
	playing_daily = false
	levels = practice_levels
	state = PLAY
	load_level(0)

# ---------------- 投稿界面输入 ----------------

func _submit_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo):
		# 方向键用 action 也行，但这里统一处理
		if event.is_action_pressed("ui_up"):
			submit_sel = wrapi(submit_sel - 1, 0, PARAM_DEFS.size()); queue_redraw()
		elif event.is_action_pressed("ui_down"):
			submit_sel = wrapi(submit_sel + 1, 0, PARAM_DEFS.size()); queue_redraw()
		return
	match event.keycode:
		KEY_ESCAPE:
			state = PLAY
			queue_redraw()
		KEY_UP:
			submit_sel = wrapi(submit_sel - 1, 0, PARAM_DEFS.size()); queue_redraw()
		KEY_DOWN:
			submit_sel = wrapi(submit_sel + 1, 0, PARAM_DEFS.size()); queue_redraw()
		KEY_LEFT:
			_adjust_submit(-1)
		KEY_RIGHT:
			_adjust_submit(1)
		KEY_ENTER, KEY_KP_ENTER, KEY_SPACE:
			_do_submit()

func _adjust_submit(delta: int) -> void:
	var d: Dictionary = PARAM_DEFS[submit_sel]
	var k := str(d["key"])
	if d["kind"] == "bool":
		submit_params[k] = not bool(submit_params[k])
	else:
		var v := int(submit_params[k]) + delta
		submit_params[k] = clampi(v, 1, 5)
	queue_redraw()

func _do_submit() -> void:
	if submit_busy:
		return
	var net := get_node_or_null("/root/Net")
	if net == null:
		submit_status = "❌ 无网络层"
		return
	submit_busy = true
	submit_status = "校验中…"
	net.submit_rule(submit_params, "", "")
	queue_redraw()

# ---------------- 移动逻辑 ----------------

func _do_move(dir: Vector2i) -> void:
	if won:
		return
	var back := player
	var target := player + dir
	if not _in_bounds(target):
		return
	if _is_wall(target):
		if params["player_ignores_walls"]:
			player = target
		elif params["player_swap_with_wall"] and _is_interior(target):
			grid[target.y][target.x] = FLOOR
			grid[player.y][player.x] = WALL
			player = target
		else:
			return
	elif _box_at(target) != -1:
		var n := _push_count(target, dir)
		if n <= 0:
			return
		boxes[_box_at(target)] = target + dir * n
		player = target
	else:
		player = target
	if params["player_can_pull"]:
		var behind := back - dir
		var bi := _box_at(behind)
		if bi != -1 and _box_at(back) == -1:
			boxes[bi] = back
	moves += 1
	_check_win()
	queue_redraw()

func _push_count(from: Vector2i, dir: Vector2i) -> int:
	var avail := 0
	var cur := from
	while true:
		var nxt := cur + dir
		if not _in_bounds(nxt) or _is_wall(nxt) or _box_at(nxt) != -1:
			break
		cur = nxt
		avail += 1
	if params["box_slides"]:
		return avail
	return min(avail, int(params["player_push_distance"]))

func _check_win() -> void:
	for y in range(height):
		for x in range(width):
			if grid[y][x] == TARGET and _box_at(Vector2i(x, y)) == -1:
				won = false
				return
	if not won:
		won = true
		level_moves[level_index] = moves

func _in_bounds(c: Vector2i) -> bool:
	return c.x >= 0 and c.y >= 0 and c.x < width and c.y < height

func _is_wall(c: Vector2i) -> bool:
	return grid[c.y][c.x] == WALL

func _is_interior(c: Vector2i) -> bool:
	return c.x > 0 and c.y > 0 and c.x < width - 1 and c.y < height - 1

func _box_at(c: Vector2i) -> int:
	return boxes.find(c)

# ---------------- 布局与绘制 ----------------

func _compute_layout(vp: Vector2) -> void:
	_uiscale = clampf(minf(vp.x / 1000.0, vp.y / 740.0), 0.55, 2.0)
	_top_band = TOP_BAND * _uiscale
	_bottom_band = BOTTOM_BAND * _uiscale
	var avail_w := vp.x - MARGIN * 2.0
	var avail_h := vp.y - _top_band - _bottom_band
	if width > 0 and height > 0:
		_tile = floor(minf(avail_w / float(width), avail_h / float(height)))
	else:
		_tile = 64.0
	_tile = clampf(_tile, 16.0, 120.0)
	var gw := width * _tile
	var gh := height * _tile
	_origin = Vector2((vp.x - gw) * 0.5, _top_band + (avail_h - gh) * 0.5)

func _draw() -> void:
	var vp := get_viewport_rect().size
	draw_rect(Rect2(Vector2.ZERO, vp), Color("#141821"))
	if font == null:
		return
	if state == SUBMIT:
		_draw_submit(vp)
		return
	if width == 0:
		return
	_compute_layout(vp)

	for y in range(height):
		for x in range(width):
			var pos := _origin + Vector2(x, y) * _tile
			var rect := Rect2(pos, Vector2(_tile, _tile))
			var t: int = grid[y][x]
			if t == WALL:
				draw_rect(rect, Color("#39404d"))
				draw_rect(rect.grow(-maxf(2.0, _tile * 0.06)), Color("#4a5262"))
			else:
				draw_rect(rect.grow(-1), Color("#20252f"))
				if t == TARGET:
					draw_circle(pos + Vector2(_tile, _tile) * 0.5, _tile * 0.16, Color("#5fd38a"))

	for b in boxes:
		var pos := _origin + Vector2(b.x, b.y) * _tile
		var rect := Rect2(pos, Vector2(_tile, _tile)).grow(-maxf(3.0, _tile * 0.11))
		var on_t: bool = grid[b.y][b.x] == TARGET
		draw_rect(rect, Color("#e2a24a") if on_t else Color("#c9832f"))

	var pp := _origin + Vector2(player.x + 0.5, player.y + 0.5) * _tile
	draw_circle(pp, _tile * 0.32, Color("#4aa3e0"))
	draw_circle(pp, _tile * 0.16, Color("#bfe0f5"))

	_draw_hud(vp)
	if state == ALL_CLEAR:
		_draw_all_clear(vp)

func _draw_hud(vp: Vector2) -> void:
	if levels.is_empty():
		return
	var m := MARGIN
	var wrap := vp.x - m * 2.0
	var fs_title := int(24 * _uiscale)
	var fs_sub := int(18 * _uiscale)
	var fs_body := int(16 * _uiscale)
	var fs_small := int(14 * _uiscale)

	var head := "第 %d / %d 关 · %s" % [level_index + 1, levels.size(), rule_name]
	if playing_daily:
		head = "今日挑战 · Day %d · %s" % [today_day, rule_name]
	draw_string(font, Vector2(m, m + fs_title), head,
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_title, Color("#f2f5fa"))

	# 副标题：优先难度信息，其次规则名；右侧显示联网状态
	var sub := ""
	var lv: Dictionary = levels[level_index]
	if lv.has("difficulty"):
		sub = "难度：%s    最快解法：%s 步" % [lv.get("difficulty", ""), lv.get("optimal_moves", "?")]
	else:
		sub = "本关规则：%s" % rule_name
	if playing_daily and streak > 0:
		sub += "    连续签到 %d 天" % streak
	draw_string(font, Vector2(m, m + fs_title + fs_sub + 8), sub,
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_sub, Color("#ffd479"))

	var desc_y := vp.y - _bottom_band + fs_body
	draw_multiline_string(font, Vector2(m, desc_y), rule_desc,
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_body, 3, Color("#aab4c4"))

	if won:
		_draw_win_banner(vp)
	else:
		var hint := "步数：%d   方向键移动 · R 重开 · D 今日挑战 · T 投稿" % moves
		draw_string(font, Vector2(m, vp.y - m * 0.6), hint,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_small, Color("#7d8798"))
		draw_string(font, Vector2(m, vp.y - m * 0.6 - fs_small - 4), net_msg,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_small, Color("#5c6675"))

func _draw_win_banner(vp: Vector2) -> void:
	var big := int(38 * _uiscale)
	var mid := int(19 * _uiscale)
	var pad := int(16 * _uiscale)
	var band_h := float(big + mid + pad * 3)
	var rh := clampf(band_h, 96.0, 220.0)
	var top := vp.y - rh
	draw_rect(Rect2(Vector2(0, top), Vector2(vp.x, rh)), Color(0.09, 0.16, 0.12, 0.97))
	draw_line(Vector2(0, top), Vector2(vp.x, top), Color("#5fd38a"), 3.0)
	var t1 := "过关！"
	var t2 := "按 空格 / 回车 进入下一关"
	if playing_daily:
		t1 = "今日挑战完成！"
		t2 = "按 空格 / 回车 同步进度并查看结果"
	elif level_index >= levels.size() - 1:
		t1 = "最后一关完成！"
		t2 = "按 空格 / 回车 查看结算"
	var y1 := top + pad + big
	draw_string(font, Vector2(0, y1), t1,
		HORIZONTAL_ALIGNMENT_CENTER, vp.x, big, Color("#5fd38a"))
	draw_string(font, Vector2(0, y1 + mid + pad), t2,
		HORIZONTAL_ALIGNMENT_CENTER, vp.x, mid, Color("#d6ffe6"))

func _draw_all_clear(vp: Vector2) -> void:
	draw_rect(Rect2(Vector2.ZERO, vp), Color(0, 0, 0, 0.84))
	var m := MARGIN
	var wrap := vp.x - m * 2.0
	var fs_big := int(40 * _uiscale)
	var fs_mid := int(20 * _uiscale)
	var fs_small := int(15 * _uiscale)
	var cy := vp.y * 0.30

	if playing_daily:
		draw_string(font, Vector2(m, cy), "今日挑战完成！",
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_big, Color("#ffd479"))
		draw_string(font, Vector2(m, cy + fs_big + 20),
			"连续签到 %d 天 · 本次 %d 步" % [streak, moves],
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#f2f5fa"))
		draw_string(font, Vector2(m, cy + fs_big + 20 + fs_mid + 14), net_msg,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_small, Color("#5fd38a"))
		draw_string(font, Vector2(m, cy + fs_big + 20 + (fs_mid + 14) * 2),
			"明天回来继续，别断了签到！",
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_small, Color("#aab4c4"))
		var cy2 := vp.y * 0.66
		draw_string(font, Vector2(m, cy2), "空格 / 回车 —— 再玩一次今日挑战",
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#5fd38a"))
		draw_string(font, Vector2(m, cy2 + fs_mid + 14), "Esc / R —— 回到练习模式",
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#aab4c4"))
		return

	var total := 0
	for k in level_moves.keys():
		total += level_moves[k]
	draw_string(font, Vector2(m, cy), "全部通关！",
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_big, Color("#ffd479"))
	draw_string(font, Vector2(m, cy + fs_big + 20),
		"你解开了全部 %d 关的规则" % levels.size(),
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#f2f5fa"))
	if total > 0:
		draw_string(font, Vector2(m, cy + fs_big + 20 + fs_mid + 10),
			"本次总步数：%d" % total,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#aab4c4"))
	var cy3 := vp.y * 0.66
	draw_string(font, Vector2(m, cy3), "空格 / 回车 —— 从头再玩一遍",
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#5fd38a"))
	draw_string(font, Vector2(m, cy3 + fs_mid + 14), "R —— 重玩最后一关",
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_mid, Color("#aab4c4"))

func _draw_submit(vp: Vector2) -> void:
	var m := MARGIN
	var wrap := vp.x - m * 2.0
	var fs_title := int(30 * _uiscale)
	var fs_row := int(20 * _uiscale)
	var fs_small := int(15 * _uiscale)

	draw_rect(Rect2(Vector2.ZERO, vp), Color("#0f131b"))
	draw_string(font, Vector2(m, m + fs_title), "投稿规则",
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_title, Color("#ffd479"))
	draw_string(font, Vector2(m, m + fs_title + fs_small + 6),
		"↑↓ 选择 · ←→ 调整 · 回车提交校验 · Esc 返回",
		HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_small, Color("#7d8798"))

	var y := vp.y * 0.22
	var row_h := fs_row * 2.0
	for i in range(PARAM_DEFS.size()):
		var d: Dictionary = PARAM_DEFS[i]
		var k := str(d["key"])
		var val_txt := ""
		if d["kind"] == "bool":
			val_txt = "开" if bool(submit_params[k]) else "关"
		else:
			val_txt = "%d 格" % int(submit_params[k])
		var sel := i == submit_sel
		var col := Color("#5fd38a") if sel else Color("#aab4c4")
		var mark := "▶ " if sel else "   "
		draw_string(font, Vector2(m + 20, y + fs_row),
			"%s%s" % [mark, str(d["label"])],
			HORIZONTAL_ALIGNMENT_LEFT, wrap - 200, fs_row, col)
		draw_string(font, Vector2(vp.x - m - 20, y + fs_row), val_txt,
			HORIZONTAL_ALIGNMENT_RIGHT, 180, fs_row, col)
		y += row_h

	var sy := vp.y - 200
	if submit_status != "":
		draw_string(font, Vector2(m, sy), submit_status,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_row, Color("#f2f5fa"))
		sy += fs_row + 12
	if not submit_preview.is_empty():
		var pv := "预览：%s · 难度 %s · 最快 %s 步" % [
			str(submit_preview.get("name", "")),
			str(submit_preview.get("difficulty", "")),
			str(submit_preview.get("optimal_moves", "?"))]
		draw_string(font, Vector2(m, sy), pv,
			HORIZONTAL_ALIGNMENT_CENTER, wrap, fs_row, Color("#ffd479"))
