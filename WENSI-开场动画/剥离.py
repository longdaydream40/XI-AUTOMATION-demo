#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 RhineLabUI 里剥出「只有开场动画」的独立版。

  上游  /home/xuan/设计/RhineLabUI        （1785 行的 main.ts + 三维阵列 + 档案 + 工作台 + 壁纸 + PWA）
  产物  /home/xuan/设计/WENSI-开场动画     （只有开场这一条链）

做四件事：
  1. src/ 里的动画文件逐字节照搬上游，一个字符不改，并记 sha256
  2. 按选择器从上游 style.css / responsive.css 里挑出开场要用的规则
  3. 只取 MiSans 覆盖拉丁字符的那一个 woff2 分片（上游 753 个分片 26 MB）
  4. 自检：逐字节一致、CSS 每条都能在上游里找到、产物里不许留三维/档案的东西

手写的部分（main.ts / theme-ui.ts / asset-url.ts / fonts.css / 黑场开场.css /
index.html / package.json / tsconfig.json / vite.config.ts）不在这里生成 —— 它们是
这个项目的正文，脚本只管搬运和校验。
"""

from __future__ import annotations

import re
import shutil
import sys
from hashlib import sha256
from pathlib import Path

UPSTREAM = Path("/home/xuan/设计/RhineLabUI")
OUT = Path("/home/xuan/设计/WENSI-开场动画")

# 动画本体：逐字节照搬，绝不改。改颜色改文案请去 黑场开场.css 和 main.ts 的 DOM。
VERBATIM = [
    "boot.ts",
    "boot-motion.ts",
    "boot-tracks.ts",
    "boot-orbit-tracks.ts",
    "boot-logo-tracks.ts",
    "boot-lettering.ts",
    "boot-lettering-art.json",
    "boot-lettering.css",
    "brand.ts",
]

# 产物里不该出现的东西（剥掉的那一坨）
FORBIDDEN = [
    "three",
    "ArchiveScene",
    "archive",
    "Workbench",
    "workbench",
    "Wallpaper",
    "wallpaper",
    "ModelViewer",
    "InspectionOverlay",
    "DocumentDecryption",
    "quality",
    "gamepad",
    "pwa",
]

# 独立版 DOM 里真实存在的选择器
KEEP = [
    r"^\*$", r"^:root$", r"^body$", r"^button$",
    r"::selection", r"button:focus-visible", r"button:disabled",
    r"#viewport", r"#stage",
    r"\.boot$", r"\.boot\b(?!-)", r"\.boot-background", r"\.boot-white",
    r"\.boot-logo", r"\.access-text", r"\.auth-status", r"\.scan\b",
    r"\.scan-", r"\.ring-", r"\.welcome\b", r"\.welcome-",
    r"\.brand\b", r"\.brand-", r"\.powered\b", r"\.boot-phrase",
    r"\[data-mode", r"\[data-boot", r"\[data-layout=\"opening\"",
    r"\[data-opening-portrait",
]
KEEP_RE = re.compile("|".join(KEEP))
DROP_RE = re.compile(
    r"three-scene|scene-atmosphere|archive|detail|terminal-modal|toast|"
    r"loading|pwa|workbench|wb-|relay|viewer|inspection|hover-label|modal|"
    r"system-nav|system-footer|\.skip|mobile-entry|category-|quality|"
    r"clock|entry-|error-state|tab-|solid-button|surface-|cinema-caption|"
    r"theme-settings|settings|search|file-title|file-open|read-file|"
    r"callout|column-navigation|export-button|@import"
)


def split_top_level(text: str) -> list[tuple[str, str]]:
    """按顶层花括号切块，跳过注释。返回 [(选择器, 整块)]。"""
    blocks: list[tuple[str, str]] = []
    i, n, start = 0, len(text), 0
    while i < n:
        if text[i : i + 2] == "/*":
            end = text.find("*/", i + 2)
            if end < 0:
                break
            i = end + 2
            continue
        if text[i] == "{":
            depth, j = 0, i
            while j < n:
                if text[j : j + 2] == "/*":
                    end = text.find("*/", j + 2)
                    if end < 0:
                        break
                    j = end + 2
                    continue
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            selector = re.split(r"[};]", text[start:i])[-1].strip()
            blocks.append((selector, text[start : j + 1]))
            i = start = j + 1
            continue
        i += 1
    return blocks


def pick_css() -> tuple[str, int]:
    picked: list[str] = []
    animations: set[str] = set()
    keyframes: dict[str, str] = {}

    for name in ("style.css", "responsive.css"):
        text = (UPSTREAM / "src" / name).read_text(encoding="utf-8")
        # 上游文件尾部挂着本项目加的「WENSI 黑场开场」覆盖段，那是正文不是上游，不拾。
        text = text.split("/* ══")[0]
        for selector, block in split_top_level(text):
            if selector.startswith("@keyframes"):
                keyframes[selector.split()[1]] = block
                continue
            if selector.startswith("@media"):
                inner = [
                    b
                    for s, b in split_top_level(block)
                    if KEEP_RE.search(s) and not DROP_RE.search(s)
                ]
                if not inner:
                    continue
                for _, b in split_top_level(block):
                    animations |= set(re.findall(r"animation:\s*([\w-]+)", b))
                picked.append(block[: block.index("{") + 1] + "\n".join(inner) + "}")
                continue
            if selector.startswith("@"):
                continue
            if DROP_RE.search(selector) or not KEEP_RE.search(selector):
                continue
            picked.append(block)
            animations |= set(re.findall(r"animation:\s*([\w-]+)", block))

    used = [keyframes[k] for k in keyframes if k in animations]
    banner = (
        "/* WENSI 开场动画 · 只保留开场需要的规则。\n"
        "   按选择器从上游 style.css / responsive.css 里挑出来的，每条与上游逐字一致。\n"
        "   黑场覆盖在 黑场开场.css 里，不在这份文件里改。\n"
        "   上游：github.com/LBEILC/RhineLabUI @ 12cc5e4（MIT） */\n\n"
    )
    return banner + "\n".join(picked + used) + "\n", len(picked)


def main() -> int:
    src = UPSTREAM / "src"
    if not src.is_dir():
        print(f"找不到上游 {src}", file=sys.stderr)
        return 1

    fail: list[str] = []
    digest: list[str] = []

    # ── 1. 动画文件逐字节照搬 ────────────────────────────────────────────
    for name in VERBATIM:
        source = src / name
        if not source.is_file():
            fail.append(f"上游缺文件 {name}")
            continue
        data = source.read_bytes()
        (OUT / "src" / name).write_bytes(data)
        digest.append(f"{sha256(data).hexdigest()}  src/{name}")

    # ── 2. 挑 CSS ────────────────────────────────────────────────────────
    css, rule_count = pick_css()
    (OUT / "src" / "style.css").write_text(css, encoding="utf-8")

    # ── 3. 字体：只要覆盖拉丁的那一个分片 ────────────────────────────────
    font_src = UPSTREAM / "public/fonts/misans-webfont-4.3.1/bold/0.woff2"
    if not font_src.is_file():
        fail.append("上游缺 MiSans bold/0.woff2")
    else:
        (OUT / "public/fonts/misans").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(font_src, OUT / "public/fonts/misans/bold-0.woff2")
    for extra, target in (
        ("public/favicon.svg", "public/favicon.svg"),
        ("public/fonts/MiSans-license.pdf", "public/fonts/LICENSE-MiSans.pdf"),
    ):
        if (UPSTREAM / extra).is_file():
            shutil.copyfile(UPSTREAM / extra, OUT / target)

    (OUT / "源码校验.sha256").write_text("\n".join(digest) + "\n", encoding="utf-8")

    # ── 4. 自检 ──────────────────────────────────────────────────────────
    # ① 照搬的文件必须逐字节等于上游
    for name in VERBATIM:
        a, b = src / name, OUT / "src" / name
        if a.is_file() and b.is_file() and a.read_bytes() != b.read_bytes():
            fail.append(f"{name} 与上游不一致")

    # ② 挑出来的每条规则，都要能在上游原文里逐字找到
    upstream_css = [
        (name, (UPSTREAM / "src" / name).read_text(encoding="utf-8"))
        for name in ("style.css", "responsive.css")
    ]
    missing = 0
    for selector, block in split_top_level(css):
        body = block[block.index("{") :]
        if not any(body in text for _, text in upstream_css):
            missing += 1
            if missing <= 3:
                fail.append(f"挑出来的规则在上游找不到：{selector[:60]!r}")
    if missing:
        fail.append(f"共 {missing} 条规则对不上上游原文")

    # ③ 手写的那几个文件里不许留三维/档案的痕迹。
    #    照搬的动画文件跳过 —— “three-frame steps”这种注释不算依赖，
    #    它们真的引了什么由下面第 ④ 条查。
    hand_written = [
        OUT / "src" / name
        for name in ("main.ts", "theme-ui.ts", "asset-url.ts", "fonts.css", "黑场开场.css", "style.css")
    ] + [OUT / "index.html"]
    for path in hand_written:
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            # .boot-background / boot-tracks 之类不算，只看整词
            if re.search(rf"(?<![A-Za-z-]){re.escape(word)}(?![A-Za-z-])", text):
                fail.append(f"{path.name} 里还留着 {word!r}")
                break

    # ④ main.ts 的 import 必须都能落地
    for ts in sorted((OUT / "src").glob("*.ts")):
        for target in re.findall(r'from\s+"(\.[^"]+)"', ts.read_text(encoding="utf-8")):
            resolved = (ts.parent / target).with_suffix("")
            if not any(
                resolved.with_suffix(ext).exists()
                for ext in (".ts", ".json", ".css", ".tsx")
            ):
                fail.append(f"{ts.name} 引了不存在的模块 {target}")

    total = sum(
        f.stat().st_size
        for f in OUT.rglob("*")
        if f.is_file()
        and not any(p in f.parts for p in ("node_modules", "dist", ".git", "预览"))
    )
    print(f"照搬 {len(VERBATIM)} 个动画文件；挑出 CSS 规则 {rule_count} 条")
    print(f"源码 + 资源 {total / 1024:.0f} KB（不含预览图与 node_modules；上游仓库 353 MB）")
    if fail:
        print(f"\n发现 {len(fail)} 个问题：", file=sys.stderr)
        for f in fail:
            print("  ✗ " + f, file=sys.stderr)
        return 2
    print("自检通过：动画文件逐字节等于上游、CSS 每条都能溯源、产物里没有三维/档案残留")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
