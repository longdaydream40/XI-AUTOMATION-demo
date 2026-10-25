# XI AUTOMATION 开场

纯黑底、暖白文字、暗红绕行点。名称已统一为 **XI**。

## 入口

- 整条动画：项目根目录的 `拼接.html`。
- 头像与退格：根目录 `index-bw.html`，自包含，可直接用浏览器打开。
- 欢迎与扫描环：`XI-开场动画/dist/index.html`，需要通过 HTTP 网页服务打开。

在 `/home/xuan/设计` 运行本地预览：

```bash
python3 -m http.server 8000 --bind 127.0.0.1
# http://127.0.0.1:8000/拼接.html
```

### 走 Tailscale 在手机上看

```bash
setsid nohup python3 -u verification/tailnet-preview.py --port 8790 > /tmp/xi-preview.log 2>&1 < /dev/null &
```

服务只绑定 Tailscale 网卡地址，局域网与公网都连不上。打开 `http://<tailscale-ip>:8790/`，首页是三个入口：

| 地址 | 内容 |
|---|---|
| `/all` | 整条：头像 → 欢迎页 → 扫描环 |
| `/portrait` | 头像段，点画面或按 R 重播 |
| `/welcome` | 欢迎页与扫描环 |

停止：按端口找进程 `ss -lntp | grep 8790` 后 `kill`，或 `pkill -f 'tailnet[-]preview'`（写成 `tailnet[-]preview` 是为了让这条命令不匹配它自己）。

改完源码重新构建，刷新页面就是新版 —— 服务加了 `no-cache`，不需要重启。

## 播放与交互

| 阶段 | 时长 | 内容 |
|---|---:|---|
| 头像 | 4.80 秒 | 192 个区块拼装、局部闪烁、头像与 XI 滑入、逐字退格 |
| 欢迎 | 3.40 秒 | WELCOME TO / XI AUTOMATION，文字扫亮，末尾短淡出 |
| 扫描环 | 3.275 秒 | 双环收拢、侧弧与卫星点出现，最后停住 |

- **鼠标透视倾斜**：上下最大 9°，左右最大 12°。指向的边缘抬起，头像和文字有不同的前后深度。约 95ms 的指数平滑跟随，离开后归位。
- **扫描环阶段不跟随鼠标**：环是一块读数，不是可把玩的场景。进入这一幕时倾斜立刻归零，回到欢迎页才恢复。
- 触屏和系统“减少动态效果”设置不会启用倾斜；冻帧也禁用倾斜，保证可重复截图。
- **R 键重播**；点击头像段也能重播。嵌入拼接页时重播的是整条动画。
- 页面隐藏时暂停，恢复时继续；重播取消旧回调。播放结束和鼠标静止后不保留空转循环。
- 拼接页先预载两段，收到准备完成通知后才开始。段间是 120ms 的短交叠，不再临时加载下一段。
- 扫描环的空间轨迹保留参考项目数据；离散闪切仍按每秒 25 帧的编辑节奏，位置与透明度按显示刷新连续计算。

## 调试参数

| 入口 | 参数 |
|---|---|
| `拼接.html` | `?order=ba` 反放两大段；`?cut=4.8` 指定头像段切点；`?at=7` 整片冻帧；`?a=...&b=...` 使用实现同一消息协议的替代页面 |
| `index-bw.html` | `?f=78` 或 `?t=3.12` 冻帧 |
| `dist/index.html` | `?t=2` 从该时间播放；`?t=2&freeze=1` 冻帧；`?stage=welcome` 或 `?stage=scan` 只播其中一幕 |
| `dist/index.html` | `?zoom=2.4` 竖屏放大；`?wscale=.7` 文案倍率；`?dot=b22430` 绕行点颜色 |

`window.__xiPlayback` 提供当前时间、就绪状态、结束状态和绘制次数；拼接页用 `window.__xiSequence`。
这些状态不启动额外的逐帧统计循环。

## 源码与构建

```bash
# 在 /home/xuan/设计 下执行
python3 -B glitch-boot/build.py
npm --prefix XI-开场动画 run build
```

头像构建需要 Pillow、NumPy。构建期完成面部掩膜、外背景透明化、色阶与扫描线处理，内联处理后的 PNG、字体和共享脚本。浏览器只解码与合成，不再现场逐像素计算。

| 文件 | 职责 |
|---|---|
| `../shared/playback.js` | 可取消的时钟、资源准备、暂停恢复、父子页面消息 |
| `../shared/tilt.js` | 独立外层透视、鼠标跟随、归位、空闲停止 |
| `src/main.ts` | 可见页面结构、响应式布局、欢迎→扫描的时间映射 |
| `src/boot.ts` | 当前可见阶段的属性更新与写入缓存 |
| `src/boot-motion.ts` | 编辑节奏、阶段判定，只计算当前阶段 |
| `src/boot-tracks.ts`、`src/boot-orbit-tracks.ts` | 固定轨迹；缓存插值切线，不逐帧重建键表 |
| `src/黑场开场.css` | 文字比例、纯黑背景、前后深度、手机适配 |
| `../glitch-boot/engine.template.html` | 头像合成、连续位移、光标与字符退格 |

**不要手改 `dist/` 或 `index-bw.html`。** 共享脚本变更后，两条构建都要执行。

## 校验不会覆盖工作文件

```bash
python3 -B XI-开场动画/剥离.py
```

默认只读：核对本地源码 SHA-256 校验值与相对导入，不再从参考仓库覆盖文件。

```bash
# 仅在审阅完有意修改之后，记录新源码校验值
python3 -B XI-开场动画/剥离.py --record

# 如需重新取参考源码，必须指定尚不存在的新目录
python3 -B XI-开场动画/剥离.py --import-upstream /tmp/rhine-reference-new
```

## 测试与预览

```bash
node verification/logic-check.cjs
python3 -B verification/browser-check.py --quick
python3 -B verification/browser-check.py
```

浏览器测试使用本机 Chromium 与 Chrome DevTools Protocol（CDP，浏览器调试协议），需要 Python 的 `websocket-client`。只绑定本地回环地址，测试结束自动关闭浏览器和测试服务。

- 本目录 `预览/`：更新后的七张欢迎页、扫描环截图。
- `../verification/screenshots/`：头像桌面/手机、退格、头像与欢迎页的鼠标倾斜，以及扫描环不跟随鼠标的对照图。
- `../verification/RESULTS.md`：验证范围、性能数据及限制。

## 拆分发包

`打包.py` 把三段拆成三个自包含页面（CSS、脚本、字体、头像内联，`file://` 直接打开），
连同根目录 `design.md` 一起写到 `发包/`，并各自打一个 zip：

```bash
python3 -B glitch-boot/build.py
npm --prefix XI-开场动画 run build
python3 -B 打包.py
```

欢迎页与扫描环包在构建产物里写死 `window.__XI_STAGE__`，只播对应那一幕；
改源码后重新构建再打包，不要手改 `发包/` 里的文件。

## 来源

轨迹和 WELCOME TO 字形美术来自 [RhineLabUI](https://github.com/LBEILC/RhineLabUI)，MIT，参考提交 `12cc5e4`。当前运行代码已有本地优化，**不再声称逐字节等于上游**。
MiSans 字体许可保留在 `public/fonts/`。未添加音频、三维模型依赖、额外网络资源。
