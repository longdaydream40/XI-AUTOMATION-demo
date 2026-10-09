# WENSI 开场动画

只有开场。黑底，没有文案，最后落在「WELCOME TO / WENSI AUTOMATION」上。

从 [RhineLabUI](https://github.com/LBEILC/RhineLabUI)（MIT，`12cc5e4`）里把开场动画这一段剥出来，
其余全部去掉：三维档案阵列、档案详情、工作台、壁纸模式、PWA、游戏手柄、音频。

---

## 跑起来

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 dist/，纯静态，丢哪都能跑
```

两个调试参数（和上游同口径）：

| 参数 | 作用 |
|---|---|
| `?t=13.28` | 从指定 appTime 起播。`1.76` 是默认起点（白场那一帧） |
| `?t=13.28&freeze=1` | 只画那一帧，不往下走。对帧用 |

时间口径：原片 25 fps，`appTime 0` = 原片第 5 秒，所以 **帧号 = (appTime + 5) × 25**。

- 入场 `appTime 1.76` = 白场 = 原片第 169 帧
- ∞ 标志画完 + 左移落定 ≈ `appTime 6.1`（原片第 278 帧）
- 扫描双环 ≈ `appTime 14.48`（原片第 487 帧）
- 欢迎页 ≈ `appTime 17.76`（原片第 569 帧）
- **停在 `appTime 21.16` = 原片 26.16 s = 第 654 帧**，白场起涨之前

---

## 改什么，去哪里改

| 想改 | 去哪 |
|---|---|
| 底色、墨色、字号、哪几个字显示 | `src/黑场开场.css` |
| 「WENSI AUTOMATION」这行字 | `src/main.ts` 里那段 DOM 模板 |
| 动画停在哪儿 | `src/main.ts` 的 `const END`（单位是 appTime，= 原片秒数 - 5） |
| ∞ 标记本身 | `src/brand.ts` 的 `paths` / `bootMarkContour` |
| 时间轴、缓动、轨迹 | `src/boot-motion.ts` + `src/boot-*.ts` |

**`src/` 里那 9 个动画文件是上游的逐字节副本，一行没改**（`boot.ts` / `boot-motion.ts` /
`boot-tracks.ts` / `boot-orbit-tracks.ts` / `boot-logo-tracks.ts` / `boot-lettering.*` / `brand.ts`）。
颜色和文案的改动全在 `黑场开场.css` 和 `main.ts`。想回到米色原版：删掉 `黑场开场.css` 的 import，
再把 `main.ts` 里那行 `WENSI AUTOMATION` 换回 `RHINE LAB.LLC.`。

改完跑一次 `python3 剥离.py` —— 它会重新搬运逐字节副本、重挑 CSS，并检查动画文件有没有被改动。

---

## 目录

```
WENSI-开场动画/
├── index.html
├── vite.config.ts          只有一句 __RHINE_NOVECENTO__: false（没有授权字体，走作者画的字形）
├── 剥离.py                 可复现的搬运 + 自检脚本
├── 源码校验.sha256         9 个动画文件的 sha256，可与上游核对
├── 预览/                   三张截图
├── public/
│   ├── favicon.svg
│   └── fonts/
│       ├── misans/bold-0.woff2    44 KB（上游 753 个分片共 26 MB，只要覆盖拉丁的那一个）
│       ├── LICENSE-MiSans.pdf
│       └── NOTICE.txt
└── src/
    ├── main.ts             ★ 手写：建 DOM、算版式、每帧写 DOM（102 行）
    ├── 黑场开场.css        ★ 手写：黑底、墨色翻白、文案层关闭、欢迎页扫过反过来
    ├── fonts.css           ★ 手写：一个 @font-face
    ├── style.css           生成：按选择器从上游挑出来的 78 条规则
    ├── boot.ts             ┐
    ├── boot-motion.ts      │
    ├── boot-tracks.ts      │
    ├── boot-orbit-tracks.ts│ 上游逐字节副本，
    ├── boot-logo-tracks.ts │ 一行没改
    ├── boot-lettering.ts   │
    ├── boot-lettering.css  │
    ├── boot-lettering-art.json
    ├── brand.ts            ┘
    ├── theme-ui.ts         ★ 手写：上游是整套调色板插值，这里只需要 themeAmount = 0
    ├── asset-url.ts        ★ 手写：上游要给三维模型算哈希路径，这里只要基路径
    └── vite-env.d.ts
```

---

## 剥掉了什么

| | 上游 | 这里 |
|---|---|---|
| `main.ts` | 1785 行（档案阵列 / 详情 / 工作台 / 壁纸 / PWA / 手柄 / 音频 / 弹窗） | 102 行 |
| `style.css` | 2287 行（整个界面） | 548 行（78 条规则，只留开场） |
| `responsive.css` | 229 行 | 挑出 6 条规则并进 `style.css` |
| `theme.css` | 69 行（亮/暗双主题） | 无 |
| `fonts.css` | 753 个 `@font-face`、26 MB | 1 个、44 KB |
| JS 依赖 | `three` + `@kitlangton/rolling-number` | 无（零运行时依赖） |
| 音频 | 670 行 + 2.9 MB ogg | 无 |
| 构建产物 | 991 KB JS + 667 KB CSS | **52 KB JS + 9.3 KB CSS** |
| 源码 + 资源 | 353 MB | **261 KB**（不含预览图；克隆仓库 353 MB） |

---

## 自检

```bash
python3 剥离.py
```

四项，任一不过退出码 2：

1. 9 个动画文件逐字节等于上游；
2. `style.css` 里每一条规则都能在上游 `style.css` / `responsive.css` 里逐字找到（防手改漂移）；
3. 手写的几个文件里不许出现 `three` / `archive` / `workbench` / `wallpaper` / `pwa` 这些词的整词；
4. `src/` 里每个 `import "./x"` 都能落地。

当前：**通过**。产物渲染结果与上游黑场版逐像素对比，平均差 0.14–0.52 / 255（差异来自截图时的帧偏移与抗锯齿，不是内容差异）。

---

## 已知限制

- **没有声音。** 开场的配乐和音效在上游 `audio.ts`（670 行）和 `public/audio/`（2.9 MB）里，
  这次一并剥掉了。浏览器不允许无点击自动出声，要留的话得再加一个「点一下开始」的门。
- **没有三维。** 白场涨满之后上游会露出档案阵列，这里停在白场之前（`appTime 21.16` / 原片 26.16 s / 第 654 帧）。
  想连白场一起放，把 `main.ts` 的 `END` 改成 `21.92`（原片 26.92 s），画面会停在满屏白。
- 上游 `verification/BOOT-MOTION.md` 自己注明：轨迹是逐帧目测 + 测量脚本拟合出来的，
  长得像原始工程数据但不是。抄数值的时候心里有数。
- Novecento 字体不随 MIT 转让，上游仓库里也没有；这里没有它，逐字排版走上游的
  「作者逐字导出的 SVG 字形」那条分支（`__RHINE_NOVECENTO__ = false`）。
