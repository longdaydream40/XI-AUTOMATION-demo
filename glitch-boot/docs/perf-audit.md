> **历史文档。** 本报告审计的是改名与重构之前的版本（当时屏幕上写 `WENSI` / `AURORA`，
> 头像施工在浏览器里做）。当前实现见 `XI-开场动画/README.md` 与 `glitch-boot/README.md`，
> 结论不要直接套用到新版本。

# 前端性能审计 · WENSI AUTOMATION 开场

## 0. 审计对象的版本锁定

`/home/xuan/设计/index.html` 在我审计期间被**另一个并发会话反复重写**（实测 md5 从
`67464fc3…`@18:54 → `0e501b41…`@19:14），所以我先钉了一份快照，本报告所有行号与数字
都指向这一份：

| 项目 | 值 |
|---|---|
| 快照源码模板 | `audit/perf/snapshot/engine.template.html` · md5 `b38fa884b45cb69193a0f3f059ec2b99` · 884 行 |
| 快照成品 | `audit/perf/snapshot/index.html` · md5 `0e501b41816fe9fbc290833795b2d273` |
| 取样时间 | 2026-10-08T19:22:52Z |
| 测试环境实际 `SZ` | **774**（由 169–174 行按视口推导，非固定值） |

行号一律指**快照模板**。成品 `index.html` 因 `{{GHOST_SPLIT}}` 等占位符展开为多行，
自 ~330 行起有 +1 偏移。

## 1. 测量方法

不用 rAF、不依赖合成器，因此数字不受这台机器负载影响：

1. 在页面脚本之前注入探针，劫持 `CanvasRenderingContext2D.prototype` 的
   `getImageData/putImageData/createImageData/drawImage/clearRect`、
   `HTMLCanvasElement.prototype.getContext`、`HTMLElement.prototype` 的
   `offsetWidth/offsetHeight/…`、`Element.prototype.getBoundingClientRect`，
   并给每张画布打 tag（`#glitch` / `off#0…off#14`）。
2. 以 `?f=0`（冻帧模式，不启动主循环）加载快照。
3. **手动驱动 1029 次 `render()`**（300 帧连续 + 27 个代表帧各 27 次），逐项计数。

复现：`perf/snapshot/` 起 `python3 -m http.server 9801`，然后
`python3 audit/perf/final_probe.py --angle swiftshader --port 9813`，
结果落在 `audit/perf/final_probe.json`。

## 2. 结论速览

| # | 问题 | 判定 | 依据 |
|---|---|---|---|
| 1 | 每帧 `getImageData/putImageData` | **无** | 驱动 1029 帧期间计数 = 0 / 0 / 0 |
| 2 | 每帧读 `offsetWidth/offsetHeight` | **无** | 全会话共 2 次，都在 `frame=-1` |
| 3 | 主渲染画布被像素回读 | **无** | `#glitch` 零回读；但触发 Chromium 告警 |
| 4 | 每帧新建对象/数组 → GC 压力 | **有分配，无压力** | 420 B/帧，强制 GC 后回落到基线 |
| 5 | 离屏 canvas 复用 | **合理** | 15 张，全部载入期一次性创建 |
| — | **真实问题：载入期 413ms 同步阻塞** | **有** | 见 §4 |

---

## 3. 逐条

### 3.1 每帧 `getImageData/putImageData` —— 没有

驱动 1029 帧期间的实测计数：

```
getImageData: 0    putImageData: 0    createImageData: 0
```

全部 31 次像素回读/写入集中在 t=326ms → 739ms，探针记录到的 `frame` 全是 **-1**
（即第 0 帧之前）。代码位置：205、257、265、284、312、321、343–344、352–353、
362、365、372、387、396、422 —— 全部位于 `image.onload`（203）、`buildVariants`（274）、
`sortInto`（393）之内，这三个都只跑一次。

这段设计意图（155–157 行注释：「所有逐像素运算在加载时一次性预渲染成离屏 canvas；
运行时只做 drawImage 合成」）是被真正兑现的。**这是全文件做得最对的一件事**，也是
每帧开销能压到几十微秒的根本原因。

### 3.2 每帧读 `offsetWidth/offsetHeight` —— 没有

全会话只有 **2 次**布局读取，都是 `#stage` 的 `offsetWidth` + `offsetHeight`，
发生在 t=750ms、`frame=-1`。驱动帧期间 0 次。

代码层面的保证：

- `measure()`（722）：`VW = stage.offsetWidth; VH = stage.offsetHeight;`
- 调用点只有两处：`boot()`（869）与 `resize` 监听（723）。
- `render()` 里的读取被 `if (!VW) measure();`（729）挡着；`VW` 一旦非 0 就永不重入。

时间线上 750ms **晚于** 739ms（载入窗口结束），说明 `render(0)` 从来没有在 `VW === 0`
的状态下跑过 —— 否则 1029 帧会留下上千次读取。`resize` 处理器读布局但不写任何 DOM，
不构成强制同步布局的读写交错。

### 3.3 主渲染画布被像素回读 —— 没有，但触发 Chromium 降级启发式

`#glitch`（426）在整个会话里只有 1 次 `getContext('2d')`（428），
**零次** `getImageData/putImageData`。所有像素操作都打在离屏 `off#0`…`off#14` 上，
渲染目标始终留在 GPU 路径。

但 Chromium 确实报了警，且栈直接指向源码：

```
Canvas2D: Multiple readback operations using getImageData are faster with the
willReadFrequently attribute set to true.
  cp.getImageData → coverOf (engine.template.html:265)
                  → buildVariants (274) → image.onload (203)
```

原因：`base` 这一张画布被回读了两次（205 与 265），触发启发式。Chromium 可能据此把它
降级到软件后备存储。

**但当前没有可测的代价**。A/B 对照（同一目标画布、500 次 `drawImage` × 5 轮取中位数，
单位 µs/次）：

| 源画布回读次数 | 0 | 1 | 2 | 3 | 5 |
|---|---|---|---|---|---|
| 中位数 µs/次 | 2.0 | 2.2 | 2.2 | 2.2 | 2.0 |

差异在噪声内。所以这是**真实存在的隐患（依赖未文档化的浏览器启发式、跨版本/后端会变），
但不是当前的性能问题**。

修复方向要小心，别修反了：

- ❌ 给 `base` / `V.*` 自己加 `{willReadFrequently: true}` —— 那是把它们钉死成软件后备，
  之后每帧从它们 `drawImage` 都要把整张 SZ² 位图（774² × 4 = 2.4 MB）上传到 GPU，
  60fps 下 2~5 张/帧就是 300~700 MB/s 的 PCIe 流量。
- ✅ 用一张**专用涂鸦画布**承载读-改-写，成品再一次性 `drawImage` 进一张全新、
  永不回读的画布：

```js
const scratch = document.createElement('canvas');
scratch.width = scratch.height = SZ;
const sctx = scratch.getContext('2d', { willReadFrequently: true });
const promote = src => {                    // 成品落到干净的 GPU 常驻画布
  const c = document.createElement('canvas'); c.width = c.height = SZ;
  c.getContext('2d').drawImage(src, 0, 0);
  return c;
};
```

### 3.4 每帧新建对象/数组 —— 有分配，但实测无 GC 压力

每帧确实在分配：

- `glitchPhase`（583）每帧 new 一个 `{ cycle, t }`（590）。实测 1029 次 render 里调用
  933 次 ≈ 0.91/帧 —— 因为 746 行的 `const tearing = … || glitchPhase(f) !== null`
  会短路，只有撕裂帧才由 `runGlitch`（601）再调一次。
- `set()`（715）每帧被调用 **约 52 次**（实测 53,823 / 1029）。其中
  `clipPath`（777、793）、`textShadow`（781、795）、`transform`（752、761、778）
  每次都要先构造模板字符串，哪怕值与缓存相同、最终并没有写 DOM。

实测代价：

- 1029 次 render 期间堆增长 +432,665 B ≈ **420 B/帧**；
- 强制 GC 后存活集回落基线（另一轮实测：247 帧净增长 **−664 B**）；
- 60fps 下 ≈ 25 KB/s 的 nursery 垃圾，相当于**一帧一张 SZ² ImageData（2.4 MB）的 0.02%**。

结论：不是 GC 问题，不需要为它改架构。若要顺手清掉，有一处既省分配又省真实工作量：

**`render()` 的逐字循环在用完以后还在空转。** 771（WENSI）与 787（AUTOMATION）两个
`forEach` 在字全部落位后，`p` 恒定、`g` 衰减到 0、`txt` 恒定，每帧算出来的值与上一帧
逐字相同。最晚的 `AUTO_AT + AUTO_DUR = 138`，辉光在 `b + 22 = 160` 帧归零。
把整块包进 `if (f <= 160)`，稳态每帧少 15 次 `set()` 调用与 15 次字符串构造。
`glitchPhase` 同理：把 `{ cycle, t }` 提成模块级单例对象，改为写字段而不是返回字面量。

### 3.5 离屏 canvas 复用 —— 合理

- **15 张**，全部在载入窗口内一次性创建（t=260.3 … 735.1ms），驱动帧期间**零创建**。
- 全部是模块级单例：`base`（197）、`V.step`（281）、`V.inv`、`V.scan`（317）、
  `V.sort`/`V.sortV`（335–336）、`V.cA`/`V.cB`（339）、`V.ghost`（358）、
  `V.noise[0..5]`（368–389）。
- `sortInto(target, vertical)`（393）和 `coverOf(canvas)`（264）都把画布当参数传入、
  就地写入，不会每次调用新建画布。
- 峰值后备存储：15 张 × 774² 像素 × 4 B/像素 = 35,944,560 B ≈ **35.9 MB**（34.3 MiB）。

两个小注记（都不构成问题）：

1. `coverOf`（265）对 `base` 二次 `getContext('2d')` —— 返回同一个 context 对象，无害。
2. `V.ghost` 只在 `f < 44` 分支用到（535），1.76s 之后就是死重量，占 2.4 MB。
   不值得为它加释放逻辑，但**别再加变体了**：15→16 张后备存储就逼近 38.3 MB，
   而每张都要付一次 GPU 回读。

---

## 4. 唯一的真实问题：载入期 413ms 同步阻塞

### 4.1 实测时间线（SZ=774）

```
326 ms  getImageData  off#0  ← 205
425 ms  putImageData  off#0  ← 257	 99ms：白掩码(211) + 四边泛洪(215–227) + 基调映射(223–256)
441 ms  V.step(281) + V.inv  → 468 ms	 27ms
473 ms  V.scan(317)          → 481 ms	  8ms
484 ms  sortInto(V.sort,  false) (335) → 567 ms	 83ms
570 ms  sortInto(V.sortV, true)  (336) → 650 ms	 80ms
654 ms  V.cA / V.cB (339)    → 673 ms	 19ms
675 ms  V.ghost (358)        → 688 ms	 13ms
688 ms  6 × V.noise (368–389) → 739 ms	 51ms
──────────────────────────────────────────────
总计 413 ms 连续主线程占用
750 ms  boot() → measure()  ← 之后才可能画第 0 帧
```

413 毫秒里没有任何 `await`、没有 `setTimeout`、没有让出。这段时间里：开机扫描条起不来、
输入没人处理、DOM 首绘被推迟。

**它不是帧率问题**：动画时钟 `acc`（815–822）是在 `boot()` 里、这个块之后才开始走的，
所以「60 FPS / 零掉帧 / 最坏 16.8ms」这组数字不受影响。它是载入延迟与可交互性问题，
并且**按 SZ² 放大**：173 行的上限是 900，在 900 下这项工作是 774 下的 1.35 倍
≈ 560ms，也就是高 DPR / 大视口显示器上更糟。

> 交叉验证：并发的另一个会话在同一时刻、用真实播放采样独立测到载入期同步阻塞
> **418–461 ms**，并同样指出 dpr 2 设备上会到 ~0.6 s。两个独立方法给出同一个量级。

### 4.2 修复 A：`Math.pow` → 766 项查表（242 行）

```js
const detail = Math.pow(clamp01((255 - lum) / 118), 0.78);
```

`lum = (r + g + b) / 3` 来自整数通道，所以送进幂函数的输入只有 766 个可能取值
（`r+g+b` ∈ 0..765）；这是一个纯粹被浪费的逐像素幂运算。

实测（599,076 像素 × 5 轮取中位数）：**pow 27.6ms → LUT 8.5ms（3.25×）**，
输出 `pixels_differing: 0 / 2,396,304` 通道 —— 逐字节完全一致。

```js
const TONE = new Float32Array(766);
for (let s = 0; s < 766; s++) TONE[s] = Math.pow(Math.min(1, Math.max(0, (255 - s / 3) / 118)), 0.78);
// 循环内：
const detail = TONE[r + g + b];
```

### 4.3 修复 B：`sortInto` 的逐像素数组 → 预分配计数排序（408、413、415 行）

```js
const run = new Array(len);                                   // 408
run[i] = [dd[q+3], dd[q], dd[q+1], dd[q+2], dd[q+3]];         // 413  每像素一个 5 元数组
run.sort((x, y) => y[0] - x[0]);                              // 415  比较排序
```

实测每次载入 **239,006 个数组/趟，两趟共 478,012 个**，外加每趟一次 O(n log n) 比较排序。

关键点：排序键是**单个字节**（alpha，413 行），所以 256 桶计数排序可以做到零分配、线性时间、
结果完全等价。

实测：**43.3ms → 7.7ms 每趟（5.6×）**；`diff_horizontal: 0`、`diff_vertical: 0`
（各 2,396,304 通道全等）。两趟合计从 163ms（在管线内实测 83 + 80ms）降到约 15ms。

```js
const cnt = new Int32Array(256), off = new Int32Array(256), tmp = new Uint8ClampedArray(SZ * 4);
// 沿用现有的段检测（399–406 行）与 len < 3 跳过，只替换 408–419：
cnt.fill(0);
for (let i = 0; i < len; i++) cnt[dd[at(start + i, line) + 3]]++;
let acc = 0;
for (let s = 255; s >= 0; s--){ off[s] = acc; acc += cnt[s]; }   // alpha 降序
for (let i = 0; i < len; i++){ const q = at(start + i, line);
  const p = (off[dd[q + 3]]++) * 4;
  tmp[p] = dd[q]; tmp[p+1] = dd[q+1]; tmp[p+2] = dd[q+2]; tmp[p+3] = dd[q+3]; }
for (let i = 0; i < len; i++){ const q = at(start + i, line);
  dd[q] = tmp[i*4]; dd[q+1] = tmp[i*4+1]; dd[q+2] = tmp[i*4+2]; dd[q+3] = tmp[i*4+3]; }
```

### 4.4 修复 C：把「还不需要的变体」挪出关键路径

`drawPortrait` 的 `f < 44` 分支（517）只用到三张画布：`base`、`V.ghost`（535）、
`V.sort`（556）。其余全部只在 `runGlitch`（593）里出现：

- `V.sortV` 最早在稳态故障周期 2（f ≥ 246）用到；
- `V.step`/`V.inv`/`V.scan`/`V.cA`/`V.cB`/`V.noise` 最早在 f=44 之后可达，
  而片头锁定期的样式 ①②③④⑤ 只覆盖到 f=58，稳态节奏从 f=158 才开始。

实测可推迟部分 = 441→739ms 减去两趟 `sortInto`（163ms）与 `V.ghost`（13ms）
= **202ms**。

做法：同步只建 `V.ghost` + `V.sort`，其余丢给 `setTimeout(…, 0)` 或
`requestIdleCallback`，并置 `variantsReady` 标志；`runGlitch` 在标志未就位时直接返回。
**必须保留这个 gate**，否则冻帧模式（`?f=`）在 f ≥ 44 直渲染时会画到还不存在的变体。

### 4.5 修复 D：`boot()` 的 40ms 轮询（870 行）

```js
if (!imgReady){ setTimeout(boot, 40); return; }
```

载入期白白叠加最多 40ms 延迟，每次加载都付一次。`imgReady = true`（260）就在
`onload` 末尾，直接在它后面调 `boot()` 即可，轮询可删。

**合计效果**：阻塞块 413ms → 约 211ms（推迟 202ms），块内再做 A+B 后关键工作再省约 89ms，
即**保证第 0 帧前完成的关键路径工作约 120ms**，另外 200ms 被挪进本来闲置的
f=0→44（1.76s）窗口。

---

## 5. 次要项：片头拼装帧是全片最贵的渲染路径（实测，但不建议动）

单次 `render()` 实测耗时：

| 帧 | f=5 | f=20 | f=30 | f=42 | f=45 | f=55 | f≥60 稳态 | f≥60 故障帧 |
|---|---|---|---|---|---|---|---|---|
| µs | 540 | **572** | 520 | 452 | 76 | 92 | 36–56（中位 ~44） | 68–124 |

原因：`f < 44` 每帧 48 个格子，每格 `save → clip → drawImage(整张画布) → restore`
（551–561，整图源在 556），外加 535 的 ghost 格绘制。

但绝对量级：最坏 **572µs = 16.67ms 预算的 3.4%**；整段 300 帧手动驱动总耗时 141.9ms
≈ 0.47ms/帧。所以**保持现状**。

特别提示：**不要**把 556 行改成子矩形 `drawImage(src, col*CW - dx, row*CH - dy, CW, CH, …)`。
`dx` 能到 ±34、`dy` 到 ±7（509–514），源矩形必然越界；按规范此时 `drawImage` 会
裁源**并按比例调整目标矩形**，结果是这条内容被横向缩放而不是平移 —— 画面会变，
而 `sliceTear`（444–447 注释）里已经把这个坑写明了。为 0.2ms 冒这个险不值得。

---

## 6. 其他实测项（无需动作）

- 每帧 `drawImage`：实测 9,176 / 1,029 ≈ **8.9 次/帧**，恒定，不产生分配。
- `ctx.save/restore` + `clip()`：有界（片头 ≤48，撕裂帧 ≤6），见 446–479。
- 后备存储固定为 `SZ` 后由 CSS 缩放（169–174），所以 ≥`SZ` 的显示尺寸不会让每帧变贵。
  `SZ` 推导里读的 `innerWidth/innerHeight/devicePixelRatio`（170–173）不强制布局，
  且只在脚本求值时读一次，无同步布局成本。
- `#glitch` 的 `willReadFrequently` 告警：见 §3.3，真实告警、当前零代价。

## 7. 建议的落地顺序

1. **修复 B（计数排序）** —— 单点收益最大（每趟 5.6×，关键路径省约 70ms），改动局部，
   且已验证输出逐字节一致。
2. **修复 A（LUT）** —— 3 行改动，2.6–3.25×，输出逐字节一致。
3. **修复 D（去掉 40ms 轮询）** —— 一行。
4. **修复 C（推迟变体）** —— 收益最大（202ms）但需要保留 `variantsReady` gate。
5. §3.4 的逐字循环 `f <= 160` 提前退出 —— 顺手清 15 次/帧的 `set()`。
6. §3.3 的 `willReadFrequently` —— 只为消除对浏览器启发式的依赖，不急。
