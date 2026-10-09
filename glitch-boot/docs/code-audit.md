# glitch-boot 代码正确性审计报告

审计角色：代码正确性审计（只读，未修改被审计文件）
审计日期：2026-10-08
结论一句话：**这一版（R2）的运行时逻辑本身没有崩溃路径，但它有一颗"静默哑弹"——`hash()` 的整数哈希写成了浮点运算，实测 `n ≥ 1300` 的输入 100% 返回精确的 `0`，导致 8 处依赖随机数的故障效果全部退化成常数；另有 1 条真实可复现的黑屏路径（`file://` 打开）和 1 条 rAF 回调链增殖缺陷。**

---

## 0. 版本、范围与方法

### 0.1 审计对象的版本（关键）

被审计的四个文件在本次审计过程中**被并发修改了 4 次以上**（模板与两份成品同时被重写）。为了让结论可复现，本次审计固定在下面这个快照上（以下简称 **R2**）：

```
$ cd /tmp/audit-snap && sha256sum *
163d96b6b375a05d9e7b73d9aec5a8e68bd5c533882e780ee71a95676ced4d91  build.py
255e32e911f1b9bf60e48dd294fea6124739d78b032c673bd71be78d0629bcf3  engine.template.html
6141ebf2bddc04e2a49b96b908d00a549ac93efef23d917d219e6e94daed6f02  index.html
788418b8043f09de7166d2b1a84445d544ea06f807e8e7ed6db1e2d31c17e972  index-rg.html
```

（R2 = 模板 816 行 / 成品 817 行、`G_START=158, G_LOOP=88, G_LEN=10`、`IMG` 为相对路径、`hash()` 为 `n<<13` 版本、`SZ=720` 固定。）

审计结束时磁盘上的最新版本（以下简称 **R3**，产物 369 KB、图片内联为 data URI、`SZ` 按视口计算、`hash()` 已改成 `Math.imul`）：

```
7733d5b2f4db3e404d2437d5d6691ef1797b90cedb30cd494040c96ad2ad8534  engine.template.html
ad12c691c5d3364511a039096c54be29dc45f7990cfa25f5b6bbea7c8c814bb5  build.py
82f914b9fae8ce2a05102f4163c6881defe2e91e96dfe5ba439e581a28080b60  index.html
0d53ed3f9d6bf57c3d4ce6efb8d49acc5760c4d1d6c8f631f57c7307ec834da6  index-rg.html
```

（R3 的文件快照在 `/tmp/r3root/`，与 19:14 的磁盘状态一致；下文所有 R3 行号均指这一版。R3 期间还短暂出现过 `7c4d8bbc…` 等中间版本，未纳入结论。）

**第 1～12 项问题针对 R2**；**第 14 节给出每一项在 R3 中的现状**（已修 / 仍存在），所有"已修"都是我用同一套工具在 R3 上重新实测过的，不是看代码猜的。

### 0.2 验证方法（全部可复现）

| 工具 | 作用 |
|---|---|
| `audit/probe.mjs` | 用 node + 软件 canvas 仿真完整跑引擎：加载期像素流水线、9 个变体、逐帧 `render()`、`reset()`、`?f=` 冻帧路径。含"干跑"模式与逐 op 绘制日志 |
| `audit/hash-degeneracy.mjs` | 直接 eval 产物里的 `hash()`，统计值域、零点、各调用点的实际取值 |
| `audit/browser-probe.mjs` | 真机 headless Chromium（CDP 驱动，无第三方依赖）：http 直播 34 s、8 种风格冻帧截图与像素哈希、`file://` 打开 |
| `node --check` | 语法校验 |
| 证据原文 | `audit/evidence/*.txt`（probe / browser / hash 三类的完整输出） |

复现命令：

```bash
cd /home/xuan/设计/glitch-boot/audit
node probe.mjs /tmp/audit-snap/index.html --sweep=700   # R2 全量
node hash-degeneracy.mjs /tmp/audit-snap                 # hash 退化
node browser-probe.mjs                                   # 真机（约 4 分钟）
```

---

## 1.【致命 · 已在 R3 修复】`hash()` 在浮点下溢出，运行时随机数全部退化为 0

### 位置

- `engine.template.html:168-171` / `index.html:168-171` / `index-rg.html:168-171`

```js
function hash(n){
  n = (n << 13) ^ n;
  return (((n * (n * n * 15731 + 789221) + 1376312589) & 0x7fffffff) / 0x7fffffff);
}
```

### 证据

`node hash-degeneracy.mjs /tmp/audit-snap` + `evidence/hash-zero-rate.txt`：

```
hash(0) = 0.6408954922300277      hash(1000) = 0        hash(1982) = 0
hash(1) = 0.6131865259321344       hash(2000) = 0        hash(7919) = 0
hash(10) = 0.03529596330378948     hash(5964) = 0        hash(82068) = 0
第一个恒零输入 n0 = 348
n∈[348, 2e5)  精确为 0 的比例 = 99.75% (199143/199652)
n∈[1300, 2e5) 精确为 0 的比例 = 100.00%
sf∈[0,5000) 的 hash(sf*977) 为 0 的比例 = 99.6%
```

浏览器内（真实 V8）复核一致：`{hash1982:0, hash3065:0, hash0:0.6408954922300277}`。

**机制**：`n = (n<<13)^n` 会把 n 放大到约 `8192n`；随后 `15731·n³` 的量级是 `~1e30`，远超 IEEE754 双精度的精确整数范围 `2^53≈9.0e15`，尾数只剩高位、低 32 位被舍入成 0，于是 `& 0x7fffffff` 必然得到 0。这是把 C 的 32 位整数溢出语义直接搬到 JS 浮点上的典型事故。

### 连锁影响（同一个根因，8 处效果被静默废掉）

| # | 调用点（R2 行号） | 设计意图 | 实测结果 |
|---|---|---|---|
| 1 | `TEAR_BANDS` 高度 `hash(i*907+3)` `template:404` | 条带高度 8~61 不等，"等分 = 滤镜，随机高度 = 故障" | 86 条里 84 条高度全是 8px，只有第 0 条 41px、末条 7px（`probe §1`、`hash-degeneracy §2`） |
| 2 | 切片撕裂参与率 `hash(i*131+sf*977)` `template:419` | 只有约 1/4 条带参与 | r 恒为 0 → **86/86 全部"参与"** |
| 3 | 切片撕裂位移 `hash(i*37+sf*613)` `template:421` | 位移在多帧内保持 | dx 恒为 0 → 撕裂完全不动；亮线 `floor(hash(sf*71)*86)=0` 被钉在 **y=0 画布最顶端** |
| 4 | 区块重排抽样 `hash(sf*991+i*137)` `template:443` | 25~40% 的块位移 | 该值恒 0，永不 `>0.62`；且目标格 `hash(sf*71+i*613)`、源偏移 `hash(sf*313+i*877)` 也恒 0 → **9 次 drawImage 全部落在同 1 格** |
| 5 | 噪点贴图 `hash(y*977+xx*31+n*7919)` `template:343` | 6 张静态噪点循环 | 777600 个采样点只有 209 个命中，且全部集中在 `y=0, xx≤11` → 6 张画布**实际只有左上角 13×2px 的斑点**（白占 12 MB） |
| 6 | 区块来源 `hash(ci*4099)` `template:498` | 每 3 个区块有 1 个用排序版 | 48 个区块里用 `V.sort` 的 = **0** |
| 7 | 入场位移/Rogue `hash(sd)/hash(sd+1)/hash(sd+2)` `template:484-485` | 每块抛入 | 除 ci=0..1 外全部是常数 `(-32,-7)` / `(+28)` |
| 8 | 周期抖动 `hash(cycle*7919+13)` `template:529` | 间隔 ±25% 抖动 | `cycle<20000` 的 jit 直方图 `19945,3,0,2,7,4,0,0,17,...` → **99.7% 的周期 jit=0**；实测故障窗起点 169,246,334,422,510,598,686 → 间隔 `77,88,88,88,88,88`，回到节拍器 |

真机复核（`evidence/browser-r2.txt`）最直观的一条：**风格①「切片撕裂」整轮 10 帧的画布像素哈希完全相同**（`f=169..178` 全部 `d97ae3a8`），而风格②每帧都不同（10/10）。node 侧逐 op 日志显示 88 次 `drawImage` 全是 `dx=0` 的自拷贝，唯一变化是 y=0 处那条 2px 亮线（1440 px = 0.28%）：

```
f= 169 风格0(切片撕裂) t=0.00 | drawImage 88 次 | 与干净底图不同的像素 = 1440 (0.28%)
f= 178 风格0(切片撕裂) t=1.00 | drawImage 88 次 | 与干净底图不同的像素 = 1440 (0.28%)
f= 334 风格2(竖向拉丝)  | drawImage 2 次  | 与干净底图不同的像素 = 0 (0.00%)   ← 完全不可见
f= 422 风格3(垂直滚动)  | drawImage 3 次  | 与干净底图不同的像素 = 0 (0.00%)   ← 首帧 dy=0
f= 686 风格6(区块重排)  | drawImage 10 次 | 与干净底图不同的像素 = 4608 (0.89%) ← 只剩左上角
```

### 修复（R3 已采用，建议保留并加自检）

```js
/* 32 位整数混洗，全程 Math.imul / 位运算，不让浮点吃掉低位 */
function hash(n){
  n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
  n = Math.imul(n ^ (n >>> 16), 0x45d9f3b);
  n = n ^ (n >>> 16);
  return (n >>> 0) / 4294967296;      // 恒 ∈ [0,1)，顺带根除 §9 的越界可能
}
```

建议在加载时加一段自检（失败只 `console.error`，不要影响播放）：

```js
(function hashSelfTest(){
  const s = new Set(); for (let i = 0; i < 2000; i++) s.add(hash(i * 977));
  if (s.size < 1900) console.error('hash 退化:', s.size, '/2000');
  for (const n of [1e4, 1e5, 1e6]) if (hash(n) === 0 && hash(n + 7) === 0) console.error('hash 大输入恒 0 @', n);
})();
```

> 注意：修好随机数后，所有"看起来还行"的观感都是在随机数恒 0 的前提下调出来的（例如 `dx` 上限只有 `0.26×2.4×amp ≈ 10px`）。R3 已经把 amp 从 16 提到 34、阈值 0.26 提到 0.42、并把"是否参与 / 方向 / 幅度"拆成三个独立随机量，这个方向是对的；上线前请再目视复核一遍 8 种风格的强度。

---

## 2.【高 · 已在 R3 修复】`file://` 直接打开 = 永久黑屏（真机复现）

### 位置

- `index.html:184-186`（`image.onload` → `bctx.getImageData`）、`index.html:813`（`image.src`）、`index.html:802-803`（`setTimeout(boot,40)` 重试）

### 证据（真实 Chromium，`evidence/browser-r2.txt`）

```
file:// 直接打开:
  画布不透明像素 = 0
  boot 重试次数 = 116（持续增长 = 永远等不到 imgReady）
  未捕获异常 = SecurityError: Failed to execute 'getImageData' on 'CanvasRenderingContext2D':
               The canvas has been tainted by cross-origin data.
               at image.onload (file:///tmp/audit-snap/index.html:186:19)
```

链路：`file://` 页面把本地图片画进 canvas 会污染画布 → `getImageData` 抛 `SecurityError` → 异常逃出 `onload`，`imgReady` 永远为 false → `boot()` 每 40 ms 重试一次、**无限循环** → 画布空白、文字/时间轴全不启动、控制台之外没有任何提示（`document.title` 仍是原标题，页面上看不到任何"出错"字样）。

### 修复

方案 A（R3 已采用，最彻底）：构建期把图片内联成 data URI，`file://` 下不再跨源。
代价：产物从 34 KB 涨到 376 KB（其中约 337 KB 是 base64 图片），且 `build.py` 现在依赖构建机上存在原图。

方案 B（无论是否内联都建议加上的兜底）：

```js
let retry = 0;
image.onerror = () => fail('图片加载失败: ' + IMG);
image.onload = () => {
  try { /* …原有像素流水线… */ }
  catch (e) { fail('画布像素读取被拒（请用 http 打开或内联图片）: ' + e.message); }
};
function fail(msg){
  imgReady = false; document.title = 'ERROR'; console.error(msg);
  const d = document.createElement('div');
  d.textContent = '⚠ ' + msg;
  /* 内联样式，避免依赖外部 CSS */ d.setAttribute('style',
    'position:fixed;left:12px;bottom:12px;z-index:99;color:#fff;font:12px monospace');
  document.body.appendChild(d);
}
function boot(){ if (!imgReady){ if (++retry > 75) return fail('超时'); setTimeout(boot, 40); return; } … }
```

---

## 3.【高 · R3 仍存在】点"重播"会让 rAF 回调链增殖，点几次就是几条链

### 位置

- `engine.template.html:747-758`（`loop` 末尾无条件 `requestAnimationFrame(loop)`）
- `engine.template.html:761-774`（`reset()` 里只 `running=false/true` + 再 `requestAnimationFrame(loop)`）

### 证据

node 侧（`evidence/probe-r2-index.txt` §4）：

```
reset() 后挂起 loop 回调数 = 1
跑 5 帧后 = 1
点 1 次重播后 = 2
点第 2 次后 = 3
再跑 20 帧: 每帧待执行 loop 回调 = 3
```

真机侧（`browser-probe.mjs` 包了 `window.requestAnimationFrame` 计数，`evidence/browser-r2.txt`）：

```
点 2 次 REPLAY 后 1.2s 内 loop 的 rAF 请求增量 = 218（单链 ≈ 72@60Hz；≈3 倍说明 3 条链）
```

原因：`loop()` 每次执行都会在末尾排队下一次回调；`reset()` 并没有取消这条排队中的回调，而是又排了一条。旧回调被唤醒时 `running` 已经是 `true`，于是两条链都活着，之后每点一次重播再加一条。`f !== lastf` 的守卫让多出来的链变成空转，所以只表现为 CPU 浪费（每条链都要走一遍 `render` 判定），不会立刻看坏画面。

### 修复

```js
let rafId = 0;                                    // 与 acc/prev/lastf 同级
function loop(ts){ … ; rafId = requestAnimationFrame(loop); }
function reset(){
  …
  cancelAnimationFrame(rafId);                    // ← 先掐掉排队中的旧链
  rafId = requestAnimationFrame(loop);
}
/* boot() 里同样写 rafId = requestAnimationFrame(loop); */
```

---

## 4.【中 · R3 仍存在】拼装期入场动画的两条分支不可达（48 个区块里只有 1 个能命中）

### 位置

- `engine.template.html:476`（`const at = 6 + REV_POS[ci] * 0.78;`）
- `engine.template.html:483-486`（`if (age < 3){ if (age === 0){…} else if (age === 1){…} }`）

### 证据（`evidence/probe-r2-index.txt` §2）

```
at=6+REV_POS*0.78 为整数的区块: [[28,6,0]] → 共 1 / 48
其余 47 个区块 age=f-at 恒为小数, age===0 / age===1 两条分支永不命中
前 8 个区块的 at: 0:41.88 1:41.1 2:42.66 3:30.18 4:39.54 5:38.76 6:40.32 7:32.52
```

`f` 永远是整数（来源是 `Math.floor(acc*FPS)`），而 `at = 6 + REV_POS[ci]*0.78` 对 47/48 个区块是小数，因此 `age = f - at` 永远不是整数，`age === 0` / `age === 1` 两条严格相等分支等价于死代码。设计中的"首帧半透明 + 抛出位移、次帧回弹"实际上只在 1 个区块上出现过。

### 修复

```js
const at = Math.round(6 + REV_POS[ci] * 0.78);     // 或 0.62，按视觉定；关键是整数化
```

（R3 把系数改成 0.62 并没有改变可达性——`0.62 = 31/50`，仍是只有 `REV_POS === 0` 那 1 个区块能整数化，实测 `1 / 48`。）

---

## 5.【中 · R3 仍存在】`blockShuffle` 收到的是周期号而不是帧号，3 个连续周期完全同款

### 位置

- 调用点 `engine.template.html:608`：`case 6: blockShuffle(idx, 9, 64 * env); break;`
- 函数体 `engine.template.html:440-441`：`function blockShuffle(f, n, amp){ const sf = Math.floor(f / 3); … }`

### 证据

`sliceTear` 传的是帧号 `f`，而 case 6 传的是 `idx`（= `ph.cycle`）。实测第一参数：

```
blockShuffle 收到的第一参数 = 6      ← 即 cycle 号，不是帧号
周期 0..11 只会产生 4 种随机图案(sf=0..3)，即每 3 个周期画面完全重复一次
同一轮爆发内 10 帧的图案都取自同一个 sf → 块面静止，只有幅度 64*env 在变
```

后果：style ⑦ 每 3 个周期（10.5 s）出现一次完全相同的块面布局；同一轮 0.4 s 爆发内块面是静止的（只有 `amp` 随 env 衰减），与函数注释里"带累积位移"的意图也不符。

### 修复

```js
case 6: blockShuffle(f, 9, 64 * env); break;      // 与其它 case 保持一致，传帧号
```

（若确实想要"每轮保持同一个位移场"，也应显式写成 `blockShuffle(idx * 1000 + f, …)` 之类，让"轮内保持、轮间变化"成为可读的意图，而不是靠传错参数偶然得到。）

---

## 6.【中 · R3 仍存在】长卡顿会整段吞掉故障窗口

### 位置

- `engine.template.html:752`：`if (dt > 0.25) dt = 0.25;` → `acc += dt; const f = Math.floor(acc*FPS);`

### 证据（`evidence/probe-r2-index.txt` §5）

```
卡顿前后 render 收到的 f 序列: 78,79,80,81,82,83,84,90
→ 一次卡顿跳过 6 个帧号
```

`dt` 上限 0.25 s 在 25 FPS 下等于**一次最多跳 6 个帧号**。稳态故障窗只有 10 帧（0.4 s），且强度包络是二次衰减：

| 窗内序号 d | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| `env=(1-t)²` | 1.000 | 0.790 | 0.605 | 0.444 | 0.309 | 0.198 | 0.111 | 0.049 | 0.012 | 0 |

如果卡顿恰好落在窗口开头，下一次渲染直接从 `d=6` 开始，用户看到的是 `env ≤ 0.111` 的残影（`case 4/5` 的 `env > .35` 门槛也过不去），**等于这一轮故障没有发生**。低帧率设备（8~10 FPS）会更频繁地采样到这个衰减尾巴。

### 修复

```js
if (dt > 0.25){
  /* 不追时间，但也别跳帧号：把时间轴锚到"最后一帧的下一帧" */
  acc = (lastf + 1) / FPS;
  prev = ts;
} else {
  acc += dt;
}
```

代价是卡顿期间动画会慢于墙钟——对一段十几秒的开场来说这是可接受的取舍。

---

## 7.【中 · R3 仍存在】把资产换成"真·透明底"PNG，整幅背景会变成实心墨块

### 位置

- `engine.template.html:191-192`（`white[]` 只按 RGB 均值判定）
- `engine.template.html:220`（`if (outside[p]){ d[i+3]=0; continue; }`）
- `engine.template.html:225-227`（未标记为白 → `v = 0.13+0.87*detail`，`lum=0` 时 `v=1` → alpha 255）

### 证据

当前资产（`温曦头像-SVG/温曦-侧颜头像-透明底.png`）实测 **alpha 通道只有 255 一个取值**（1254×1254 全不透明），所以现在能跑。把同一张图导出成真正的透明底再用引擎跑（软件仿真，`probe §10`）：

```
真透明底资产 → 底图不透明像素 518400 (100.0%) 透明 0
```

原因是透明像素经 `drawImage` 后是 `(0,0,0,0)`：RGB 均值 0 → `white[p]=0` → 不会被四边泛洪标成外部背景 → 落进成像分支，`lum=0 → detail=1 → v=0.13+0.87=1` → **alpha 255、涂满墨色**。文件名写着"透明底"，实现却要求"不透明白底"，这是个随时会被下一次导出踩中的陷阱。

### 修复

```js
/* 透明像素等同于白：让泛洪能从四边把真·透明区也标成 outside */
white[p] = (d[i+3] === 0 || (d[i] + d[i+1] + d[i+2]) / 3 >= 248.5) ? 1 : 0;
```

另外建议把资产改名（如 `…-白底.png`）或在 `build.py` 里加一条断言：读图后检查是否 100% 不透明，否则 `sys.exit` 并提示改用透明底兼容逻辑。

---

## 8.【低 · R3 仍存在】`?f=abc` 会把 `NaN` 写进样式

### 位置

- `engine.template.html:779-780`：`parseInt/parseFloat` 后只判 `!== null`
- `engine.template.html:801-806`：冻帧分支直接 `render(f)`

### 证据（`probe §8`）

```
render(NaN) → 无异常 | pwrap.transform = "translateX(NaN%) scale(NaN)" | divider.height = "NaNpx"
```

不抛异常，但会往 `style` 里写非法值（浏览器静默忽略），且 `w-wensi` 的文字走 `scramble(fin, NaN)` 后会把整串字符显示成乱码，画面停在半成品状态。

### 修复

```js
const qf0 = q.has('f') ? Number(q.get('f')) : null;
const qt0 = q.has('t') ? Number(q.get('t')) : null;
const qf = Number.isFinite(qf0) ? qf0 : null;
const qt = Number.isFinite(qt0) ? qt0 : null;
```

---

## 9.【低 · 已被 R3 的 hash 实现顺带根除】用 `hash()*长度` 取下标存在理论越界；一旦触发会永久冻结动画

### 位置

- `engine.template.html:430`：`TEAR_BANDS[Math.floor(hash(sf * 71) * TEAR_BANDS.length)]` → 取到 `undefined` 后立即读 `b.y`
- `engine.template.html:632`（`scramble` 内）：`GLYPH[Math.floor(hash(...) * GLYPH.length)]`

### 证据（`probe §1` / §8）

```
TEAR_BANDS[floor(hash(sf*71)*N)] : 检查 200000 个真实种子 → 命中 1.0 的次数 = 0
GLYPH[floor(hash(i*631+q*977)*43)] : 检查 492 个真实种子 → 命中 1.0 的次数 = 0
n<2e6 内 hash(n)===1 的个数 = 0
```

即：要越界必须 `hash()` 精确返回 `1.0`。R2 的实现里理论可达（`&0x7fffffff)/0x7fffffff` 的右端点是闭区间），实测 200 万个输入里一次都没出现，所以是**低概率但后果严重**的一类：

- 若发生在 `sliceTear`：`TypeError` 逃出 `loop()` 的 `render()` 调用，**`loop()` 尾部的 `requestAnimationFrame(loop)` 不会执行 → 整条动画链死亡**（重播按钮此时若还没出现，页面等于卡死）。
- 若发生在 `scramble`：文字里会混进字符串 `"undefined"`。

### 修复

R3 的 `return (n >>> 0) / 4294967296;` 天然落在 `[0,1)`，已根除。若保留旧实现，请写成：

```js
const idxOf = (h, len) => Math.min(len - 1, Math.floor(h * len));
```

---

## 10.【低 · 当前资产实测无影响】色度判别先于背景判定

### 位置

- `engine.template.html:216`（`if (r - (g+b)*0.5 > 25){ {{CLIP_RGB}} …continue; }`）
- `engine.template.html:220`（`if (outside[p]){ d[i+3]=0; …}`）

### 证据

判别式在背景判定**之前**执行，所以"背景里的任何暖色像素"都会被写成实心不透明块（且 alpha=255），而正常背景应当是透明的。用与引擎完全相同的算法在真实 PNG 上复算（PIL + 同一泛洪逻辑）：

```
命中色度判别的暖色像素 = 2290
  其中落在外部背景区(会被画成不透明实心块) = 0
  落在人物区内 = 2290
```

结论：当前资产安全（2290 个暖色像素全在人物内）。但这是资产属性，不是代码保证——换一张带暖色背景的图就会在画面上出现实心色块。

### 修复（两行顺序对调即可）

```js
if (outside[p]){ d[i+3] = 0; continue; }               // 先判背景
if (r - (g + b) * 0.5 > 25){ {{CLIP_RGB}} continue; }  // 再判发夹
```

---

## 11.【低 · R3 仍存在】内存与"空白噪点"：R2 常驻约 29.7 MB（含源图约 36 MB），其中约 12 MB 是空的

### 证据（`probe §14`，R2 / 720×720）

```
一次装载创建的 canvas = 17 个, 合计像素缓冲 = 8.0 MB   ← 探针计数器只在“创建时”累加
V 上常驻画布 = step,inv,scan,sort,sortV,cA,cB,ghost + noise[6] → 共 14 个 / 720×720
```

探针的 `alloc.canvasBytes` 在 `canvas.width/height` 被赋值（重新分配像素缓冲）时没有累加，所以 8.0 MB 是**低估**。按 720×720×4 B = 1.98 MB/张 计算，**base + 8 个变体 + 6 张噪点 = 15 张 ≈ 29.7 MB 常驻**（这 17 个 canvas 里另外 2 个是主画布 `#glitch` 与源图载体）；浏览器里还要再加上解码后的源图 1254²×4 ≈ 6.3 MB，加载期还会同时存在 2~3 份 ImageData（每份 2.0 MB）。这些 canvas 都挂在模块级 `V` 上、永不释放，属于"一次性预渲染换每帧恒定开销"的有意设计，桌面端没问题，移动端（尤其 R3 把 SZ 上限提到 900 后 ≈ 15×3.24 MB = 48 MB）需要留意。

其中 6 张噪点画布因 §1 的 hash 退化**只有左上角 13×2 px 的斑点**，等于白占 11.9 MB——修好 hash 之后这 6 张才真正有用，届时内存开销才算合理，不必删。

顺带：Chromium 会对这些画布报 `Canvas2D: Multiple readback operations using getImageData are faster with the willReadFrequently attribute set to true`（`evidence/browser-r2.txt`）。只在加载期读一次，忽略即可；若想消掉警告，给这些离屏画布用 `getContext('2d', { willReadFrequently: true })`。

---

## 12.【信息】两处小问题

1. **冻帧页的 REPLAY 按钮是可点的**：`?f=200` 页面上按钮 opacity=1，点一下 `reset()` 会把冻帧页变成直播页（实测点击后有 1 条 loop 回调被挂起，"f=200" 的标题不再可信）。用于逐帧校验时建议加 `?f=` 模式下 `replay.disabled = true` 或隐藏按钮。
2. **注释与实现不一致**：`AUTO_AT/DUR` 实测最后一字落在 `f=134-138`，注释写 `f98→132`；`glitchPhase` 注释写"间隔 3s、±25% 抖动"，实测 R2 的抖动恒为 0（见 §1）。注释是最好的规格书，建议同步。

---

## 13. 已验证正确的部分（逐条回答审计要求）

> 全部基于 R2 + 真机 Chromium；证据见 `audit/evidence/`。

### 13.1 严格模式 / 未声明变量 / TDZ / 隐式全局 —— 未发现问题

- 两份成品的内联脚本 `node --check` 均通过；模板本身因为语句位置上有 `{{STEP_R}}` 之类的占位符**不能**直接通过语法检查（预期行为，构建后才合法）。
- 全脚本以 `"use strict"` 开头，实测跑通了 `image.onload`（像素流水线 + 9 个变体 + 2 次像素排序）、`render()` 连续 700 帧、`reset()`、`?f=` 冻帧、8 种故障风格——**任何隐式全局赋值都会在严格模式下抛错，全程 0 异常**（`probe §11`），故不存在未声明变量/隐式全局。
- 顶层函数声明会被 `hook` 覆盖、`const/let` 不受影响，说明代码是普通的脚本作用域，没有模块化残留；`mk()`、`base` 等 `const` 的初始化顺序也正确（`buildVariants` 由 `onload` 异步触发，不存在 TDZ 竞态）。

### 13.2 时间轴推进、帧号越界、`reset()` 复原 —— 逻辑正确

- `f = Math.floor(acc*FPS)` 单调不减，实测 0→700 连续无跳号、无回退、无越界访问（数组下标全部由长度取模/边界夹取）。
- 故障窗口与 `render()` 的"是否重绘"判据**逐帧一致**：`glitchPhase(f) !== null` 同时驱动 `tearing` 与 `runGlitch`，实测"glitchPhase 非空但未绘制"= 0 帧、"非空但未重绘"= 0 帧；每轮窗口后**恰好有 1 帧清理重绘**（`template:683` 的 `wasTear`），无孤儿清理帧。
  （R2 窗口表：`169-178, 246-255, 334-343, 422-431, 510-519, 598-607, 686-695`，长度恒为 10。）
- `reset()`（`template:761-774`）复原了全部**可见**状态：`pwrap` transform、divider 高度、bootBar/bootBand/sync/hud/status/replay 的 opacity、四个角标与四个括号、15 个字母的文本/clipPath/transform/textShadow、以及 `ctx.clearRect` 清空画布；`acc/prev/lastf/drawn/wasTear` 全部归零。
  残留的只有 3 个**不可见**样式值（`bootBar.transform`、`bootBand.height/transform`、`sync.transform`）：它们只在 `f<14`/`f∈[46,58]` 被写，且当时 opacity 已为 0，下一轮首帧就会覆盖，无实际影响。
  ⚠️ 唯一缺陷是 §3 的 rAF 链增殖。

### 13.3 撕裂帧残留 —— 已正确处理（真机验证）

- 浏览器实测：`?f=179`（窗口后一帧）画布哈希 `20a7b7a8` **等于** `?f=157`（干净帧）`20a7b7a8`；`?f=178`（窗口末帧）哈希 `d97ae3a8` **不等于** 179。即"撕裂-清理"闭环成立，没有残留。
- node 侧用同一像素级判据对比"直播模式走到第 N 帧"与"`?f=N` 冻帧"：6/6 采样帧（窗口首帧、末帧、清理帧、下一窗口首帧）像素校验和完全一致 → 冻帧截图可以作为直播状态的可靠证据。
- 直播抽样（320 次 rAF，覆盖锁定爆发 f=44→58）显示：故障帧之后画布立刻回到干净底图哈希并长期保持。

### 13.4 占位符替换与两份成品的差异 —— 完整且只有调色差异

```
BW/RG 各自: 调色板键 15 个 | 模板占位符 15 个
  调色板有但模板没有(静默失效): 无
  模板有但调色板没有(build 会 sys.exit): 无
  每个占位符在模板中出现次数: 全部 = 1
  用同值标记替换全部占位符后，两份模板渲染结果逐字节相同 = True
  磁盘产物 == 模板重新渲染 = True（两份）
  成品中残留占位符 = 无
```

即：两份成品是同一份模板的两个调色实例化，差异 100% 来自调色板（24 行 diff：TITLE/MODE/`--line`/`--accent`/`CLIP_RGB`/`INK_RGB`/`STEP_*`/`INV_RGB`/`GHOST_SPLIT`/`NOISE_RGB`/`SYNC_INK`）。
建议：`build.py` 目前只校验"没有残留占位符"，不校验生成的 JS 是否可解析。加一步成本极低：

```python
# verify_render(text): 抽出 <script> 写临时文件 → node --check
```

### 13.5 `sortInto` 区间排序 —— 不会越界、不会死循环、不变量成立

（`probe §6`；用**源码本身**（`Function.prototype.toString` 取出后替换 I/O 注入掩码）在 6 组退化掩码 × 行/列两种方向下跑，并用 Proxy 统计越界读。）

```
掩码[全不透明]    : 越界读 = 0 | 行/列各耗时 …
掩码[全透明]      : 越界读 = 0
掩码[交替单点]    : 越界读 = 0
掩码[长度 1/2 碎段]: 越界读 = 0
掩码[随机 50%]    : 越界读 = 0
合计越界读 = 0
真实底图(V.sort/V.sortV): 参与排序的连续段 631/533，多重集被破坏的段 = 0，透明洞位置变化 = 0，降序违例 = 0
```

- 终止性有保证：空白跳过循环与墨区提取循环都会让 `k` 严格递增；`len < 3` 分支里 `k` 已经越过该段，`continue` 不会原地打转（`len===0` 只可能发生在 `k===SZ`，外层条件随即为假）。
- 下标上界 `at(SZ-1, SZ-1) = (NP-1)*4`，不越界。
- 每段的多重集（颜色 + alpha）守恒、透明/不透明位置不变、按排序键降序成立——行/列两个方向都通过。

### 13.6 异常路径扫描 —— 除 §2/§9 外没有别的抛错点

- node：`image.onload` + 700 帧 `render` + `reset` + 越界输入（`NaN/-5/1e9/Infinity`）= 0 异常。
- 真机：http 直播 34 s（f≈850，覆盖全部 8 种风格）= 0 异常；`fps=60`、`drops=1`（那一次是加载期同步阻塞造成的 317 ms 抖动）。
- 唯一真实抛错点是 `file://`（§2）；理论上还可能来自 §9。

### 13.7 加载期性能（真机）

```
首帧(画布出现非透明像素)耗时 ≈ 937 ms (R2) / 668 ms (R3)
__stats(约 1s 后) = {"frames":6,"drops":1,"fps":13.8,"worst":317}
```

加载期像素流水线是同步的，会阻塞主线程约 0.3~0.6 s（`worst=317 ms` 即那次阻塞），加上图片解码总计约 0.7~0.9 s 才出现第一帧。这段黑屏期间页面没有任何进度提示。若要改善，可把 `buildVariants()` 拆成几段用 `requestIdleCallback`/`setTimeout(…,0)` 让出主线程，或先渲染底图再后台生成变体（用"该变体就绪前先退化用 base"的方式）。

---

## 14. 最新版（R3）现状对照

用与 R2 完全相同的工具在 R3 上重跑（`evidence/probe-r3-newest.txt`、`evidence/browser-r3.txt`）：

| # | R2 问题 | R3 现状 | 复核证据 |
|---|---|---|---|
| 1 | `hash()` 浮点溢出 → 随机数全 0 | **已修** | `hash(n)` 全值域无零点；`n∈[0,2e4]` 不同取值 20001/20001；jit 直方图 `1232,1275,1276,1252,1271,1195,1218,1213,1191,1284,1239,1271,1235,1263,1285,1300`（≈均匀）；窗口起间隔 `86,98,83,88,91` 恢复抖动 |
| 1-1 | `TEAR_BANDS` 84/86 退化 8px | **已修** | R3（SZ=640）：20 条，高度 10~58 分布正常；R2（SZ=720）为 86 条、84 条恒为 8px |
| 1-2 | 风格①整轮静止（10 帧同图） | **已修** | 真机：窗口内 8 帧哈希两两不同；node：与干净底图差异 23.45%→20.4%→19.4%→…逐帧衰减 |
| 1-3 | 风格③④⑥ 首帧不可见 | **已修** | node 差异：风格③ 22.52%、风格④ 24.04%、风格⑥ 10.54%（R2 分别 0%、0%、0.89%） |
| 1-4 | `V.sort/V.sortV` 排序键是 RGB 和（单色图 → 空操作） | **已修** | 排序键改为 alpha；实测 alpha 非增违例 = 0 |
| 1-5 | 噪点贴图几乎空白 | **已修** | 噪点种子恢复正常取值（hash 修复的直接结果） |
| 2 | `file://` 打开永久黑屏 | **已修** | 真机 `file://` 直开：不透明像素 162587、0 异常 |
| 3 | 重播点击 → rAF 链增殖 | **仍存在** | 连点 2 次后挂起 loop 回调 = 3（R3 未加 `cancelAnimationFrame`） |
| 4 | `age === 0 / 1` 死分支（47/48 区块） | **仍存在** | `at=6+REV_POS*0.62` → 仍只有 1/48 整数化 |
| 5 | `blockShuffle(idx, …)` 传错参数 | **仍存在** | 仍为 `case 6: blockShuffle(idx, 9, 64*env)`；第一参数 = 周期号 |
| 6 | 卡顿跳帧吞掉故障窗 | **仍存在** | 仍为 `if (dt > 0.25) dt = 0.25`，实测一次跳过 6 个帧号 |
| 7 | 真·透明底资产 → 背景实心 | **仍存在**（风险） | `white[]` 仍只按 RGB 判定；已改为内联 data URI，触发条件变成"构建期换图" |
| 8 | `?f=abc` 写入 NaN 样式 | **仍存在** | 仍直接 `parseInt/parseFloat`，无 `Number.isFinite` 校验 |
| 9 | `hash()*len` 下标理论越界 | **已根除** | 新实现返回 `[0,1)`，结构上不可能等于 1 |
| 10 | 色度判别先于背景判定 | **仍存在**（当前资产无影响） | 两分支顺序未变 |
| 11 | 6 张空白噪点画布白占内存 | **已修**（随机数修好后噪点才真正生效） | — |
| 12 | 冻帧页 REPLAY 可点 / 注释与实现不一致 | **部分**：AUTOMATION 注释改成 `f98→134`（实际末字扫完在 f=138，仍有 4 帧差）；冻帧页仍可点重播 | R3 `engine.template.html:786` |

### R3 引入的新观察（不是回归，但值得注意）

1. **`SZ` 改为按视口/DPR 计算**（`engine.template.html:169-176`，`index.html` 同）：产出的像素级结果从此**依机器而异**（本机 headless 1280×720 → SZ=640），"确定性故障/同一帧同一结果"的保证只在同一设备同一窗口尺寸内成立。若之后要做逐帧截图回归比对（本报告的冻帧哈希法就依赖这一点），需要固定 SZ（例如把 SZ 也做成 `?sz=` 参数，默认按视口）。
2. **`canvas.width = canvas.height = SZ`（`engine.template.html:427`、`index.html:428`）与 HTML 里写死的 `width="720" height="720"` 不一致**：JS 会覆盖，所以能跑；但如果 JS 在到达该行前抛错，页面会按 720 的 canvas 属性渲染（比例仍对，只是分辨率不是预期的）——属可接受的降级。
3. **`const autoBar = document.querySelector('.auto-bar')`（`engine.template.html:710`、`index.html:711`）没有空值兜底**：`set()` 用的是 `WeakMap`，一旦 `.auto-bar` 不存在/类名被改，`cache.set(null, {})` 会抛 `TypeError: Invalid value used as weak map key`；这个抛错发生在 `render()` 里 → `loop()` 尾部排队下一帧的语句不会执行 → **整条动画永久冻结**。建议：

```js
const autoBar = document.querySelector('.auto-bar');
…
if (autoBar) set(autoBar, 'opacity', …);
/* 或让 set() 自保： function set(el, prop, val){ if (!el) return; … } */
```
4. **产物体积**：内联 data URI 后 `index.html` 从 34 KB → 376 KB（`index-rg.html` 同量级），两份共 753 KB；换来的是 `file://` 可直接打开。这是有意识的取舍，只需知道 `build.py` 从此依赖构建机上存在原图（若原图缺失会 `FileNotFoundError` 直接中断构建——比静默产出坏文件好，但建议给个友好报错）。
5. `IMAGE_DATA_URI` 由 `render()` 单独替换、不进调色板 dict（因此"调色板键 ↔ 模板占位符"的一次性校验会显示 1 个差集）。替换残留仍会被 `leftover` 检查兜住，属可接受；若想严格，把 `IMAGE_DATA_URI` 也放进两个 palette dict（值相同）即可。

---

## 15. 修复优先级清单（按"性价比 / 风险"排序）

| 优先级 | 动作 | 位置 | 备注 |
|---|---|---|---|
| P0 | `hash()` 改为 32 位整数实现 + 加载自检 | `template:168-171` | R3 已做，补上自检；改完必须重新目视校一次 8 种风格强度 |
| P0 | `reset()` 里 `cancelAnimationFrame(rafId)` | `template:747-774` | 3 行改动，根除 rAF 链增殖 |
| P1 | `image.onload` 加 try/catch、补 `image.onerror`、重试设上限 | `template:184-186, 802-803` | 内联 data URI 已解决主因，兜底仍需 |
| P1 | `at` 整数化 | `template:476` | 一行；让 47 个区块的入场动画真正生效 |
| P1 | `blockShuffle(f, …)` | `template:608` | 一行；消除"3 周期同款"与"轮内静止" |
| P1 | 卡顿不再跳帧号（`acc = (lastf+1)/FPS`） | `template:752` | 3 行；低帧率设备上才看得出差别 |
| P2 | `white[]` 把 `alpha===0` 当白 | `template:191-192` | 5 行；避免下一次换图整片变黑/白 |
| P2 | 色度判别挪到背景判定之后 | `template:216-220` | 2 行顺序调整 |
| P2 | `?f/?t` 加 `Number.isFinite` 校验 | `template:779-780` | 3 行 |
| P3 | `set(el, …)` 增加 `if (!el) return;` | `template:650-653` | 防止 DOM 变动导致整条链死亡 |
| P3 | 构建后 `node --check` 一次生成的内联脚本 | `build.py` | 让占位符替换错误在构建期暴露 |
| P3 | 冻帧模式隐藏/禁用 REPLAY；注释与实现对齐 | `template:801-806, 622-624` | 校验体验 |

---

## 附：证据文件清单

| 文件 | 内容 |
|---|---|
| `evidence/probe-r2-index.txt` | R2（黑白版）全量仿真：§0 装载 / §1 hash / §2 死分支 / §3 窗口一致性 / §4 rAF 链 / §5 跳帧 / §6 sortInto / §7 reset / §8 异常 / §9 冻帧一致 / §12 风格与节奏表 / §13 hash 精度 / §14 内存 / §15 reset 残留 / §16 逐风格绘制指令与像素差 |
| `evidence/probe-r2-index-rg.txt` | 同上，红绿版（验证两份产物的运行时行为一致） |
| `evidence/hash-degeneracy-r2.txt` | R2 `hash()` 退化逐项实测（零点、条带表、各调用点取值） |
| `evidence/hash-zero-rate.txt` | R2 `hash()` 零值占比（99.75% / 100%） |
| `evidence/browser-r2.txt` | R2 真机：http 直播 34 s、8 风格冻帧哈希、`file://` 失败链路 |
| `evidence/probe-r3-newest.txt` | R3 同一套探针的复核结果（含"仍存在"项） |
| `evidence/browser-r3.txt` | R3 真机：首帧 668 ms、直播 25 s 0 异常、`file://` 成功 |
