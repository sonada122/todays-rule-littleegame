#!/usr/bin/env python3
"""《今天的规则》—— 分享卡片生成器（Stage 3）。

把当天关卡渲染成一张适合社交分享的 PNG：网格缩略图 + 规则名 + 描述 +
难度/最优步数 + 底部品牌。

【中文字体】：优先使用随项目打包的子集字体 assets/fonts/NotoSansSC-Subset.ttf
（由 tools/fetch_font.py 生成/子集化，约 1~4MB，随包分发，不依赖系统字体）。
若该文件不存在，则回退到系统 CJK 字体，最后回退到 DejaVu（无中文）。

命令行:
    python tools/share_card.py --day 1 --out share_day1.png
被后端 /api/share/{day}.png 以 render_bytes(level) 直接调用。
"""
import argparse
import io
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

W, H = 1080, 1350
BG = (20, 24, 33)
CARD = (28, 33, 43)
WALL = (74, 82, 98)
FLOOR = (32, 37, 47)
TARGET = (95, 211, 138)
BOX = (201, 131, 47)
BOX_ON = (226, 162, 74)
PLAYER = (74, 163, 224)
TEXT = (242, 245, 250)
DIM = (170, 180, 196)
GOLD = (255, 212, 121)

# 字体查找顺序：随包子集字体 → 系统 CJK → DejaVu
FONT_CANDIDATES = [
    os.path.join(ROOT, "assets", "fonts", "NotoSansSC-Subset.ttf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_FONT_CACHE = {}


def _font(size):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size)
                _FONT_CACHE[size] = f
                return f
            except OSError:
                continue
    f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _parse(level):
    grid = level["map"]
    boxes, targets, walls, player = set(), set(), set(), None
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == "#":
                walls.add((x, y))
            elif ch == ".":
                targets.add((x, y))
            elif ch == "$":
                boxes.add((x, y))
            elif ch == "*":
                boxes.add((x, y)); targets.add((x, y))
            elif ch == "@":
                player = (x, y)
            elif ch == "+":
                player = (x, y); targets.add((x, y))
    return grid, walls, targets, boxes, player


def render(level, out_path=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.text((W / 2, 90), "今天的规则", font=_font(56), fill=GOLD, anchor="mm")
    day = level.get("day", level.get("id", "?"))
    d.text((W / 2, 165), f"Day {day}", font=_font(30), fill=DIM, anchor="mm")

    d.rounded_rectangle([60, 230, W - 60, H - 360], radius=28, fill=CARD)

    grid, walls, targets, boxes, player = _parse(level)
    gh, gw = len(grid), len(grid[0])
    area_w, area_h = W - 240, 620
    tile = int(min(area_w / gw, area_h / gh))
    ox, oy = (W - gw * tile) // 2, 300
    for y in range(gh):
        for x in range(gw):
            px, py = ox + x * tile, oy + y * tile
            if (x, y) in walls:
                d.rectangle([px, py, px + tile, py + tile], fill=WALL)
            else:
                d.rectangle([px + 1, py + 1, px + tile - 1, py + tile - 1], fill=FLOOR)
                if (x, y) in targets:
                    r = tile * 0.16
                    cx, cy = px + tile / 2, py + tile / 2
                    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=TARGET)
    for (x, y) in boxes:
        px, py = ox + x * tile, oy + y * tile
        col = BOX_ON if (x, y) in targets else BOX
        m = tile * 0.12
        d.rounded_rectangle([px + m, py + m, px + tile - m, py + tile - m],
                            radius=8, fill=col)
    if player:
        px, py = ox + player[0] * tile, oy + player[1] * tile
        cx, cy = px + tile / 2, py + tile / 2
        r = tile * 0.32
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLAYER)

    name = level.get("name", "")
    desc = level.get("desc", "")
    diff = level.get("difficulty", "")
    om = level.get("optimal_moves", "?")
    ty = oy + gh * tile + 60
    d.text((W / 2, ty), name, font=_font(46), fill=TEXT, anchor="mm")
    d.text((W / 2, ty + 55), f"难度 {diff}  ·  最快 {om} 步",
           font=_font(30), fill=GOLD, anchor="mm")
    f = _font(28)
    line, lines = "", []
    for ch in list(desc):
        if f.getlength(line + ch) > W - 200:
            lines.append(line); line = ch
        else:
            line += ch
    if line:
        lines.append(line)
    ly = ty + 115
    for ln in lines[:3]:
        d.text((W / 2, ly), ln, font=f, fill=DIM, anchor="mm")
        ly += 42

    d.text((W / 2, H - 110), "把每个箱子推到目标点上",
           font=_font(26), fill=(125, 135, 152), anchor="mm")
    d.text((W / 2, H - 60), "TODAY'S RULE  ·  每日一规则",
           font=_font(30), fill=GOLD, anchor="mm")

    if out_path:
        img.save(out_path)
    return img


def render_bytes(level):
    buf = io.BytesIO()
    render(level).save(buf, format="PNG")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", type=int, default=1)
    ap.add_argument("--queue", default=os.path.join(ROOT, "daily_queue.json"))
    ap.add_argument("--out", default="share_card.png")
    args = ap.parse_args()
    with open(args.queue, encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items", data) if isinstance(data, dict) else data
    lv = next((it for it in items
               if int(it.get("day", it.get("id", 0))) == args.day), None)
    if not lv:
        raise SystemExit(f"找不到 Day {args.day}")
    render(lv, args.out)
    print(f"已生成 {args.out}（字体：{_font(24).getname()}）")


if __name__ == "__main__":
    main()
