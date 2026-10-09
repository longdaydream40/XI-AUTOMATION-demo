#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RhineLabUI 开场动画剥离 + 流程阶段标记

做三件事：
  1. 源码/      —— 从上游仓库逐字节拷出「开场动画」相关文件（可用 sha256 与上游核对）
  2. 源码/片段/ —— main.ts / style.css / responsive.css 里属于开场的行段，带原行号抽出
  3. 标记/      —— 同内容副本，在每个阶段块的起始行**行尾**追加阶段标记注释
                   （只加行尾注释，不插入新行 → 标记版与源码版行号一一对应）

标记词：// ▶ 阶段N 名称 · 时间段 · 原片帧号
阶段划分来自 src/boot-motion.ts 的 step 判定 + src/main.ts 的交棒逻辑，不是猜的。
"""

from hashlib import sha256
from pathlib import Path
import sys

UPSTREAM = Path("/home/xuan/设计/RhineLabUI")
OUT = Path("/home/xuan/设计/RhineLabUI-开场动画-剥离")

# ── 流程阶段（时间以 appTime+5 = 原片时间；帧号 = 原片 25fps 帧号）─────────────
S0 = "阶段0 装载 · 贯穿 · 与帧无关"
SD = "★流程分派 · access/logo/auth/scan/welcome 五段的边界就写在这里"
S1 = "阶段1 access · 6.76–9.12s · f169–227"
S2 = "阶段2 logo · 9.12–11.12s · f228–277"
S3 = "阶段3 auth · 11.12–19.48s · f278–486"
S4 = "阶段4 scan · 19.48–22.76s · f487–568"
S5 = "阶段5 welcome · 22.76–26.92s · f569–672"
S6 = "阶段6 交棒 · 21.9s 起三维叠层 / 26.92s 起白场退出 · f673+"

MARK_PREFIX = "  // ▶ "

# ── 属于开场动画的文件（核心链）────────────────────────────────────────────
CORE = [
    "boot.ts",
    "boot-motion.ts",
    "boot-tracks.ts",
    "boot-logo-tracks.ts",
    "boot-orbit-tracks.ts",
    "boot-lettering.ts",
    "boot-lettering-art.json",
    "boot-lettering.css",
    "brand.ts",
    "audio.ts",
    "typing-rhythm.ts",
    "typing-samples.ts",
    "asset-url.ts",
    "theme-ui.ts",
]
# 相邻但不在开场主链上的文件（上一轮剥离收过，保留但单独放）
RELATED = [
    "hud-projection.ts",
    "startup.ts",
    "startup.css",
]

# ── 标记表：文件名 → [(锚点文本, 阶段标签, 第几次出现)] ──────────────────────
# 锚点必须唯一（或靠第 3 个元素指定序号），找不到就报错，绝不静默跳过。
MARKS = {
    "boot-motion.ts": [
        ("// Original footage is 25 fps", S0, 1),
        ("export function bootMotion(appTime: number) {", S0, 1),
        ('  let auth = "";', S3, 1),
        ("  if (f < 363) {", S3, 1),
        ('  const step =', SD, 1),
        ("  const frame = t * 25;", S4, 1),
        ("  const scanGlitch = at(f", S4, 1),
        ("  const welcomeIntro", S5, 1),
        ('    access: "ACCESS PERMISSION REQUIRED".slice(', S1, 1),
        ("    accessOpacity:", S1, 1),
        ("    logoOpacity:", S2, 1),
        ("    logo: bootLogoTrack(frame),", S2, 1),
        ("    logoLetters:", S2, 1),
        ("    authOpacity:", S3, 1),
        ("    brand: [0, 1, 2].map", S3, 1),
        ("    poweredLetters:", S3, 1),
        ("    scanVisible:", S4, 1),
        ("    scan,", S4, 1),
        ("    ornament: t >= 21.84,", S4, 1),
        ("    welcomeVisible:", S5, 1),
        ("    welcomePanel:", S5, 1),
        ("    companyVisible:", S5, 1),
        ("    databaseOpacity:", S5, 1),
        ("    welcomeLogo: f >= 588,", S5, 1),
        ("    backgroundOpacity:", S6, 1),
        ("    white: smooth(progress(t, 26.16, 26.88)),", S6, 1),
    ],
    "boot.ts": [
        ("import { bootMotion }", S0, 1),
        ("const arc = (r: number", S4, 1),
        ("export class BootSequence {", S0, 1),
        ("  constructor(private stage: HTMLElement) {", S0, 1),
        ('this.accessLettering = new BootLettering(this.el(".access-text")', S1, 1),
        ('      ".scan > span",', S4, 1),
        ('this.authLettering = new BootLettering(this.el("#auth-message")', S3, 1),
        ("  update(time: number) {", S0, 1),
        ("this.accessLettering.setText(s.access);", S1, 1),
        ('    this.opacity(".access-text", s.accessOpacity);', S1, 1),
        ("this.contour.style.strokeDasharray", S2, 1),
        ("if (this.letters.textContent !== s.logoLetters)", S2, 1),
        ("this.plus.style.opacity = this.minus.style.opacity =", S2, 1),
        ("      `translate(${s.logo.plusX} 70)", S2, 1),
        ("      `M${-s.logo.minusWidth / 2} 0h${s.logo.minusWidth}`", S2, 1),
        ("      `translate(${s.logo.minusX} 70)", S2, 1),
        ('    this.opacity(".auth-status", s.authOpacity);', S3, 1),
        ("    this.authLettering.setText(s.auth);", S3, 1),
        ('    this.opacity(".brand", 1);', S3, 1),
        ("    this.brandLines.forEach((node, i) => {", S3, 1),
        ('    this.opacity(".powered", s.poweredLetters > 0);', S3, 1),
        ('    this.opacity(".scan", s.scanVisible);', S4, 1),
        ("if (s.scanVisible) this.renderScan(s);", S4, 1),
        ('    this.opacity(".welcome", s.welcomeVisible ? s.welcomeOpacity : 0);', S5, 1),
        ("    this.el(\".welcome\").style.transform = `scale(${s.welcomeScale})`;", S5, 1),
        ("    this.el(\".welcome\").style.filter =", S5, 1),
        ('    this.opacity(".welcome-panel", s.welcomePanel);', S5, 1),
        ('    this.opacity(".welcome-company", s.companyVisible);', S5, 1),
        ("    this.companyInk[1].querySelector(\"span\")!.style.opacity", S5, 1),
        ('    this.el(".welcome-highlight").style.clipPath =', S5, 1),
        ('    this.opacity(".welcome-database", s.databaseOpacity);', S5, 1),
        ('    this.opacity(".welcome-logo", s.welcomeLogo);', S5, 1),
        ('    this.opacity("#boot-background", s.backgroundOpacity);', S5, 1),
        ('    this.opacity(".boot-white", s.white);', S6, 1),
        ('    this.el(".boot-background svg").style.transform =', S5, 1),
        ("  private renderScan(s: ReturnType<typeof bootMotion>) {", S4, 1),
        ('    this.opacity(".scan > span", s.permissionOpacity);', S4, 1),
        ("  reset() {", S6, 1),
    ],
    "boot-tracks.ts": [
        ("// Reference-space measurements (1920×1080, 25 fps)", S0, 1),
        ("export function track(keys: readonly Key[], frame: number): number {", S0, 1),
        ("// All three lines repeat this trajectory with a two-frame offset.", S3, 1),
        ("const brandX = [", S3, 1),
        ("export const brandTrack = (frame: number, line: number) => {", S3, 1),
        ("// Frames 590–591 cut the layer out", S5, 1),
        ("const highlightKeys: readonly Key[] = [", S5, 1),
        ("export const companyTrack = (frame: number) =>", S5, 1),
        ("export function scanTrack(frame: number) {", S4, 1),
    ],
    "boot-logo-tracks.ts": [
        ("const draw = [", S2, 1),
        ("const movingCut = [", S2, 1),
        ("const leftEdge = [", S2, 1),
        ("export function bootLogoTrack(frame: number) {", S2, 1),
    ],
    "boot-orbit-tracks.ts": [
        ("const sides = [", S4, 1),
        ("const columns = Array.from({ length: 9 }", S4, 1),
        ("const orbit = [", S4, 1),
        ("const dotGrowth = [", S4, 1),
        ("export function scanOrbitTrack(frame: number) {", S4, 1),
    ],
    "boot-lettering.ts": [
        ("export async function loadBootWebfonts() {", S0, 1),
        ("export class BootLettering {", S0, 1),
        ("  constructor(private host: HTMLElement, keys: PhraseKey[]) {", S0, 1),
        ("  useWebfonts() {", S0, 1),
        ("  setText(value: string) {", S0, 1),
    ],
    "brand.ts": [
        ("const paths = `", S2, 1),
        ("export const labelMarkSvg =", S0, 1),
        ("export const logo = `", S2, 1),
        ("export const bootMarkContour =", S2, 1),
        ("export const brandHeading =", S3, 1),
    ],
    "audio.ts": [
        ("export const BOOT_CUES:", S0, 1),
        ("export function synthesizeSound(", S0, 1),
        ("export class TerminalAudio {", S0, 1),
        ("  restartBoot() {", S0, 1),
        ("  updateBoot(appTime: number, frozen = false) {", S0, 1),
        ("    const phase = time < 22.76", S0, 1),
        ("    for (const cue of BOOT_CUES)", S0, 1),
        ('    if (hasTypingBetween(previous, time)) this.play("key");', S3, 1),
    ],
    "typing-rhythm.ts": [
        ("// Use the actual 25 fps text reveal", S3, 1),
        ("export const TYPING_FRAMES: readonly number[] = [", S3, 1),
        ("export function hasTypingBetween(", S3, 1),
    ],
    "typing-samples.ts": [
        ("export const TYPING_SAMPLE_RATE = 48000;", S3, 1),
    ],
    "asset-url.ts": [
        ("export const assetUrl = (path: string) => {", S0, 1),
    ],
    "theme-ui.ts": [
        ("const palette = {", S0, 1),
        ("export function paintTheme(amount: number) {", S0, 1),
    ],
    "boot-lettering.css": [
        ("/* Fixed Novecento phrase drawings;", S3, 1),
        ("#auth-message {", S3, 1),
        (".auth-status { top: 527px;", S3, 1),
        (".welcome-company {", S5, 1),
        (".brand h1 {", S3, 1),
    ],
    "hud-projection.ts": [
        ("export", S0, 1),
    ],
    "startup.ts": [
        ("export class StartupGate", S0, 1),
    ],
}

# ── 片段抽取范围（原文件行号，含首尾）──────────────────────────────────────
SEGMENTS = [
    (
        "src/main.ts",
        "片段/main.ts.开场片段.ts",
        [
            (27, 30, "开场模块 import"),
            (53, 54, "StartupGate / 加载门 import"),
            (60, 60, "startup.css import"),
            (74, 76, "开场 DOM 注入前的取节点工具"),
            (77, 121, "开场 DOM 全部标记 + BootSequence 实例化"),
            (127, 141, "模式与开场起点 bootStart / frozenTime"),
            (143, 156, "冻帧调试入口"),
            (941, 988, "bootFrame：开场时间轴分段 + 交给三维"),
            (1000, 1046, "frame：每帧调度，22 秒前开场层盖住三维"),
            (1182, 1212, "completeStartup：点击开始 / 白场起点 1.76"),
            (639, 649, "replayBoot：重播开场"),
            (484, 545, "setMode：切模式与开场 reset / inert"),
        ],
    ),
    (
        "src/style.css",
        "片段/style.css.开场段.css",
        [
            (95, 340, "开场基础样式：brand / powered / boot-background / boot / boot-logo / auth-status / access-text / scan / welcome"),
            (1810, 1813, "开场覆盖：powered 字号、boot-background svg 透明度"),
            (2138, 2231, "开场覆盖：帧驱动（禁 CSS 过渡）、boot-white、scan、welcome 全组、退出隐藏"),
        ],
    ),
    (
        "src/responsive.css",
        "片段/responsive.css.开场段.css",
        [
            (5, 12, "开场多分辨率：opening 版式、boot / boot-white / scan 缩放、竖屏字号"),
            (18, 19, "开场期间的 PWA 提示隐藏"),
            (30, 31, "移动端开场入口"),
            (48, 51, "紧凑/竖屏下 brand 与 powered 处理"),
            (104, 104, "竖屏 brand 缩放"),
            (208, 208, "紧凑版式 brand 缩放"),
        ],
    ),
]


def ana(line: str) -> str:
    """把标记追加到行尾；行尾已有注释的仍然追加，保持行数不变。"""
    return line.rstrip("\n")


def main() -> int:
    src = UPSTREAM / "src"
    if not src.is_dir():
        print(f"找不到上游源码目录 {src}", file=sys.stderr)
        return 1

    (OUT / "源码" / "src").mkdir(parents=True, exist_ok=True)
    (OUT / "源码" / "片段").mkdir(parents=True, exist_ok=True)
    (OUT / "标记").mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    digest: list[str] = []

    # ── 1 & 3. 拷贝 + 生成标记版 ──────────────────────────────────────────
    for name in CORE + RELATED:
        path = src / name
        if not path.is_file():
            errors.append(f"缺失文件 {name}")
            continue
        data = path.read_bytes()
        (OUT / "源码" / "src" / name).write_bytes(data)
        digest.append(f"{sha256(data).hexdigest()}  src/{name}")

        text = data.decode("utf-8")
        lines = text.split("\n")

        marks = MARKS.get(name, [])
        used: dict[str, int] = {}
        for anchor, stage, occurrence in marks:
            hits = [i for i, ln in enumerate(lines) if anchor in ln]
            if len(hits) < occurrence:
                errors.append(
                    f"{name}: 锚点找不到 第{occurrence}次 → {anchor!r}（命中 {len(hits)} 行）"
                )
                continue
            idx = hits[occurrence - 1]
            tag = MARK_PREFIX + stage
            if lines[idx].rstrip().endswith(tag.strip()):
                continue
            lines[idx] = ana(lines[idx]) + tag

        # JSON 不能加注释：原样拷，标记只在 00-流程标记.md 里
        if name.endswith(".json"):
            (OUT / "标记" / name).write_bytes(data)
        else:
            (OUT / "标记" / name).write_text("\n".join(lines), encoding="utf-8")

    # ── 2. 片段抽取 ───────────────────────────────────────────────────────
    for src_rel, dst_rel, ranges in SEGMENTS:
        src_path = UPSTREAM / src_rel
        if not src_path.is_file():
            errors.append(f"缺失文件 {src_rel}")
            continue
        all_lines = src_path.read_text(encoding="utf-8").split("\n")
        total = len(all_lines)
        body: list[str] = [
            f"// 剥离自 {src_rel}（仅开场相关行段）。行号 = 原文件行号。",
            f"// 上游：{UPSTREAM}  {src_rel} 共 {total} 行",
            "",
        ]
        for a, b, note in ranges:
            if b > total:
                errors.append(f"{src_rel}: 行段 {a}-{b} 超出文件（共 {total} 行）")
                continue
            body.append(f"// ───── 原 {src_rel}:{a}-{b}  {note} ─────")
            for n in range(a, b + 1):
                body.append(f"{all_lines[n - 1]}")
            body.append("")
        (OUT / "源码" / dst_rel).write_text("\n".join(body), encoding="utf-8")

    # ── 4. 自检：标记版与原文件行数必须一一对应 ────────────────────────────
    for name in CORE + RELATED:
        a = src / name
        b = OUT / "源码" / "src" / name
        c = OUT / "标记" / name
        if not (a.is_file() and b.is_file() and c.is_file()):
            continue
        if a.read_bytes() != b.read_bytes():
            errors.append(f"{name}: 源码副本与上游不一致")
        if name.endswith(".json"):
            continue
        la = len(a.read_text(encoding="utf-8").split("\n"))
        lc = len(c.read_text(encoding="utf-8").split("\n"))
        if la != lc:
            errors.append(f"{name}: 标记版行数 {lc} ≠ 原文件 {la}")
        # 把标记后缀全部剥掉后，必须逐字节等于上游原文件
        stripped = "\n".join(
            ln[: ln.index(MARK_PREFIX)] if MARK_PREFIX in ln else ln
            for ln in c.read_text(encoding="utf-8").split("\n")
        )
        if stripped != a.read_text(encoding="utf-8"):
            errors.append(f"{name}: 剥掉标记后与上游不一致（标记不是纯行尾注释）")

    (OUT / "源码" / "校验.sha256").write_text("\n".join(digest) + "\n", encoding="utf-8")

    tag_lines = sum(
        1
        for name in CORE + RELATED
        if not name.endswith(".json")
        and (OUT / "标记" / name).is_file()
        for ln in (OUT / "标记" / name).read_text(encoding="utf-8").split("\n")
        if MARK_PREFIX in ln
    )
    print(f"剥离文件 {len(CORE)} 个核心 + {len(RELATED)} 个相邻；标记行 {tag_lines} 处")

    if errors:
        print("\n发现 %d 个问题：" % len(errors), file=sys.stderr)
        for e in errors:
            print("  ✗ " + e, file=sys.stderr)
        return 2
    print("自检通过：源码副本逐字节等于上游，标记版与源码版行号一一对应")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
