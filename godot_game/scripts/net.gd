extends Node
## 《今天的规则》—— 网络层（Autoload，节点名 Net）
##
## 封装与后端的 HTTP 交互、设备标识持久化、离线回退。所有请求失败都不应
## 影响游戏可玩性：客户端始终能用本地 daily_queue.json 离线游玩。
##
## 用法（其它脚本）：
##     Net.today_result.connect(_on_today)
##     Net.fetch_today()

signal today_result(data: Dictionary, from_server: bool)
signal progress_result(ok: bool, data: Dictionary)
signal submit_result(ok: bool, data: Dictionary)

const CONFIG_PATH := "user://config.cfg"
const DEFAULT_BASE := "http://127.0.0.1:8080"

var base_url := DEFAULT_BASE
var device_id := ""
var online := false

func _ready() -> void:
	_load_config()
	if device_id == "":
		device_id = _gen_device_id()
		_save_config()

func _load_config() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(CONFIG_PATH) == OK:
		base_url = str(cfg.get_value("net", "base_url", DEFAULT_BASE))
		device_id = str(cfg.get_value("net", "device_id", ""))

func _save_config() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("net", "base_url", base_url)
	cfg.set_value("net", "device_id", device_id)
	cfg.save(CONFIG_PATH)

func _gen_device_id() -> String:
	var rng := RandomNumberGenerator.new()
	rng.randomize()
	return "%08x%08x" % [rng.randi(), rng.randi()]

func _request(method: int, url: String, body: Dictionary, cb: Callable) -> void:
	var http := HTTPRequest.new()
	http.timeout = 10.0
	add_child(http)
	http.request_completed.connect(
		func(_result: int, code: int, _headers: PackedStringArray, data: PackedByteArray) -> void:
			http.queue_free()
			var parsed: Dictionary = {}
			var txt := data.get_string_from_utf8()
			if txt != "":
				var j = JSON.parse_string(txt)
				if typeof(j) == TYPE_DICTIONARY:
					parsed = j
			cb.call(code >= 200 and code < 300, code, parsed)
	)
	var headers := PackedStringArray(["Content-Type: application/json"])
	var payload := "" if method == HTTPClient.METHOD_GET else JSON.stringify(body)
	var err := http.request(url, headers, method, payload)
	if err != OK:
		http.queue_free()
		cb.call(false, 0, {})

# ---- 对外接口 ----

func fetch_today() -> void:
	var url := "%s/api/today?device_id=%s" % [base_url, device_id]
	_request(HTTPClient.METHOD_GET, url, {}, func(ok: bool, _code: int, data: Dictionary) -> void:
		online = ok
		today_result.emit(data, ok))

func post_progress(day: int, moves: int) -> void:
	var url := "%s/api/progress" % base_url
	var body := {"device_id": device_id, "day": day, "moves": moves}
	_request(HTTPClient.METHOD_POST, url, body, func(ok: bool, _code: int, data: Dictionary) -> void:
		progress_result.emit(ok, data))

func submit_rule(params: Dictionary, rule_name: String, desc: String) -> void:
	var url := "%s/api/submit_rule" % base_url
	var body := {"params": params, "name": rule_name, "desc": desc}
	_request(HTTPClient.METHOD_POST, url, body, func(ok: bool, _code: int, data: Dictionary) -> void:
		submit_result.emit(ok, data))
