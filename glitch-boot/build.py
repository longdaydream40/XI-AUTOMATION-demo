#!/usr/bin/env python3
"""Build the self-contained XI portrait. Fixed pixel work runs here, not on page load.
Requires Pillow and NumPy. The original portrait and face mask are never modified.
"""
import base64
import io
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WHITE = (255, 255, 255)
CLIP_RED = (178, 36, 48)


def data_uri(data, mime):
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def png_uri(pixels):
    stream = io.BytesIO()
    Image.fromarray(pixels).save(stream, format="PNG", optimize=True)
    return data_uri(stream.getvalue(), "image/png")


def portrait_assets():
    source = Image.open(ROOT / "温曦头像-SVG/温曦-侧颜头像-透明底.png").convert("RGB")
    rgb = np.asarray(source, dtype=np.float64)
    height, width = rgb.shape[:2]
    lum = rgb.mean(axis=2)
    # A white border lets one four-connected flood fill reach every outer edge.
    white = np.full((height + 2, width + 2), 255, dtype=np.uint8)
    white[1:-1, 1:-1] = np.where(lum >= 248.5, 255, 0)
    # fromarray() may be read-only/zero-copy; floodfill needs a writable image.
    flood = Image.fromarray(white).copy()
    ImageDraw.floodfill(flood, (0, 0), 128)
    outside = np.asarray(flood)[1:-1, 1:-1] == 128
    if not outside[0, 0] or not outside[-1, -1]:
        raise ValueError("Outer-background flood fill failed")
    face = np.asarray(Image.open(HERE / "facemask.png").convert("L").resize(source.size, Image.Resampling.NEAREST)) > 128
    detail = np.clip((255 - np.minimum(232, lum)) / 118, 0, 1) ** 0.78
    tone = 0.20 + 0.56 * (np.floor(detail * 5 + 0.5) / 5)
    scan = np.where(np.arange(height) % 3 == 2, 0.885, 1.058)[:, None]
    pixels = np.empty((height, width, 4), dtype=np.uint8)
    pixels[:, :, :3] = WHITE
    pixels[:, :, 3] = np.floor(255 * np.minimum(1, tone * scan) + 0.5)
    pixels[face | outside, 3] = 0
    red = rgb[:, :, 0] - (rgb[:, :, 1] + rgb[:, :, 2]) * 0.5 > 25
    pixels[red, :3] = CLIP_RED
    pixels[red, 3] = 255
    ghost = pixels.copy()
    ghost[:, :, :3] = WHITE
    ghost[:, :, 3] = np.floor(255 * 0.22 + 0.16 * pixels[:, :, 3] + 0.5)
    return png_uri(pixels), png_uri(ghost)


def render():
    base, ghost = portrait_assets()
    values = {
        "IMAGE_DATA_URI": base,
        "GHOST_DATA_URI": ghost,
        "FONT_DATA_URI": data_uri((HERE / "fonts/CalSans-latin.woff2").read_bytes(), "font/woff2"),
        "SHARED_SCRIPT": "\n".join(
            (ROOT / "shared" / name).read_text().replace("export function ", "function ")
            for name in ("tilt.js", "playback.js")
        ),
    }
    text = (HERE / "engine.template.html").read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    leftover = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if leftover:
        raise ValueError(f"Unfilled template fields: {leftover}")
    return text


if __name__ == "__main__":
    output = ROOT / "index-bw.html"
    text = render()
    output.write_text(text, encoding="utf-8")
    print(f"Built {output} ({len(text.encode('utf-8')):,} bytes)")
