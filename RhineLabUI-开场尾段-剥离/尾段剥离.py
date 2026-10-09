#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RhineLabUI 开场动画 · 尾段剥离

把开场动画从「START PROCESSING...」那一帧起、到二维开场层结束为止的代码抽出来。

  起点 f457（原片 18.28 s / appTime 13.28 s）—— 截图那一帧
  终点 f673（原片 26.92 s / appTime 21.92 s）—— 二维层最后一次数值变化

做四件事：
  1. 源码/尾段片段/  —— 每个上游文件里尾段真正执行到的行段，带原文件行号
  2. 源码/逐帧快照.json —— 直接跑上游 boot-motion.ts 实测出来的逐帧数值（回归基准）
  3. 源码/逐帧变更表.md —— 上面那份数据摊平成可读表
  4. 自检：行号锚点必须命中、窗口边界必须和数据吻合

为什么锚点是手写的：行号会漂。上一轮剥离里 main.ts 的 bootFrame / frame /
completeStartup 三段行号整体错位（941 / 1000 / 1182，实际是 1200 / 1274 / 1537），
那次的脚本只检查了「行段没超出文件」，所以一路绿灯放行。这次的锚点带语义，
行号一对不上就报错，不会静默放过。
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

UPSTREAM = Path("/home/xuan/设计/RhineLabUI")
OUT = Path("/home/xuan/设计/RhineLabUI-开场尾段-剥离")

# ── 尾段窗口 ─────────────────────────────────────────────────────────────
# f = floor((appTime + 5) * 25 + 1e-5)，所以帧 f 覆盖 t ∈ [f/25, (f+1)/25)
START_FRAME = 457
END_FRAME = 673

# ── 片段标签 ─────────────────────────────────────────────────────────────
T = "尾段"
D = "依赖"
P = "前置"

# ── 片段表 ───────────────────────────────────────────────────────────────
# (文件, 输出名, [(起, 止, 标签, 说明, [(上游绝对行号, 该行必须包含的文本), ...]), ...])
# 探针用的是上游原文件行号，不是片段内偏移 —— 写行号时看的就是原文件，不容易错位。
SEGMENTS: list[tuple[str, str, list[tuple]]] = [
    (
        "src/boot-motion.ts",
        "boot-motion.ts.尾段.ts",
        [
            (1, 5, D, "import：曲线表两条 + 标志轨迹一条", [(1, "// Original footage is 25 fps"), (3, "boot-tracks")]),
            (6, 22, D, "progress / smooth / typed / at / accessCounts，逐字文案就靠这几个", [(6, "export const progress"), (9, "const typed ="), (19, "const at =")]),
            (24, 26, D, "bootMotion 入口 + 帧号换算：f = floor((appTime + 5) * 25 + 1e-5)", [(24, "export function bootMotion"), (26, "Math.floor(t * 25")]),
            (27, 36, T, "★step 五段分派。第 32 行 t < 19.48 和第 34 行 t < 22.76 是尾段的两条边界", [(27, "const step ="), (32, "t < 19.48"), (33, '"auth"'), (34, "t < 22.76"), (35, '"scan"')]),
            (37, 41, P, "auth 前两段（ID CONFIRMED / REQUEST RECEIVED），尾段不走这里", [(38, "if (f < 363)"), (41, "REQUEST RECEIVED")]),
            (42, 47, T, "★尾段起点。第 44-45 行补三个点，第 46 行是 f479/485/486 的缺字故障", [(44, "if (f >= 449)"), (45, 'repeat(Math.min(3'), (46, "SING...")]),
            (48, 54, T, "每帧输入量：frame / scan / scanOrbit / scanGlitch / 闪切表 / exit", [(48, "const frame = t * 25;"), (49, "scanTrack(frame)"), (50, "scanOrbitTrack(frame)"), (51, "scanGlitch"), (54, "const exit = smooth")]),
            (55, 70, T, "快照头部：step / auth / logoOpacity / authOpacity / 标志 / 品牌三行 / powered", [(58, "step,"), (59, "auth,"), (65, "logoOpacity:"), (68, "authOpacity:")]),
            (71, 120, T, "★scan 组：双环半径与起止角、环闪、字距收拢、核心装饰、小点绕行", [(71, "scanVisible:"), (74, "scanRadius:"), (75, "ringScale:"), (88, "scanTracking:"), (119, "ornament:")]),
            (121, 136, T, "★welcome 组：闪切表、公司名扫过、高亮、数据库闪动、退场缩放模糊", [(121, "welcomeVisible:"), (128, "companyVisible:"), (130, "highlight:"), (131, "databaseOpacity:"), (135, "exitBlur:")]),
            (137, 138, T, "★白场与底纹：底纹在 26.92 s 关掉，白场在 26.16–26.88 s 涨满", [(137, "backgroundOpacity:"), (138, "white: smooth")]),
            (139, 140, T, "return 收尾", [(139, "};"), (140, "}")]),
        ],
    ),
    (
        "src/boot.ts",
        "boot.ts.尾段.ts",
        [
            (129, 132, D, "update 入口：同帧只算一次快照，写进 dataset.bootFrame", [(129, "update(time: number) {"), (132, "dataset.bootFrame")]),
            (133, 137, P, "access-text / boot-logo 层（尾段里 logoOpacity 恒定，只有位移在写）", [(133, "accessLettering.setText"), (136, "style.transform =")]),
            (138, 140, T, "★标志轮廓缺口。f457 时只剩 97.25% 实线，缺口绕行到 f486 才停", [(138, "strokeDasharray"), (139, "strokeDashoffset"), (140, "stroke-width")]),
            (141, 158, P, "字形文本节点 + 加减号（尾段恒定）", [(143, "this.letters.textContent"), (145, "this.plus.style.opacity"), (151, "this.minus.setAttribute")]),
            (159, 160, T, "★auth-status 开关 + setText(s.auth)：f479/485/486 的缺字就从这一行进 DOM", [(159, "auth-status"), (160, "authLettering.setText(s.auth)")]),
            (161, 169, P, "brand 三行 / powered（尾段恒定）", [(161, 'this.opacity(".brand", 1)'), (167, 'powered'), (168, "clipPath")]),
            (170, 171, T, "★scan 层开关 + renderScan 调用。f487 之后这一行是整段扫描环的唯一入口", [(170, 'this.opacity(".scan"'), (171, "renderScan(s);")]),
            (172, 196, T, "★welcome 组 + 白场 + 底纹 + return。f569–f673 全部动画都在这一段里", [(172, 'this.opacity(".welcome"'), (175, "blur(${s.exitBlur}px)"), (184, "companyInk[1]"), (191, "boot-background"), (192, "boot-white"), (195, "return s;")]),
            (197, 264, T, "★renderScan：尾段专有。扫描环全部几何（弧、端点圆、小点、字距）都由这里落进 SVG", [(197, "private renderScan("), (203, "ringScale"), (207, "scanPaths[0]"), (239, "ornament"), (242, "orbitDots"), (253, "caps.forEach"), (261, "letterSpacing")]),
            (265, 273, T, "reset：跳过或重播时的收尾，尾段里被 setMode 调用", [(265, "reset() {"), (272, 'this.opacity("#boot-background", 0);')]),
        ],
    ),
    (
        "src/boot-tracks.ts",
        "boot-tracks.ts.尾段.ts",
        [
            (1, 33, D, "track()：单调三次 Hermite 插值。下面两条尾段曲线都跑它", [(1, "// Reference-space measurements"), (5, "export function track("), (11, "const tangent")]),
            (59, 85, T, "★companyTrack：f588–f611 公司名黑底扫过的横向量", [(59, "Frames 590–591 cut"), (60, "const highlightKeys"), (84, "export const companyTrack")]),
            (87, 347, T, "★scanTrack：扫描环的全部轨迹表（半径 / 黑白双环 / 内外弧 / 轨道点 / 端点圆 / 六列节点）", [(87, "export function scanTrack("), (91, "radius: value(["), (110, "])")]),
        ],
    ),
    (
        "src/boot-orbit-tracks.ts",
        "boot-orbit-tracks.ts.尾段.ts",
        [
            (1, 149, T, "★整份文件都是给尾段的：两侧小圆（543–568）、九列节点、六颗小点绕行、核心闪光", [(1, 'import { track }'), (8, "const sides = ["), (57, "const columns"), (90, "export function scanOrbitTrack"), (99, "const flash ="), (138, "sideVisible"), (140, "satellites:")]),
        ],
    ),
    (
        "src/boot-lettering.ts",
        "boot-lettering.ts.尾段.ts",
        [
            (9, 32, D, "loadBootWebfonts：字体加载门（字体缺失就退回作者画的字形）", [(9, "loadBootWebfonts"), (25, "catch")]),
            (35, 78, D, "构造函数：把 art.json 里的字形格子先建好，setText 才有东西可显隐", [(35, "export class BootLettering"), (45, "constructor("), (55, "art.letters.map"), (76, "dataset.letteringRenderer = \"artwork\"")]),
            (80, 92, D, "useWebfonts：字体就绪后换掉字形来源，格子与时间轴不变", [(80, "useWebfonts() {"), (87, "dataset.letter"), (91, "letteringRenderer")]),
            (94, 110, T, "★setText：尾段唯一入口。逐帧比对同值直接 return，值一变压 phrase 与字母格子", [(94, "setText(value: string) {"), (95, "if (this.value === value) return;"), (98, "startsWith(value)"), (107, "letter.hidden = hidden")]),
        ],
    ),
    (
        "src/boot-lettering.css",
        "boot-lettering.css.尾段.css",
        [
            (1, 57, D, "逐字排版基础：.boot-phrase 格子与字母位", [(2, ".boot-phrase {"), (11, ".boot-phrase-letter {")]),
            (58, 60, T, "★尾段三个短语的字距与字号：负间距、.auth-status 21.35px、.welcome-company -0.5px", [(58, "#auth-message"), (59, ".auth-status"), (60, ".welcome-company")]),
            (71, 75, T, "★竖屏下 scan 文案的字距（!important 盖掉 JS 每帧写的值）", [(73, "portrait"), (74, "important")]),
        ],
    ),
    (
        "src/audio.ts",
        "audio.ts.尾段.ts",
        [
            (74, 85, T, "★BOOT_CUES：按原片时间码的提示点表。窗口内命中 6 条", [(74, "export const BOOT_CUES"), (77, "19.48"), (82, "26.92")]),
            (614, 643, T, "★updateBoot：相位配平（22.76 / 26.92 两条边界）+ cue 派发 + 键音", [(614, "updateBoot(appTime: number"), (618, "const phase = time < 22.76"), (635, "time - previous > 0.3"), (640, "for (const cue of BOOT_CUES)"), (642, "hasTypingBetween")]),
        ],
    ),
    (
        "src/typing-rhythm.ts",
        "typing-rhythm.ts.尾段.ts",
        [
            (1, 30, T, "★TYPING_FRAMES：拿 bootMotion 反推出来的逐字帧表。窗口内只剩 f457 一帧", [(1, 'import { bootMotion }'), (5, "export const TYPING_FRAMES"), (25, "export function hasTypingBetween")]),
        ],
    ),
    (
        "src/main.ts",
        "main.ts.尾段.ts",
        [
            (1196, 1260, T, "★ease + bootFrame：开场时间轴分段。二维尾段在 f673 结束，之后交三维", [(1196, "const ease ="), (1200, "function bootFrame(t: number) {"), (1231, 'step = "array";'), (1243, "file-title"), (1248, '"--entry-opacity"'), (1252, "const reveal = ease"), (1255, "if (t >= 35)"), (1259, "return { reveal, lift, zoom, time: t };")]),
            (1274, 1351, D, "frame()：每帧调度。22 秒前开场层盖住三维场景", [(1274, "function frame(ms: number) {"), (1289, "const cinema ="), (1291, "bootFrame(frozenTime"), (1299, "cinema.time >= 21.9"), (1350, "requestAnimationFrame(frame);")]),
            (1537, 1585, D, "completeStartup：点击开始。bootStart = now - 1.76，就是白场那一帧", [(1537, "function completeStartup(silent: boolean) {"), (1548, "bootStart ="), (1550, 'reviewParams.get("time")'), (1552, 'setMode("boot")'), (1565, "setTimeout"), (1581, "requestAnimationFrame(frame);")]),
            (484, 550, D, "setMode：切模式。boot 的收尾（reset 与 inert）在这里", [(484, "function setMode(next: Mode) {"), (541, 'next === "detail"')]),
            (639, 649, D, "replayBoot：重播开场", [(639, "function replayBoot"), (643, "function replayBootAfterModal")]),
        ],
    ),
    (
        "src/style.css",
        "style.css.尾段.css",
        [
            (230, 283, T, "★.scan 基础样式：定位、缩放、环、节点。JS 每帧覆写的那些值在这里有底", [(230, ".scan {"), (246, ".scan > span"), (254, ".scan-track"), (258, ".scan-ring")]),
            (284, 315, T, "★.welcome 基础样式：欢迎页三层与标志位", [(284, ".welcome {"), (299, ".welcome strong"), (307, ".welcome-logo")]),
            (2138, 2227, T, "★尾段覆盖：开场期间禁 CSS 过渡与动画（全帧驱动），.boot-white / .scan / .welcome 全组尺寸", [(2138, '[data-mode="boot"] .powered'), (2140, "transition: none;"), (2149, ".boot-white {"), (2155, ".scan {"), (2167, ".welcome {"), (2175, ".welcome-heading {"), (2182, ".welcome-panel {"), (2190, ".welcome-company {"), (2209, ".welcome-highlight"), (2213, ".welcome-database {"), (2222, ".welcome-logo {")]),
        ],
    ),
    (
        "src/responsive.css",
        "responsive.css.尾段.css",
        [
            (5, 12, T, "★开场版式：二维层固定 1920×1080 局部坐标，白场按 --opening-* 缩放，竖屏文案放大", [(5, "[data-layout=\"opening\"] .boot {"), (6, ".boot-white"), (7, ".scan {"), (8, ".access-text, .auth-status"), (9, ".scan > span"), (12, "mobile-boot")]),
        ],
    ),
]

MARK = {
    T: "★ 尾段生效",
    D: "· 依赖（尾段之前就跑完 / 尾段每帧都在用）",
    P: "· 前置（尾段窗口内已定型，不再变化）",
}


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def main() -> int:
    src = UPSTREAM / "src"
    if not src.is_dir():
        print(f"找不到上游源码目录 {src}", file=sys.stderr)
        return 1
    if not (OUT / "工具" / "逐帧探针.ts").is_file():
        print("找不到 工具/逐帧探针.ts", file=sys.stderr)
        return 1

    fail: list[str] = []
    (OUT / "源码" / "尾段片段").mkdir(parents=True, exist_ok=True)
    digest: list[str] = []

    # ── 1. 抽片段 ────────────────────────────────────────────────────────
    anchor_count = 0
    for rel, out_name, blocks in SEGMENTS:
        path = UPSTREAM / rel
        if not path.is_file():
            fail.append(f"缺失文件 {rel}")
            continue
        digest.append(f"{sha256(path.read_bytes()).hexdigest()}  {rel}")
        lines = read_lines(path)
        total = len(lines) - (1 if lines and lines[-1] == "" else 0)
        body = [
            f"// 尾段片段：{rel}",
            f"// 起止 = 上游原文件行号；上游 {UPSTREAM}（HEAD 12cc5e4）",
            f"// 尾段窗口 f{START_FRAME}–f{END_FRAME}（原片 {START_FRAME / 25:.2f}–{END_FRAME / 25:.2f} s）",
            "",
        ]
        for start, end, tag, note, probes in blocks:
            if end > total:
                fail.append(f"{rel}: 行段 {start}-{end} 超出文件（共 {total} 行）")
                continue
            chunk = lines[start - 1 : end]
            label = MARK[tag]
            body.append(f"{'─' * 4} {rel}:{start}-{end}  {label} {note}")
            for line_no, expect in probes:
                if line_no < start or line_no > end:
                    fail.append(f"{rel}:{start}-{end} 探针行号 {line_no} 落在片段外")
                    continue
                actual = chunk[line_no - start]
                anchor_count += 1
                if expect not in actual:
                    fail.append(
                        f"{rel}:{start}-{end} 锚点失配 —— 第 {line_no} 行\n"
                        f"        期望含 {expect!r}\n        实际是 {actual.strip()[:110]!r}"
                    )
            body.extend(chunk)
            body.append("")
        (OUT / "源码" / "尾段片段" / out_name).write_text("\n".join(body), encoding="utf-8")

    (OUT / "源码" / "校验.sha256").write_text("\n".join(digest) + "\n", encoding="utf-8")

    # ── 2. 跑探针拿实测数据 ──────────────────────────────────────────────
    try:
        raw = subprocess.run(
            ["bun", "run", "工具/逐帧探针.ts"],
            cwd=OUT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        print("找不到 bun，装一个再跑（快照那一步需要它）", file=sys.stderr)
        return 1
    if raw.returncode != 0:
        print("探针跑挂了：\n" + raw.stderr[-3000:], file=sys.stderr)
        return 1
    probe = json.loads(raw.stdout)

    # 快照文件：头部（边界/变更/音频）缩进排，217 帧则是「一行一帧」，不然一个 3 万行的 JSON 没法看
    head = {k: v for k, v in probe.items() if k != "frames"}
    head_text = json.dumps(head, ensure_ascii=False, indent=1).rstrip()
    frames_text = ",\n".join(
        "  " + json.dumps(f, ensure_ascii=False, separators=(",", ":"))
        for f in probe["frames"]
    )
    (OUT / "源码" / "逐帧快照.json").write_text(
        head_text[:-1] + ',\n "frames": [\n' + frames_text + "\n ]\n}\n",
        encoding="utf-8",
    )

    # 变更表（可读版）
    win = [c for c in probe["changes"] if c["from"] <= END_FRAME]
    after = probe["changes"][len(win):]
    table = [
        f"# 尾段逐帧变更表（实测）",
        "",
        f"数据来源：`bun run 工具/逐帧探针.ts` —— 直接 import 上游 `src/boot-motion.ts`，",
        f"把 f{START_FRAME}–f{END_FRAME} 每一帧的 38 个字段全算一遍，逐帧对比得出「哪几帧真的在动」。",
        "",
        f"- 窗口：f{START_FRAME}–f{END_FRAME}，共 **{END_FRAME - START_FRAME + 1} 帧 / {(END_FRAME - START_FRAME + 1) / 25:.2f} s**",
        f"- 有变化的帧：**{len({f for c in win for f in range(c['from'], c['to'] + 1)})} 帧**，合并成 {len(win)} 段",
        f"- 窗口之后再看 {30} 帧（f{END_FRAME + 1}–f{END_FRAME + 30}）：**{'无变化' if not after else str(len(after)) + ' 段变化'}**",
        "",
        "`t` 与 `f` 是时钟本身，每帧必变，不计入。",
        "",
        "## 一、每个字段的首动 / 末动帧",
        "",
        "一整段都没动过的字段（`access` / `accessOpacity` / `logo` 的位移与线宽 / `logoLetters` / `brand` / `poweredLetters` / `scan` / `scanOrbit` / `scanFont`）不列。",
        "",
        "| 字段 | 首动 | 末动 | 动了多少帧 |",
        "|---|---|---|---|",
    ]
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    for c in win:
        for f in c["fields"]:
            first[f] = min(first.get(f, 10**9), c["from"])
            last[f] = max(last.get(f, 0), c["to"])
    for f in sorted(last, key=lambda k: (first[k], k)):
        moved = len(
            {n for c in win for n in range(c["from"], c["to"] + 1) if f in c["fields"]}
        )
        table.append(f"| `{f}` | f{first[f]} | f{last[f]} | {moved} |")

    table += ["", "## 二、逐帧变更分组", "", "| 帧区间 | 原片秒 | 在动的字段 |", "|---|---|---|"]
    for c in win:
        rng = f"f{c['from']}" if c["from"] == c["to"] else f"f{c['from']}–f{c['to']}"
        sec = f"{c['from'] / 25:.2f}–{(c['to'] + 1) / 25:.2f}"
        table.append(f"| {rng} | {sec} | {' '.join(c['fields'])} |")
    if after:
        table += ["", "## 三、窗口之后", "", "| 帧区间 | 在动的字段 |", "|---|---|"]
        table += [
            f"| f{c['from']}–f{c['to']} | {' '.join(c['fields'])} |" for c in after
        ]
    (OUT / "源码" / "逐帧变更表.md").write_text("\n".join(table) + "\n", encoding="utf-8")

    # ── 3. 边界自检：文档说的窗口必须和数据吻合 ──────────────────────────
    b = probe["boundary"]
    if b["startFrame"] != START_FRAME or b["endFrame"] != END_FRAME:
        fail.append(f"探针窗口 {b['startFrame']}–{b['endFrame']} 与脚本写的 {START_FRAME}–{END_FRAME} 不一致")
    if abs(b["startVideoTime"] - START_FRAME / 25) > 1e-9:
        fail.append("起点原片时间换算不对")
    if b["startAuthText"] != "START PROCESSING...":
        fail.append(f"起点 auth 文案是 {b['startAuthText']!r}，截图上是 START PROCESSING...")
    if b["lastChangeFrameInWindow"] != END_FRAME:
        fail.append(
            f"窗口内最后一次变化在第 {b['lastChangeFrameInWindow']} 帧，不是第 {END_FRAME} 帧 —— 终点选错了"
        )
    if b["changesAfterWindow"]:
        fail.append(f"终点之后还有变化：{b['changesAfterWindow'][:3]}")
    end_state = b["endState"]
    if end_state["white"] != 1 or end_state["backgroundOpacity"] != 0 or end_state["welcomeVisible"]:
        fail.append(f"终点那一帧二维层没退干净：{end_state}")
    if probe["audio"]["typingFramesInWindow"] != [START_FRAME]:
        fail.append(f"窗口内逐字帧是 {probe['audio']['typingFramesInWindow']}，预期只有 [{START_FRAME}]")
    if len(probe["audio"]["cuesInWindow"]) != 6:
        fail.append(f"窗口内音频提示点 {len(probe['audio']['cuesInWindow'])} 条，预期 6 条")
    moving = set(probe["movingWhileDots"])
    if moving != {"logo.start", "logo.length"}:
        fail.append(f"「三个点」那 22 帧里在动的字段是 {sorted(moving)}，预期只有标志缺口两个")
    frames = probe["frames"]
    if len(frames) != END_FRAME - START_FRAME + 1:
        fail.append(f"快照 {len(frames)} 帧，预期 {END_FRAME - START_FRAME + 1} 帧")
    # 落盘的 JSON 必须是合法的，而且帧数据一行不丢、字段一个不少
    saved = json.loads((OUT / "源码" / "逐帧快照.json").read_text(encoding="utf-8"))
    if len(saved.get("frames", [])) != len(frames):
        fail.append("落盘快照的帧数与内存里不一致")
    if sorted(saved["frames"][0]["state"]) != sorted(frames[0]["state"]):
        fail.append("落盘快照的字段表与内存里不一致")
    if saved["frames"][-1]["frame"] != END_FRAME:
        fail.append("落盘快照的末帧不是终点帧")
    tagged = sum(
        1
        for _, _, blocks in SEGMENTS
        for start, end, tag, _, _ in blocks
        if tag == T
    )
    print(
        f"尾段 f{START_FRAME}–f{END_FRAME}（原片 {START_FRAME / 25:.2f}–{END_FRAME / 25:.2f} s，"
        f"appTime {START_FRAME / 25 - 5:.2f}–{END_FRAME / 25 - 5:.2f}）"
    )
    print(f"抽片段 {len(SEGMENTS)} 个文件 / {sum(len(s[2]) for s in SEGMENTS)} 段（其中尾段生效段 {tagged} 段）")
    print(f"行号锚点校验 {anchor_count} 处")
    print(f"实测：{len(win)} 段变化、窗口内唯一的逐字帧是 f{START_FRAME}、音频提示点 6 条")

    if fail:
        print(f"\n发现 {len(fail)} 个问题：", file=sys.stderr)
        for f in fail:
            print("  ✗ " + f, file=sys.stderr)
        return 2
    print("自检通过：锚点全中、终点确实是二维层最后一帧、终点之后 30 帧无变化")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
