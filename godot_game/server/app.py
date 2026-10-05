#!/usr/bin/env python3
"""《今天的规则》—— 轻量后端（Stage 3）。

仅用 Python 标准库实现（零第三方依赖），提供：

  GET  /api/today?device_id=xxx        当天关卡（全球同款）+ 断签信息
  GET  /api/level/{day}                指定某天的关卡（严格不可提前偷看未来）
  POST /api/progress                   上报某天通关结果（步数）
  GET  /api/progress?device_id=xxx     拉取该设备的历史进度 + 连续签到
  GET  /api/share/{day}.png            生成并返回当天的分享卡片（PNG）

数据存储：SQLite（server/data.db），单文件、零运维。
关卡来源：daily_queue.json（由 tools/pipeline.py 生成）。

启动:
    python server/app.py --port 8080
"""
import argparse
import json
import os
import sqlite3
import sys
import datetime as dt
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

DB_PATH = os.path.join(HERE, "data.db")
QUEUE_PATH = os.path.join(ROOT, "daily_queue.json")

# 赛季起始日：Day 1 对应这一天
SEASON_START = dt.date(2026, 10, 5)


def load_queue():
    with open(QUEUE_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items", data) if isinstance(data, dict) else data
    by_day = {}
    for it in items:
        by_day[int(it.get("day", it.get("id", 0)))] = it
    return by_day


def today_day(today=None):
    today = today or dt.date.today()
    return (today - SEASON_START).days + 1


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS progress (
        device_id TEXT NOT NULL,
        day       INTEGER NOT NULL,
        moves     INTEGER NOT NULL,
        cleared_at TEXT NOT NULL,
        PRIMARY KEY (device_id, day)
    )""")
    return conn


def streak(conn, device_id, current_day):
    rows = conn.execute(
        "SELECT day FROM progress WHERE device_id=? ORDER BY day",
        (device_id,)).fetchall()
    days = {r[0] for r in rows}
    s = 0
    d = current_day
    while d in days:
        s += 1
        d -= 1
    # 今天还没通关但昨天通了，也不算断（留一天宽限）
    if s == 0 and (current_day - 1) in days:
        d = current_day - 1
        while d in days:
            s += 1
            d -= 1
    return s


class Handler(BaseHTTPRequestHandler):
    queue = {}

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send(self, data, ctype="application/octet-stream", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/api/today":
            day = today_day()
            lv = self.queue.get(day)
            if not lv:
                return self._json({"error": "今天暂无关卡"}, 404)
            dev = self._query().get("device_id", [""])[0]
            conn = db()
            st = streak(conn, dev, day) if dev else 0
            cleared = conn.execute(
                "SELECT moves FROM progress WHERE device_id=? AND day=?",
                (dev, day)).fetchone()
            conn.close()
            return self._json({
                "day": day,
                "level": lv,
                "streak": st,
                "cleared_today": bool(cleared),
                "today_moves": cleared[0] if cleared else None,
            })

        if path.startswith("/api/level/"):
            try:
                d = int(path.rsplit("/", 1)[1])
            except ValueError:
                return self._json({"error": "bad day"}, 400)
            if d > today_day():
                return self._json({"error": "尚未解锁"}, 403)
            lv = self.queue.get(d)
            if not lv:
                return self._json({"error": "无此关卡"}, 404)
            return self._json({"day": d, "level": lv})

        if path == "/api/progress":
            dev = self._query().get("device_id", [""])[0]
            if not dev:
                return self._json({"error": "缺少 device_id"}, 400)
            conn = db()
            rows = conn.execute(
                "SELECT day, moves, cleared_at FROM progress "
                "WHERE device_id=? ORDER BY day", (dev,)).fetchall()
            days = [{"day": r[0], "moves": r[1], "cleared_at": r[2]} for r in rows]
            st = streak(conn, dev, today_day())
            conn.close()
            return self._json({"device_id": dev, "days": days,
                               "streak": st, "total_cleared": len(days)})

        if path.startswith("/api/share/"):
            name = path.rsplit("/", 1)[1].replace(".png", "")
            try:
                d = int(name)
            except ValueError:
                return self._json({"error": "bad day"}, 400)
            lv = self.queue.get(d)
            if not lv:
                return self._json({"error": "无此关卡"}, 404)
            try:
                import share_card
                png = share_card.render_bytes(lv)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": f"分享卡片生成失败: {e}"}, 500)
            return self._send(png, ctype="image/png")

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(body or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)

        if path == "/api/submit_rule":
            import submit_rule
            params = req.get("params", {})
            try:
                ok, payload = submit_rule.review(
                    params, name=str(req.get("name", "")),
                    desc=str(req.get("desc", "")))
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "reason": f"校验异常: {e}"}, 500)
            return self._json({"ok": ok, **payload}, 200 if ok else 422)

        if path == "/api/progress":
            dev = str(req.get("device_id", ""))
            day = req.get("day")
            moves = req.get("moves")
            if not dev or not isinstance(day, int) or not isinstance(moves, int):
                return self._json({"error": "缺少 device_id/day/moves"}, 400)
            if day > today_day():
                return self._json({"error": "不能提交未来关卡"}, 403)
            conn = db()
            conn.execute(
                "INSERT OR REPLACE INTO progress VALUES (?,?,?,?)",
                (dev, day, moves, dt.datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            st = streak(conn, dev, today_day())
            conn.close()
            return self._json({"ok": True, "streak": st})

        return self._json({"error": "not found"}, 404)

    def _query(self):
        from urllib.parse import urlparse, parse_qs
        return parse_qs(urlparse(self.path).query)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--queue", default=QUEUE_PATH)
    args = ap.parse_args()
    Handler.queue = load_queue()
    print(f"后端启动: http://127.0.0.1:{args.port}  "
          f"（已载入 {len(Handler.queue)} 天关卡，今天=Day {today_day()}）")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
