#!/usr/bin/env python3
"""把 engine.template.html 渲染成两份独立成品。

两版共用同一套时间轴与故障引擎，只有调色板与墨色不同，
避免两份代码各自漂移。

占位符只有两类：
  直接写像素的（INK_RGB / CLIP_RGB）—— 展开成对 d[i] 的赋值语句
  纯色与标题（MODE / TITLE / BG / INK / ALPHA_MUL）
"""
import base64
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TPL = (HERE / "engine.template.html").read_text(encoding="utf-8")

# 头像原图内联成 data URI：让成品在 file:// 下双击也能跑
ART = HERE.parent / "温曦头像-SVG" / "温曦-侧颜头像-透明底.png"
IMAGE_DATA_URI = "data:image/png;base64," + base64.b64encode(ART.read_bytes()).decode("ascii")

# Cal Sans 同样内联：file:// 下不能依赖任何外部请求
FONT = HERE / "fonts" / "CalSans-latin.woff2"
FONT_DATA_URI = "data:font/woff2;base64," + base64.b64encode(FONT.read_bytes()).decode("ascii")

# SVG 里 face 组的光栅化剪影，用作面部掩膜。
# 不能再用「亮度>=248.5 的泛洪」判面部：源图的脸本身有纵向渐变
# （y415 均值 230 → y599 均值 248），只有 45% 的脸像素达标，
# 于是半张脸被当成头发处理，脸上会出现一条对角渐变。
FACE_MASK = HERE / "facemask.png"
FACE_MASK_DATA_URI = "data:image/png;base64," + base64.b64encode(FACE_MASK.read_bytes()).decode("ascii")


def rgb_assign(target, rgb, off="i"):
    """生成对像素的墨色赋值。

    坑：这里必须把循环下标 i 拼进去（d[i+0] / d[i+1] / d[i+2]）。
    写成字面的 d[0] / d[1] / d[2] 会只改到画布的第一个像素，
    整张图保畕原图的颜色 —— 表面上看不出报错，但调色版根本没生效。
    """
    return "".join("%s[%s+%d] = %d; " % (target, off, k, c) for k, c in enumerate(rgb))


TEAL = (84, 172, 154)
CLIP_RED = (178, 36, 48)
WHITE = (255, 255, 255)


def palette(ink, clip, mode, title, out):
    """两版共用同一套时间轴、故障引擎、alpha 映射，只有墨色与发夹色不同。

    黑白版不是「另做一版」：只把发块墨色换成白，
    alpha 映射一字不改，色彩深度与彩色版完全一致；
    发夹色仍然传彩色版的暗红。
    """
    return dict(
        MODE=mode, TITLE=title, OUT=out,
        BG="#000000", INK="#ffffff", ALPHA_MUL="1.0",
        INK_RGB=rgb_assign("d", ink),
        CLIP_RGB=rgb_assign("d", clip) + "d[i+3] = 255;",
    )


# ── 彩色版：暗青绿人像 + 暗红发夹 ────────────────────────────────
#
# 墨色 (84,172,154) 是按参考产物的实测值反推的，不是拍的：
#   参考图人像内容像素  P10 RGB(30,63,56) / P50 RGB(47,96,86) / P90 RGB(63,129,114)
#   三通道比 47:96:86，取 G=172 归一 → 墨色 (84,172,154)
#   于是参考图的 P50 对应 alpha≈0.56，与模板里 vHair/vFace 的取值区间对齐。
COLOR = palette(TEAL, CLIP_RED, "color", "WENSI AUTOMATION",
                HERE.parent / "index.html")

# ── 黑白版：人像去色变白，但发饰保留鲜艳的红色 ─────────────────
# 用户要求：白色那一版发饰必须还是红的（红是画面里唯一的色相锚点，
# 去色后整个画面就只剩黑白灰，发夹也跟着丢了）。
MONO = palette(WHITE, CLIP_RED, "mono", "WENSI AUTOMATION · MONO",
               HERE.parent / "index-bw.html")


def render(pal: dict) -> str:
    out = TPL.replace("{{IMAGE_DATA_URI}}", IMAGE_DATA_URI)
    out = out.replace("{{FONT_DATA_URI}}", FONT_DATA_URI)
    out = out.replace("{{FACE_MASK_DATA_URI}}", FACE_MASK_DATA_URI)
    for key, val in pal.items():
        if key == "OUT":
            continue
        out = out.replace("{{%s}}" % key, str(val))
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if leftover:
        sys.exit("未替换的占位符: %s" % sorted(set(leftover)))
    return out


def main():
    for pal in (COLOR, MONO):
        text = render(pal)
        pal["OUT"].write_text(text, encoding="utf-8")
        print("写出 %s  (%d 字节)" % (pal["OUT"], len(text)))


if __name__ == "__main__":
    main()
