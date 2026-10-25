#!/usr/bin/env python3
"""把 XI 开场动画拆成三个可以单独拿走、单独双击打开的自包含页面。

    发包/01-头像段/index.html   头像拼装 + XI 退格删除，4.80 秒
    发包/02-欢迎页/index.html   WELCOME TO / XI AUTOMATION 扫亮，3.40 秒
    发包/03-扫描环/index.html   双环收拢，3.275 秒
    发包/design.md             风格说明（根目录 design.md 的副本）

只读取构建产物（根目录 index-bw.html、XI-开场动画/dist），把外链的 CSS、JS、
字体全部内联成 data URI；不改产物本身。三个入口都只依赖一个 .html 文件。

先跑两条构建，再执行本脚本：
    python3 -B glitch-boot/build.py
    npm --prefix XI-开场动画 run build
    python3 -B 打包.py
"""
import base64
import hashlib
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "XI-开场动画" / "dist"
OUT = ROOT / "发包"
ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# 目录名, 压缩包名, 标题, 来源：portrait = 单文件头像页；welcome/scan = 构建产物里的一幕
PACKAGES = [
    ("01-头像段", "XI-开场-01-头像段.zip", "XI AUTOMATION · 头像段", "portrait"),
    ("02-欢迎页", "XI-开场-02-欢迎页.zip", "XI AUTOMATION · 欢迎", "welcome"),
    ("03-扫描环", "XI-开场-03-扫描环.zip", "XI AUTOMATION · 扫描环", "scan"),
]


def data_uri(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def inline_css(css: str, base: Path) -> str:
    def swap(match: re.Match) -> str:
        ref = match.group(1).strip("'\"")
        if ref.startswith(("data:", "http:", "https:")):
            return match.group(0)
        target = (base / ref).resolve()
        suffix = target.suffix.lower()
        if not target.is_file():
            raise SystemExit(f"CSS 引用的文件不存在：{target}")
        if suffix == ".woff2":
            mime = "font/woff2"
        elif suffix == ".css":
            raise SystemExit("产物 CSS 里还有 @import，需要先合并")
        else:
            mime = "application/octet-stream"
        return f"url({data_uri(target, mime)})"

    return re.sub(r"url\(([^)]+)\)", swap, css)


def build_act(stage: str, title: str) -> str:
    html = (DIST / "index.html").read_text(encoding="utf-8")
    css_link = re.search(r'<link rel="stylesheet"[^>]*href="([^"]+)"[^>]*>', html)
    js_script = re.search(r'<script type="module"[^>]*src="([^"]+)"[^>]*></script>', html)
    if not (css_link and js_script):
        raise SystemExit("dist/index.html 结构变了：找不到 CSS 或模块脚本")

    css = inline_css((DIST / css_link.group(1)).read_text(encoding="utf-8"), (DIST / css_link.group(1)).parent)
    js = (DIST / js_script.group(1)).read_text(encoding="utf-8")
    if "</script" in js.lower():
        raise SystemExit("产物脚本里出现 </script，不能直接内联")

    html = html.replace(js_script.group(0),
                        f'<script>window.__XI_STAGE__="{stage}";</script>\n'
                        f'<script type="module">\n{js}</script>')
    html = html.replace(css_link.group(0), f"<style>\n{css}</style>")
    # 字体已内联进 CSS，预加载那一行没有意义，还会在 file:// 下多一次失败请求。
    html = re.sub(r'\n\s*<link rel="preload"[^>]*>', "", html)
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1)
    return html


def build_portrait(title: str) -> str:
    html = (ROOT / "index-bw.html").read_text(encoding="utf-8")
    if "{{" in html:
        raise SystemExit("index-bw.html 里还有未填充的模板字段，先跑 glitch-boot/build.py")
    return re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1)


def check_self_contained(name: str, html: str) -> None:
    """任何还会去硬盘或网络取文件的引用都算漏网。"""
    leftovers = [m for m in re.findall(r'(?:src|href)="([^"]*)"', html)
                 if not m.startswith(("data:", "#"))]
    if leftovers:
        raise SystemExit(f"{name} 仍引用外部文件：{leftovers}")


def write_zip(folder: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        entry = zipfile.ZipInfo(f"{folder.name}/index.html", date_time=ZIP_TIME)
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        archive.writestr(entry, (folder / "index.html").read_bytes())


def main() -> None:
    for required in (ROOT / "index-bw.html", DIST / "index.html"):
        if not required.exists():
            raise SystemExit(f"缺少构建产物：{required}")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    rows = []
    for folder_name, zip_name, title, source in PACKAGES:
        html = build_portrait(title) if source == "portrait" else build_act(source, title)
        check_self_contained(folder_name, html)
        folder = OUT / folder_name
        folder.mkdir()
        (folder / "index.html").write_text(html, encoding="utf-8")
        write_zip(folder, OUT / zip_name)
        raw = (folder / "index.html").read_bytes()
        rows.append((folder_name, len(raw), hashlib.sha256(raw).hexdigest()[:12],
                     (OUT / zip_name).stat().st_size))

    design = ROOT / "design.md"
    if design.exists():
        shutil.copy2(design, OUT / "design.md")

    for folder_name, size, digest, packed in rows:
        print(f"{folder_name:10} {size:>9,} B  sha256:{digest}  压缩包 {packed:>8,} B")


if __name__ == "__main__":
    main()
