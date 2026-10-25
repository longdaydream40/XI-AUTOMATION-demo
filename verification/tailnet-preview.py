#!/usr/bin/env python3
"""Tailnet preview for the XI opening. Static files plus three short URLs.

  /            entry list
  /all         full sequence (拼接.html)
  /portrait    portrait + backspace only (index-bw.html)
  /welcome     welcome + scan ring (XI-开场动画/dist/index.html)

Binds to the Tailscale address by default; override with --host/--port.
"""
import argparse
import functools
import http.server
import socket
import subprocess
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    "/all": "拼接.html",
    "/portrait": "index-bw.html",
    "/welcome": "XI-开场动画/dist/index.html",
}
ENTRIES = [
    ("/all", "整条", "头像 → 欢迎页 → 扫描环，6.68 秒加 4.80 秒，段间 120ms 交叠"),
    ("/portrait", "头像段", "区块拼装、局部闪烁、XI 滑入、逐字退格；点击或按 R 重播"),
    ("/welcome", "欢迎与扫描环", "WELCOME TO / XI AUTOMATION 扫亮，双环收拢"),
]
LANDING = """<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#000000"><title>XI AUTOMATION</title>
<style>
html,body{margin:0;min-height:100%;background:#000;color:#f2f0ec;
 font:16px/1.6 "MiSans","PingFang SC","Microsoft YaHei",system-ui,sans-serif}
main{max-width:34rem;margin:0 auto;padding:12vh 6vw calc(8vh + env(safe-area-inset-bottom))}
h1{margin:0 0 .3em;font-size:clamp(28px,8vw,44px);letter-spacing:.04em;font-weight:700}
p.lead{margin:0 0 2.4em;color:#8a8a86;font-size:14px;letter-spacing:.02em}
a{display:block;padding:1em 1.1em;margin:0 0 .8em;border:1px solid #2c2c2a;border-radius:3px;
 text-decoration:none;color:inherit;-webkit-tap-highlight-color:transparent}
a:active{border-color:#b22430;background:#111}
b{display:block;font-size:17px;font-weight:700;letter-spacing:.03em}
span{display:block;margin-top:.35em;color:#8a8a86;font-size:13px;line-height:1.5}
em{color:#b22430;font-style:normal}
</style></head><body><main>
<h1>XI AUTOMATION</h1>
<p class="lead">开场动画预览 · 走 Tailscale，只在你的网络里</p>
%(links)s
<p class="lead" style="margin:2em 0 0">手机竖屏已经做过版式适配。<em>鼠标透视倾斜</em>只在带鼠标的设备上生效。</p>
</main></body></html>"""  # %(links)s placeholder; CSS above contains %, so replace() is used below


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            links = "".join(
                f'<a href="{url}"><b>{title}</b><span>{note}</span></a>' for url, title, note in ENTRIES)
            body = LANDING.replace("%(links)s", links).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ALIASES:
            self.path = "/" + urllib.parse.quote(ALIASES[path])
        super().do_GET()

    def end_headers(self):
        # Always revalidate so a rebuild shows up on the next pull-to-refresh.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        print("%s %s" % (self.address_string(), fmt % args), flush=True)


def default_host():
    # hostname resolution often returns 127.0.1.1, so ask Tailscale first.
    try:
        out = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=5)
        for line in out.stdout.split():
            if line.startswith("100."):
                return line
    except (OSError, subprocess.SubprocessError):
        pass
    for *_, sockaddr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        if sockaddr[0].startswith("100."):
            return sockaddr[0]
    raise SystemExit("No Tailscale address found; pass --host explicitly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=default_host())
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    handler = functools.partial(Handler, directory=str(ROOT))
    with http.server.ThreadingHTTPServer((args.host, args.port), handler) as server:
        print(f"serving {ROOT} on http://{args.host}:{args.port}/", flush=True)
        server.serve_forever()
