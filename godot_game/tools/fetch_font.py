#!/usr/bin/env python3
"""《今天的规则》—— 分享卡片中文字体获取 / 子集化（Stage 3）。

分享卡片需要一套能渲染中文的字体。生产环境不该依赖系统字体（不同机器
未必安装），所以本脚本把字体【随项目打包】，并做【子集化】把体积从 ~20MB
压到几百 KB。

策略（按优先级）：
  1. 若 assets/fonts/NotoSansSC-Subset.ttf 已存在且非空 → 直接复用；
  2. 否则寻找本地 CJK 字体（系统中的 Noto Sans CJK / 思源黑体 ttf）；
  3. 否则从网络下载 Noto Sans SC（需联网，可用 --url 覆盖）；
  4. 用 fontTools 子集化为"ASCII + 常用汉字（GB2312）+ 中文标点"；
  5. 写入 assets/fonts/NotoSansSC-Subset.ttf。

用法:
    python tools/fetch_font.py                 # 生成子集字体
    python tools/fetch_font.py --full          # 直接拷贝完整字体（不子集化）
    python tools/fetch_font.py --text "自定义字符"
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "assets", "fonts")
OUT_FILE = os.path.join(OUT_DIR, "NotoSansSC-Subset.ttf")

# 本地候选字体（按优先级）：优先独立 .ttf，其次 .ttc（需指定 fontNumber）
LOCAL_CANDIDATES = [
    ("/usr/local/share/fonts/tabbit/NotoSansSC-Regular.ttf", None),
    ("/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf", None),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
]

DOWNLOAD_URL = (
    "https://github.com/notofonts/noto-cjk/raw/main/Sans/OTF/"
    "SimplifiedChinese/NotoSansCJKsc-Regular.otf"
)


def common_charset():
    """ASCII + 中文标点 + GB2312 常用汉字。"""
    chars = set(chr(c) for c in range(0x20, 0x7F))
    chars |= set(" 、。！？；：（）【】《》“”‘’…—·，％＋－×÷～「」『』〔〕")
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                chars.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    return chars


def find_local():
    for path, num in LOCAL_CANDIDATES:
        if os.path.exists(path):
            return path, num
    return None, None


def subset_font(src, font_number, out_path, charset):
    from fontTools import subset
    opts = subset.Options()
    opts.desubroutinize = True
    opts.layout_features = ["*"]
    opts.notdef_outline = True
    opts.name_IDs = ["*"]
    opts.name_legacy = True
    kwargs = {"fontNumber": font_number} if font_number is not None else {}
    font = subset.load_font(src, opts, **kwargs)
    # 若是可变字体（VF），先实例化为静态 Regular，体积可显著下降
    try:
        from fontTools.varLib import instancer
        if "fvar" in font:
            instancer.instantiateVariableFont(font, {"wght": 400}, inplace=True)
    except Exception:
        pass
    ss = subset.Subsetter(options=opts)
    ss.populate(text="".join(sorted(charset)))
    ss.subset(font)
    subset.save_font(font, out_path, opts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="不子集化，直接拷贝完整字体")
    ap.add_argument("--url", default=DOWNLOAD_URL)
    ap.add_argument("--text", default="", help="追加要保留的自定义字符")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT_FILE) and os.path.getsize(OUT_FILE) > 0 and not args.force:
        print(f"已存在，跳过：{OUT_FILE}（{os.path.getsize(OUT_FILE)} 字节）")
        return

    src, num = find_local()
    if not src:
        print(f"本地未找到 CJK 字体，尝试下载 {args.url} ...")
        import urllib.request
        tmp = os.path.join(OUT_DIR, "_download.tmp")
        urllib.request.urlretrieve(args.url, tmp)
        src, num = tmp, None

    if args.full:
        shutil.copyfile(src, OUT_FILE)
    else:
        charset = common_charset()
        if args.text:
            charset |= set(args.text)
        print(f"子集化：{src}（fontNumber={num}），字符数≈{len(charset)} ...")
        subset_font(src, num, OUT_FILE, charset)
    print(f"已生成 {OUT_FILE}（{os.path.getsize(OUT_FILE)} 字节）")


if __name__ == "__main__":
    main()
