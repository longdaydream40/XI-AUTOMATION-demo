# XI AUTOMATION 开场动画 · 工作区

三段式开场：头像拼装与退格（4.80 秒）→ 欢迎页（3.40 秒）→ 扫描环（3.275 秒）。
黑底、暖白、一枚暗红。风格规则见 [`design.md`](design.md)。

## 从哪里看

| 入口 | 内容 | 打开方式 |
|---|---|---|
| `拼接.html` | 整条：头像 → 欢迎 → 扫描环，段间 120 毫秒交叠 | 需 HTTP（Vite 产物是 ES 模块） |
| `index-bw.html` | 头像段，自包含 | 双击即可（`file://`） |
| `XI-开场动画/dist/index.html` | 欢迎页与扫描环 | 需 HTTP |
| `发包/01-头像段/index.html` | 拆分后的单文件版，4.80 秒 | 双击即可 |
| `发包/02-欢迎页/index.html` | 拆分后的单文件版，3.40 秒 | 双击即可 |
| `发包/03-扫描环/index.html` | 拆分后的单文件版，3.275 秒 | 双击即可 |

本地起服务：`python3 -m http.server 8000 --bind 127.0.0.1`，然后开 `http://127.0.0.1:8000/拼接.html`。
手机预览走 `verification/tailnet-preview.py`（只绑 Tailscale 地址，见 `XI-开场动画/README.md`）。

## 目录

```
设计/
├── 拼接.html                 整条播放器（两个 iframe + 120ms 交叠）
├── index-bw.html             头像段产物（单文件，构建生成）
├── design.md                 风格说明：用色、节奏表、运动规则、反例清单
├── 打包.py                   把三段拆成自包含页面与 zip，输出到 发包/
├── 发包/                     交付物（生成，已 gitignore）
├── glitch-boot/              头像段的源码与构建（canvas + 192 区块）
│   └── docs/                 技法、性能、参考拆解、历史审计
├── XI-开场动画/              欢迎页与扫描环的源码（Vite + TS）与 dist
├── shared/                   playback.js（可取消时钟）与 tilt.js（透视倾斜）
├── verification/             逐帧检查、浏览器实测、截图、RESULTS.md
├── 参考提取/                 上游 RhineLabUI 开场段的源码留档（不参与构建）
├── 温曦头像-SVG/             头像源素材（build.py 只读引用）
└── 温曦-人格重构/            与动画无关的人格提示词文档
```

## 构建

```bash
python3 -B glitch-boot/build.py          # 头像段 → index-bw.html（需要 Pillow、NumPy）
npm --prefix XI-开场动画 run build        # 欢迎 + 扫描环 → dist/
python3 -B 打包.py                        # 三段拆分包 → 发包/（需要前两条先跑）
```

**改源码，不要手改 `index-bw.html`、`XI-开场动画/dist/`、`发包/`。** `shared/` 被内联进两条链，改完两边都要重建。

## 验证

```bash
node verification/logic-check.cjs                  # 无浏览器的确定性检查
python3 -B verification/browser-check.py --quick   # 真实浏览器播放与截图
python3 -B XI-开场动画/剥离.py                      # 只读：源码哈希与相对导入
```

最新一轮的数字与没验的部分写在 `verification/RESULTS.md`。

## 其他说明

- `拼接.html` 与 `dist/` 通过 `postMessage` 通讯：子页面报告 `ready` / `started`，父页面才计时。
- 扫描环是不跟随鼠标的读数，进入该阶段后倾斜会关闭。
- 上游 RhineLabUI 为 MIT；Novecento 字体不随 MIT 转让，本项目改用 Cal Sans 与 MiSans。
