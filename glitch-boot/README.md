# glitch-boot · 头像引擎

产出根目录的 `index-bw.html`：黑白侧颜头像、192 个区块的拼装与局部闪烁、`XI` 与 `AUTOMATION` 的滑入、逐字退格删除。单文件自包含，可双击直接打开。

## 构建

```bash
# 在 /home/xuan/设计 下执行；需要 Pillow、NumPy
python3 -B glitch-boot/build.py
```

`engine.template.html` 是模板，`build.py` 负责把固定像素运算和资源内联进去：

- 读取 `温曦头像-SVG/温曦-侧颜头像-透明底.png`（只读，不修改原图）
- 用面部掩膜挖空脸与外部背景、色阶量化、横向扫描线、红发夹保留
- 生成透明底头像与青雾底两版 PNG
- 内联 Cal Sans 字体、以及 `shared/tilt.js`、`shared/playback.js`

浏览器端只解码和合成，不再逐像素处理，也不再引用任何外部文件。

## 时间轴

| 帧 | 内容 |
|---:|---|
| 0–26 | 192 个区块由面部向外拼装；区块出现时间连续分布在整个窗口内 |
| 28–40 | 唯一的故障窗：局部区块闪烁，参与率随进度衰减 |
| 40–66 | 头像左移到位，`XI` 与 `AUTOMATION` 依次滑入 |
| 84–104 | 光标出现，逐字退格删除 `XI`（每字 10 帧：7 帧里光标扫过字形、字形同步淡出，光标落到新位置时字刚好消失，再停 3 帧） |
| 104–120 | 光标停在行首闪烁；播放结束 |

整片 4.80 秒。位置与透明度按显示刷新率连续计算，区块闪烁与光标节拍仍按每秒 25 帧的编辑节奏。

## 交互与状态

- 鼠标透视倾斜由 `shared/tilt.js` 提供，作用在外层 `.tilt-plane`；头像与文字在不同的 3D 深度上。
- 点击画面或按 R 重播；嵌入 `拼接.html` 时改为通知父页面重播整条动画。
- 页面隐藏时暂停；重播会取消旧回调，不会叠加循环。
- `?f=78` 或 `?t=3.12` 冻帧；冻帧下倾斜被禁用。`window.__xiPlayback` 暴露时间、就绪、结束状态与绘制次数。

## 圆角重播按钮已移除

重播只保留点击画面与 R 键两种入口，页面上不再有可见控件。

## 校验

```bash
node verification/logic-check.cjs
python3 -B verification/browser-check.py --quick
```

生成的头像是构建期产物，改调色板、掩膜或扫描线请改 `build.py`，不要手改 `index-bw.html`。

## docs/

| 文件 | 说明 |
|---|---|
| `history-before-xi.md` | 重构前的交接文档，保留当时的实测数字与坑 |
| `code-audit.md`、`perf-audit.md`、`requirement-audit.md`、`visual-audit.md` | **历史文档**，审计的是旧版本 |
| `glitch-techniques.md`、`perf-guidelines.md`、`rhinelab-reference.md` | 通用技法与参考拆解，与版本无关 |
