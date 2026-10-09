# Canvas + DOM 混合动画 60fps 稳定性指南

> 目标读者：在同一个页面上同时跑 canvas 逐帧绘制和 DOM 动画的实现者（本项目：glitch art 实时渲染）。
>
> 本文所有数字都标了出处。**没有出处的数字一律标注为「经验区间」，不代表实测。**
> 标注规则：【规范/文档】= 标准或官方文档明文；【官方实测】= 浏览器厂商博客里的实测数据；【经验区间】= 社区共识或本文推断，需自测确认。

---

## 0. 先给结论

| 问题 | 结论 | 关键数字 |
|---|---|---|
| 每帧预算 | 60Hz 下全部工作必须塞进 16.67ms | 16.67ms（60Hz）、8.33ms（120Hz）；rAF 回调内建议 < 15ms |
| 画布多大安全 | 单层全屏不危险，**重复绘制（overdraw）才危险** | 1080×1920 = 207 万像素，60fps 需 1.244 亿像素/秒填充 |
| drawImage 多少次 | 无官方安全值，取决于源尺寸与是否缩放 | 桌面小 sprite 数百次/帧可行；上万次必挂【经验区间】 |
| 像素回读 | 全屏 getImageData/putImageData 是禁区 | 全屏 1080p 每帧上传约 498 MB/s |
| forced reflow | 只读 geometry 属性本身不贵，**读-写-读-写交替才贵** | 干净布局下读 offsetHeight < 0.1ms；dirty 时触发整棵布局 |
| rAF 时间轴 | 物理用固定步长 + 累加器；纯视觉动画用时间戳算进度 | 后台恢复时 delta 可达数秒，必须 clamp |
| 合成 vs 布局 | 只有 `transform` / `opacity` 能跳过 layout + paint | 改动 `top/left/width` 走完整 5 阶段管线 |
| Panel/层 | 每层要显存 + 上传带宽，移动端代价尤其大 | 滚动/过渡期间合成时间目标约 4–5ms |
| FPS 测量 | rAF 轮询有 7 项已知缺陷，只能当辅助信号 | 判据：gap > 1.5 × 刷新间隔 ≈ 丢帧 |
| iOS | 画布有**硬性面积上限**和**内存上限**，超限直接返回 null | iOS ≤17：16,777,216 像素；iOS 18：67,108,864 |
| iOS 刷新率 | Safari 默认把页面渲染钳到接近 60Hz，即使屏幕是 120Hz ProMotion | 直到 iOS 18 才修好 iPhone Pro 的 120Hz 路径 |

**一句话版本**：把每帧的工作量压到预算的 70% 以内；能不做像素回读就不做；能用 `transform` 就不用 `top/left`；每帧都测，但只测「掉帧比例」而不是平均 FPS。

---

## 1. Canvas 2D 每帧 drawImage 的性能预算

### 1.1 帧预算的硬数字【规范/文档】

刷新率决定预算，预算是**一帧内所有工作的总和**（JS 计算 + 样式计算 + 布局 + 绘制 + 合成 + 浏览器自身开销）：

| 刷新率 | 单帧预算 |
|---|---|
| 60 Hz | 16.67 ms |
| 75 Hz | 13.33 ms |
| 90 Hz | 11.11 ms |
| 120 Hz | 8.33 ms |
| 144 Hz | ≈ 6.94 ms |

web.dev 在《Jank busting for better rendering performance》中给的实操建议是：把 rAF 回调控制在 **15ms 以内**，给浏览器留出渲染和合成的余地。

**建议的预算分配**（本文建议值，非官方数字）：

| 环节 | 建议上限 |
|---|---|
| rAF 回调内的 JS（含 glitch 计算） | 6 ms |
| canvas 绘制命令提交 | 4 ms |
| DOM 样式写入 + 合成 | 2 ms |
| 留白（浏览器内部开销、GC、偶发） | 4 ms |

任何一项超了就先动那一项，别去优化没超的。

### 1.2 画布尺寸与填充率

先算清最基本的物理量。**画布成本正比于「实际填充的像素总数」，不只是画布尺寸**：

```
1080 × 1920 = 2,073,600 像素/层
× 60 帧/秒   = 124,416,000 像素/秒 填充需求（单层、无 overdraw）
```

现代移动 GPU 的填充率在「每秒几亿到几十亿像素」量级，单层全屏本身有余量。真正的杀手是 **overdraw（重复绘制）**：

- `overdraw = 1.5×` 时，需要 1.87 亿像素/秒
- `overdraw = 3×` 时，需要 3.73 亿像素/秒

而且移动 GPU 大多是 **tile-based（分块渲染）架构**，同一块 tile 被反复写入会反复消耗显存带宽，代价不是线性叠加。所以移动端的优化顺序是：**先把全屏重绘降成局部重绘，再谈数量**。

**【规范/文档】硬性尺寸上限**：

| 引擎 | 上限 |
|---|---|
| Chromium 单边 | 32767 px，但受总面积限制（约 2^28 = 268,435,456 像素） |
| iOS Safari ≤ 17 | 面积 16,777,216 像素（即 4096×4096） |
| iOS Safari 18 | 面积 67,108,864 像素（8192×8192），依据 WebKit bug 271002 |

超出面积上限的后果不是「变慢」，是**画布直接不可用**——`getContext('2d')` 返回 `null`，控制台报 `Canvas area exceeds the maximum limit (width * height > 16777216)`。

### 1.3 drawImage 调用次数的现实区间

**没有任何一家官方文档给过「每帧 N 次」的安全值**，因为成本取决于：源图尺寸、是否缩放、坐标是否整数、画布是否背靠 GPU、sprite 是否共享同一张贴图。

可用的参考点：

- 【官方实测】Chrome 团队 2012 年 GPU 加速 `drawImage` 落地时的案例：**180 个 256×256 的 PNG sprite（带 transform）+ 一个 N-body 物理模拟**，在低端笔记本上跑到 30–60fps。当时 GPU 加速的价值就是让 `drawImage` 从 CPU 路径切到 GPU 路径。
- 【经验区间】现代桌面 + GPU 加速 + 小 sprite（≤128×128）+ 整数坐标 + 不缩放：**数百次 drawImage/帧**通常安全。
- 【经验区间】上万次（例如 20,000 个 tile）会明显掉到 60fps 以下，即使全是小图。
- 【经验区间】移动端受填充率和带宽限制，同等条件大约是桌面的 1/3 到 1/5。

**结论**：次数不是指标，**像素总量 × 绘制批次 × 是否缩放** 才是指标。用「每秒填充像素数」而不是「每秒调用次数」做预算，跨设备才可比。

### 1.4 单次 drawImage 贵不贵，看这几个开关

| 做法 | 代价 | 出处 |
|---|---|---|
| 整数坐标（`Math.floor` 后） | 正常 | MDN：浮点坐标会触发 sub-pixel 抗锯齿，浏览器要做额外计算 |
| 浮点坐标 | 额外 AA 计算 | 同上 |
| 在 `drawImage` 里直接缩放 | 显著变慢 | MDN：应在加载时把各种尺寸预渲染到离屏画布，而不是每次缩放 |
| 源图与目标尺寸一致（不缩放） | 最快 | 同上 |
| `getContext('2d', { alpha: false })` | 省掉混合 | MDN：不需要透明背景时应关闭 alpha |
| `shadowBlur` | 极慢 | MDN：「尽量避免使用」 |
| 大量文字渲染（`fillText`） | 极慢 | MDN / web.dev：「文字渲染是非常昂贵的操作」 |
| 频繁切换 `fillStyle` 等状态 | 有成本 | web.dev：状态机切换昂贵，应按颜色分组批量绘制，不要按位置交错 |
| 逐段 `stroke()` 画折线 | 慢 | web.dev：应把折线点全塞进一条 path 再一次 `stroke()` |
| 每个小图单独一次矩形绘制 | 反而可能更快 | web.dev 的例外：包围盒很小的图元（水平/垂直线）分开画可能更优，因为合并会产生大包围盒 |

### 1.5 像素回读：真正的禁区

`getImageData` / `putImageData` 是**唯一能读回像素的手段**，也是性能悬崖：

- 【官方实测】Chrome 团队在 Canvas2D 新特性公告里给出的量级对比（1000×1000 场景）：
  - `drawImage`（canvas → canvas）≈ **160,000 ops/s**
  - `putImageData` ≈ **769 ops/s**（单次约 1.3ms）
  
  **两者相差约 200 倍。**

- 【文档/机制】`getImageData` 会触发 GPU → CPU 回读（readback），这个操作会**打断管线并可能把整张画布从 GPU 加速路径打回 CPU 光栅化**。一旦打回 CPU，后续所有绘制都会慢一个数量级。
- 【官方实测】Middle Engine 的 `drawImage` 基准测试佐证了这一点：同样代码，因调用了 `getImageData` 导致画布降级为 CPU 路径后，`drawImage` 吞吐从「无缩放约 59 ops/s」掉到「缩放到 3000×3000 仅 19.88 ops/s」。
- 【文档】`getContext('2d', { willReadFrequently: true })` 会让浏览器**主动选择 CPU 端画布**——反复读写像素时更快，但其他绘制变慢。这是个二选一，不是免费加速。

**带宽账**（本文计算）：

```
全屏 1920×1080 每帧 putImageData = 1920 × 1080 × 4 字节 ≈ 7.9 MiB
× 60 帧/秒 ≈ 498 MB/s  纯上传带宽
半分辨率（960×540）      ≈ 124 MB/s
```

这个数字在移动端直接决定了可行性。**glitch 效果（pixel sorting、dither、bitcrush）如果必须走像素回读，就把处理区域缩到上表能接受的范围，或者把结果降采样后再放大。**

### 1.6 怎么测：最小可用基准

Chrome 团队推荐的方法论是：**用真实负载，逐步加码，直到帧率掉下来，那个点就是你设备的容量。**

```js
// 迭代式容量探测：找出本机每帧能画多少个 sprite
function probeCapacity(drawOnce, { maxFrameTime = 1000 / 55, cap = 20000 } = {}) {
  let load = 1;
  let slowCount = 0;
  let last = performance.now();

  function tick() {
    const now = performance.now();
    const elapsed = now - last;

    if (elapsed < maxFrameTime && load < cap) {
      load = Math.min(load * 1.25, cap);
    } else {
      slowCount++;
      if (slowCount > 5) {
        console.log(`本机每帧安全上限约 ${Math.floor(load)} 个绘制单元`);
        return;
      }
    }

    last = now;
    drawOnce(load);
    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);
}
```

配套注意事项：

- 【官方实测】**不要用 `setTimeout` 测图形性能**：浏览器把 setTimeout 最小间隔钳到 4ms（理论上最高 250 FPS），而且 Chrome 的绘制命令是先进命令缓冲、下一帧才执行，FPS 数字完全失真。
- 【文档】测之前先确认 canvas 确实走了硬件加速：Chrome 地址栏输入 `about:gpu`，看 `Canvas: Hardware accelerated`。如果显示软件路径，你的所有测量都没意义。
- 【官方实测】因为渲染和屏幕刷新同步，**峰值永远卡在刷新率上**（60Hz 屏幕测不出 >60fps），所以基准测试的读数是「在掉帧之前能画多少」，不是「最快多少 fps」。
- 【文档】用 `performance.now()` 而不是 `Date.now()`：`Date` 会被 NTP 校时影响（时钟可能忽快忽慢），精度也不够衡量 17ms 级的帧。
- 【文档】Chrome DevTools Performance 面板录一段 rAF 循环，看 Frames 轨道里每一帧的 JS / Layout / Paint 耗时分解。

---

## 2. 强制同步布局（forced reflow）

### 2.1 机制

浏览器正常情况下把样式和布局**延迟到帧末统一批处理**：写 1000 次 `style.width`，只算 1 次布局。

但如果你在**写完样式之后立刻读一个依赖几何的属性**，浏览器没有别的选择：它必须当场把样式重算 + 布局跑完，才能给你一个正确的返回值。这就是强制同步布局（forced synchronous layout / forced reflow）。

单个不算大问题。真正致命的是**交替**：

```js
// 布局抖动（layout thrashing）：每次迭代都强制一次完整布局
for (let i = 0; i < items.length; i++) {
  items[i].style.width = box.offsetWidth + 'px';  // 读 → 写 → 下一轮读又得重算
}
```

【经验区间/文档例证】一次布局在复杂页面上可能耗时约 5ms；100 个元素的这种循环 = 100 次布局 = 约 500ms，足够丢掉 30 帧。**同样的代码，只是把读写顺序拆开，成本就从 100 次布局降到 1 次。**

### 2.2 触发强制布局的属性清单

【规范/文档】以下读取操作，在「布局脏了」的情况下会强制刷新布局：

| 类别 | 属性/方法 |
|---|---|
| 盒子尺寸 | `offsetWidth` `offsetHeight` `offsetTop` `offsetLeft` `offsetParent` |
| 客户区 | `clientWidth` `clientHeight` `clientTop` `clientLeft` |
| 滚动 | `scrollTop` `scrollLeft` `scrollWidth` `scrollHeight` |
| 矩形 | `getBoundingClientRect()` `getClientRects()` |
| 计算样式 | `getComputedStyle()`（读取依赖布局的属性时；只读 `color` 这类不触发） |
| 滚动动作 | `scrollIntoView()` `scrollBy()` |
| 焦点/文本 | `el.focus()`（需要确定滚动位置时）、`el.innerText`（需渲染后文本） |
| Range | `Range.getBoundingClientRect()` |

**关键区分**：读这些属性本身永远是合法的、便宜的——**只要布局是干净的**。

- 【经验区间/文档】干净布局下读 `offsetHeight` < **0.1ms**（走缓存）。
- 【文档】只有「读之前有未提交的写」才贵。所以规则是**顺序问题，不是属性黑名单问题**。

### 2.3 缓存策略

三条策略，按优先级：

**策略 A：读-写分离（首选）**

```js
// ❌ 读-写-读-写
items.forEach(el => { el.style.height = el.offsetHeight * 2 + 'px'; });

// ✅ 先全读，再全写
const heights = items.map(el => el.offsetHeight);
items.forEach((el, i) => { el.style.height = heights[i] * 2 + 'px'; });
```

**策略 B：缓存到变量 / 用 Observer 代替轮询**

```js
// ❌ 每帧读，等于每帧赌一次布局是否 dirty
function frame() {
  const w = stage.clientWidth;
  canvas.style.width = w + 'px';
  requestAnimationFrame(frame);
}

// ✅ ResizeObserver 在布局稳定后回调，不会强制刷新
const ro = new ResizeObserver(([entry]) => {
  const w = entry.contentRect.width;
  canvas.style.width = w + 'px';
});
ro.observe(stage);
```

`ResizeObserver` / `IntersectionObserver` 的回调在布局已结算之后投递，**不会触发强制布局**，是替代「每帧读尺寸」的现代做法。

**策略 C：把测量推到下一帧**

如果确实需要「写入之后的新几何值」，把它拆成两帧：

```js
// 第 1 帧：只写
element.style.width = '50%';
// 第 2 帧：才读（此时布局已经正常结算过一轮）
requestAnimationFrame(() => {
  console.log(element.offsetWidth);
});
```

**策略 D：限制爆炸半径**

控制不了第三方代码（动画库、tooltip 定位器、自适应输入框都爱读几何）时，用 CSS containment 把强制重排限制在子树内：

```css
.glitch-panel {
  contain: layout;   /* 该子树的内部布局变化不外溢 */
}
```

### 2.4 缓存的失效边界

缓存值描述的是**某一刻的布局状态**。以下情况必须重新测，不能无限期持有全局缓存：

- 视口尺寸变化（`resize`、`orientationchange`）
- 字体加载完成（`document.fonts.ready`）——文字宽度会变
- 内容增减导致文档高度变化
- 父容器尺寸变化

### 2.5 怎么发现强制布局

- 【文档】Chrome DevTools Performance 面板有 **Forced Reflow** 洞察，直接指出触发的代码位置。DevTools 给的建议阈值是：**单次强制重排不应超过 30ms**，并且应尽量减少「紧挨着几何写入之后的几何读取」。
- 【文档】**Long Animation Frame API（LoAF）** 提供 `forcedStyleAndLayoutDuration` 字段，可以在真实用户环境（field）里定位强制同步布局的总耗时，不需要开 DevTools。
- 【经验区间】如果 trace 里出现你找不到来源的 forced reflow，优先怀疑第三方测量代码，而不是自己的循环。

---

## 3. rAF 时间轴正确写法

### 3.1 时间戳的语义【规范/文档】

`requestAnimationFrame(callback)` 的回调收到一个 `DOMHighResTimeStamp`：

- 它是**本帧开始渲染的时刻**（MDN 表述为「上一次帧渲染结束」），不是「回调被调用的时刻」——所以比在回调里调 `performance.now()` 更准确。
- 它与 `performance.now()` **同一个时间原点**，单调递增，可用于直接计算差值。
- **频率跟随显示刷新率**，不保证 60Hz：可能是 60 / 75 / 90 / 120 / 144Hz，也可能因负载被降频。

**不要用 rAF 的调用次数当时间源**（「每帧移动 5px」这种），它在不同刷新率设备上速度不同。

### 3.2 三种写法，按用途选

**写法 1：纯视觉动画 → 用时间差算进度（推荐给 glitch 的视觉抖动）**

```js
let startTime = null;

function frame(ts) {
  if (startTime === null) startTime = ts;
  const elapsed = ts - startTime;          // 从开始到现在的真实毫秒数
  const progress = Math.min(elapsed / 2000, 1);   // 2 秒的动画进度 0→1

  render(progress);                        // render 只依赖 progress
  if (progress < 1) requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
```

好处：掉帧不会导致动画「跑得慢」，它只是跳过中间状态直接到正确位置。**抖动/闪烁类效果尤其需要这个性质**——否则 30fps 时 glitch 的节奏会变成正常的一半。

**写法 2：物理/状态模拟 → 固定步长 + 累加器**

见 3.3。

**写法 3：低功耗 idle 模式 → 按帧数节流**

```js
let frameCount = 0;
function frame(ts) {
  if (++frameCount % 2 === 0) render();   // 降到 30fps
  requestAnimationFrame(frame);
}
```

注意：**按帧数节流在不同刷新率上得到不同结果**——`%2` 在 60Hz 上是 30fps，在 120Hz 上是 60fps。要固定节奏就按时间判断，不按帧计数。

### 3.3 固定步长 vs 可变步长

这是游戏循环的老问题，答案在 Gaffer On Games 的经典文章《Fix Your Timestep!》里。

**可变步长（`dt = now - last`）的问题**：

1. **物理不稳定**：步长变化会让积分器误差变化。同样一段运动，在不同 dt 下解出不同轨迹（数值积分不满足「时间可加性」）。
2. **掉帧时跳变**：一次 100ms 的卡顿会让 `dt` 突然变成正常值的 6 倍，物体瞬移，或者穿过碰撞体（tunneling）。
3. **不可复现**：无法重放、难以调试。

**固定步长 + 累加器（正确解法）**：

```js
const DT = 1 / 60;              // 固定物理步长（秒）
const MAX_FRAME = 0.25;         // Gaffer 建议的单帧上限：250ms
let accumulator = 0;
let lastTime = null;
let prevState = null, currState = null;

function frame(ts) {
  requestAnimationFrame(frame);   // 尽早注册，避免丢帧

  if (lastTime === null) { lastTime = ts; prevState = currState = initState(); return; }

  let delta = (ts - lastTime) / 1000;
  lastTime = ts;

  // 关键：clamp，防止「死亡螺旋」
  if (delta > MAX_FRAME) delta = MAX_FRAME;

  accumulator += delta;

  while (accumulator >= DT) {
    prevState = currState;
    currState = integrate(currState, DT);   // 永远用固定 DT
    accumulator -= DT;
  }

  const alpha = accumulator / DT;           // 0..1 的插值因子
  render(interpolate(prevState, currState, alpha));
}
requestAnimationFrame(frame);
```

要点：

- `while` 里的 `DT` 永远是常量，所以物理行为只依赖步数，不依赖帧率。
- **必须 clamp `delta`**。Gaffer 给的上限是 **250ms**。不 clamp 时：一次 2 秒的卡顿 = 120 次物理迭代 = 更卡 = 下次 delta 更大，这就是所谓的**死亡螺旋（spiral of death）**。
- `alpha` 用于渲染插值，把模拟状态平滑到当前真实时间点，避免固定步长带来的视觉抖动。

**glitch 项目里的取舍**：视觉抖动大多不需要真正的物理积分，用 3.2 的写法 1 就够，且更省 CPU。只有当动画有「状态依赖」（例如滴落、扩散、衰减累积）时才需要固定步长。

### 3.4 避免卡顿累积

三条铁律：

1. **不要累加位置**：`x += speed` 会在掉帧时永久落后。用 `x = f(elapsed)`。
2. **不要用帧计数换算时间**：`frames / 60` 在 120Hz 设备上快一倍。
3. **对 delta 设上限**：任何 `delta` 进入业务逻辑前先 `Math.min(delta, MAX)`。

【官方实测/文档】web.dev 给了一个很有说服力的对照：`setTimeout(fn, 16)` 与 60Hz 的 16.67ms 周期**每帧差 0.67ms**，累积 **24 帧（约 400ms）就刚好差出一整个帧周期**——表现为周期性的一次重复帧/跳帧，肉眼很容易看出节奏卡顿。而且 setTimeout 还会受后台标签页、电池模式、系统负载影响。**任何视觉动画都不该用定时器驱动。**

### 3.5 后台标签页与恢复

- 【规范/文档】rAF 在后台标签页和隐藏的 iframe 里**会被暂停**（省电/省 CPU），恢复时继续。
- **但时间戳不暂停**。`ts` 是单调时钟，恢复后的第一帧 `ts - lastTime` 可能是**几秒甚至几分钟**。
- 不做处理就会：物理瞬间跑几千步（如果没 clamp）、纯视觉动画直接跳到终点。

正确做法：

```js
let lastTime = null;

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    lastTime = null;        // 强制下一帧重新校准，丢掉整段间隔
    accumulator = 0;        // 累加器也要清，否则会一次性补算
  }
});
```

**注意**：rAF 停止不代表页面停止。`setInterval` 在后台同样被节流（Chrome 后台标签页常被钳到 ≥1000ms），所以「后台继续跑模拟」这个需求不能靠定时器，只能放到 Web Worker 里（Worker 的定时器同样受节流，但行为可控）。

### 3.6 高刷新率设备

- 【规范/文档】rAF 频率「通常匹配显示刷新率」，但**规格没有保证任何具体数值**，由 UA 决定。
- 120Hz 设备上预算从 16.67ms 掉到 **8.33ms**——不是「更流畅」，是**更难达标**。原来勉强 60fps 的代码在 120Hz 设备上会掉到 60fps 以下，视觉上反而更糟。
- 【经验区间】推荐：**主动定义目标帧率并跳过多余帧**。如果你的效果设计上只需要 30fps，就不要跑满，把省下的预算留给其他工作：

```js
const TARGET = 1000 / 30;   // 30fps
let last = 0;

function frame(ts) {
  requestAnimationFrame(frame);
  if (ts - last < TARGET - 1) return;   // -1 抵消时间戳抖动
  last = ts;
  render(ts);
}
```

- 【官方实测/文档】web.dev 的 smoothness 文章里有一条重要观察：**稳定的 30fps 比不稳定的 60fps 观感更好**——用户对「帧率不一致」的敏感度高于对「帧率较低」的敏感度。所以掉帧时可以考虑主动降半帧率（60→30），而不是让它随机抖动在 45–60 之间。

---

## 4. 何时用 transform/opacity，何时不能用 top/left/width

### 4.1 三条渲染路径【规范/文档】

像素管线有 5 个阶段：**JS → Style → Layout → Paint → Composite**。你改的属性决定走哪条路：

| 你改的属性 | 走的阶段 | 代价 |
|---|---|---|
| `width` `height` `top` `left` `margin` `padding` `font-size` | JS → Style → **Layout** → Paint → Composite | 最贵，可能触发整个文档重排 |
| `color` `background-image` `box-shadow` `border-radius` | JS → Style → **Paint** → Composite | 中等，跳过 layout |
| **`transform` `opacity`** | JS → Style → **Composite** | 最便宜，跳过 layout 和 paint |

【规范/文档】今天**只有这两个属性**能完全交给合成器（compositor）处理。这是 web.dev 的明确结论，也是所有「动画要只动 transform/opacity」建议的来源。

### 4.2 前提：元素必须在自己的合成层上

仅仅用 `transform` 不够——**被动画的元素必须被提升（promote）成独立合成层**，否则它还是跟着整棵子树一起被重绘。

```css
.moving-element {
  will-change: transform;      /* 现代写法 */
}
```

```css
.moving-element {
  transform: translateZ(0);    /* 老浏览器的等价写法 */
}
```

### 4.3 层的代价【规范/文档】

**每一层都要显存 + 管理开销，还要把纹理从 CPU 上传到 GPU。** web.dev 的原话是：低内存设备上，创建层的代价可以**远远超过**它带来的收益。

因此：

- **不要批量提升**。下面这种写法（把所有元素都提升）是明确的错误示范：

```css
* { will-change: transform; }   /* ❌ 层爆炸 */
```

- 【规范/文档】滚动/过渡这类性能关键路径上，**合成时间的目标是 4–5ms**。用 DevTools 的 Paint profiler 看层数量和层的创建原因。
- 【规范/文档】高 DPI 屏幕上 `position: fixed` 元素会被自动提升；低 DPI 上不会（因为会改变文字渲染方式，从 subpixel 变 grayscale）。这解释了「同样的代码在不同设备上表现不一致」。

### 4.4 will-change 的正确用法【规范/文档】

MDN 对 `will-change` 的态度相当保守，值得逐条照做：

| 建议 | 说明 |
|---|---|
| **不要滥用** | 浏览器本来就在尽力优化；`will-change` 触发的强优化会占用大量资源，滥用会**更慢** |
| **当成最后手段** | 原文：不要用它来「预防」性能问题，只在已经出问题时用它 |
| **用脚本开关，别写死在样式表** | 写在样式表里意味着浏览器**长期**保留这份优化；用脚本在动画前后挂上和摘下 |
| **提前一点设置** | 给浏览器时间做预先准备，但不要提前太久 |
| **限制在深层、小范围的元素上** | 该属性作用于整棵子树；对 `<body>` 这种大范围用非 `auto` 值是负优化 |
| **注意会创建层叠上下文** | `will-change: opacity` 会提前创建 stacking context，可能改变视觉效果 |

推荐模式：

```js
function animateOnce(el) {
  el.style.willChange = 'transform';         // 动画前挂上
  el.addEventListener('transitionend', () => {
    el.style.willChange = 'auto';            // 动画后摘下，释放显存
  }, { once: true });
  el.classList.add('running');
}
```

**注意**：用 CSS `@keyframes` 做的动画，其属性**已经等价于被 `will-change` 声明了**，不需要额外加。

### 4.5 DOM + canvas 混合时的具体建议

| 场景 | 做法 |
|---|---|
| 移动 canvas 本身在页面上的位置 | 用 `transform: translate3d()`，不要改 `left/top` |
| canvas 缩放适配 | 用 CSS `transform: scale()`（MDN 明确说 CSS transform 走 GPU，比改 `width/height` 快） |
| 全屏遮罩层显隐 | 用 `opacity`，不要用 `display:none` 切换（`display` 会让 layer 失效并触发布局） |
| glitch 的「切片位移」效果 | 在 canvas 内部用 `drawImage` 的源矩形做，不要用多个 DOM 元素各自 `top` 位移 |
| 需要高频改尺寸 | 用 `ResizeObserver` + 写入下一帧，或改用 `transform: scale()` 代替真实尺寸变化 |

**canvas 的两个尺寸概念别搞混**：

```js
// canvas.width / height  = 后备存储（像素数）→ 改变它会清空画布并重新分配内存，很贵
// canvas.style.width/height = 显示尺寸（CSS 像素）→ 便宜
```

每帧改 `canvas.width` 是灾难（重新分配 + 清空 + 重新加速），只在 resize 时改。

---

## 5. 离屏预渲染（offscreen pre-rendering）

### 5.1 收益原理【规范/文档】

MDN 的表述：**如果你每帧都在重复同样的绘制操作，把它挪到离屏画布，然后只把结果 `drawImage` 回来。**

web.dev 的 Mario 例子最直观：

```js
// ❌ 每帧重画 Mario 的帽子、胡子、"M"（很多次 path 操作 + 文字）
function render() {
  drawMario(context);
  requestAnimationFrame(render);
}

// ✅ 只画一次，之后每帧只做一次 drawImage
const m_canvas = document.createElement('canvas');
m_canvas.width = 64;
m_canvas.height = 64;
drawMario(m_canvas.getContext('2d'));

function render() {
  context.drawImage(m_canvas, 0, 0);
  requestAnimationFrame(render);
}
```

**收益最大的场景（按 web.dev 的排序）**：

1. **文字渲染**——web.dev 明文「非常昂贵的操作」。任何静态文字/标签/数字都应预渲染成图。
2. **复杂 path / 多次 `stroke()`**——合并成一次离屏绘制。
3. **带滤镜/阴影的图元**（`shadowBlur`、`filter`）——MDN 说尽量别用，如果必须用就预渲染一次。
4. **重复出现的小图元组合**（粒子、图标、噪点块）。

### 5.2 「紧贴」原则（最容易踩的坑）【官方实测】

web.dev 的基准测试里有一个反直觉的结果：**预渲染画布尺寸不合适的话，收益会被拷贝成本吃掉。**

| 离屏画布 | 结果 |
|---|---|
| 100×40（紧贴内容） | 好 |
| 300×100（内容周围留大量空白） | 明显更差 |

原因：`drawImage` 的成本**与源目标尺寸成正比**，不只与可见内容成正比。所以离屏画布必须**刚好包住要画的东西**。

### 5.3 变体表策略

不要在 `drawImage` 里缩放——MDN 明确说要把各种尺寸在**加载时**预渲染好。

```js
// 变体表：一次性生成，之后全部是 1:1 无缩放 drawImage
const cache = new Map();

function getVariant(key, w, h, renderFn) {
  let c = cache.get(key);
  if (!c) {
    c = document.createElement('canvas');
    c.width = w;             // 紧贴
    c.height = h;
    renderFn(c.getContext('2d'));
    cache.set(key, c);
  }
  return c;
}

// 使用：key 包含所有影响外观的参数
ctx.drawImage(getVariant(`glyph:${char}:${size}:${color}`, w, h, drawGlyph), x, y);
```

变体表的维度选择：

- **值得做变体的**：尺寸档位（离散几档）、颜色档位、模糊半径档位、字符集（有限）。
- **不值得做的**：连续参数（旋转角度、缩放比例）——变体数爆炸。连续参数用 `transform` 或接受一次缩放绘制。
- **必须加容量上限**：变体表失控就是 iOS 上「Total canvas memory use exceeds the maximum limit」的直接原因（见 7.2）。建议设 LRU 上限并在超限时按浏览器类型收紧。

### 5.4 分层画布（对 glitch 尤其重要）

【规范/文档】MDN 和 web.dev 都推荐：把**变化频率不同的内容放到不同的 canvas 元素上**，用绝对定位叠起来。

典型三层：

```html
<div id="stage">
  <canvas id="ui-layer"></canvas>        <!-- 只响应用户输入才重绘 -->
  <canvas id="game-layer"></canvas>      <!-- 每帧重绘（glitch 主图层） -->
  <canvas id="background-layer"></canvas><!-- 基本不变 -->
</div>
```

```css
#stage { position: relative; }
canvas { position: absolute; }
#ui-layer { z-index: 3; }
#game-layer { z-index: 2; }
#background-layer { z-index: 1; }
```

关键收益：**清空前景层不会影响背景层**。如果全画在一张上，每帧的 `clearRect` 都要把静态背景一起重画。

MDN 还给了两个更省的做法：

- 静态背景**根本不用 canvas**，用 CSS `background` 画在一个 `<div>` 上，塞在 canvas 底下。这样它一次都不会被重绘。
- 用**脏矩形**（redraw regions）：记录上一帧绘制的包围盒，只 `clearRect(last.x, last.y, last.w, last.h)`，而不是清全屏。web.dev 称之为 redraw regions 技术。

### 5.5 OffscreenCanvas 的真实价值【规范/文档】

要纠正一个常见误解：**OffscreenCanvas 本身不比普通 canvas 快**。它的价值是**不阻塞主线程**。

```js
const canvas = document.getElementById('glitch');
const offscreen = canvas.transferControlToOffscreen();
const worker = new Worker('glitch-worker.js');
worker.postMessage({ canvas: offscreen }, [offscreen]);

// glitch-worker.js
self.onmessage = (e) => {
  const ctx = e.data.canvas.getContext('2d');
  function render() {
    // 在这里做重活：像素处理、大量 drawImage
    // 主线程完全不受影响，DOM 动画继续跑
    requestAnimationFrame(render);
  }
  render();
};
```

**对「canvas + DOM 混合动画」这个场景，这是最重要的一条建议**：如果你同时要跑 canvas 的 glitch 效果和 DOM 动画（文字抖动、CSS 过渡），把 canvas 整个搬进 Worker，主线程就只剩 DOM 和合成——两边的预算不再互相抢。web.dev 的 OffscreenCanvas 演示里，主线程被占满时 Worker 里的动画依然流畅。

迁移成本与限制：

- 需要传输控制权（`transferControlToOffscreen`），**不可逆**——传出去之后主线程不能再拿 `getContext`。
- Worker 里没有 DOM，所有测量/事件要走 `postMessage`。
- Worker 的 rAF 可用性见 7.4（Safari 直到 16.4 才支持）。
- `OffscreenCanvas` 在 Worker 里也能转成 `ImageBitmap` 再传回主线程展示。

### 5.6 加速状态陷阱（glitch 项目最容易踩）【官方实测】

一次 `getImageData` 就可能把画布从 GPU 路径打回 CPU 路径，**后续所有绘制慢一个数量级**，而且这个状态不会自己恢复。

规避手法：

1. **像素处理单独一张画布**，别和主渲染画布混用。主画布永远保持 GPU 路径。
2. **需要的像素尽量小**：只 `getImageData` 你要处理的小区域，不是全屏。
3. **降低处理分辨率**：把 glitch 处理放在 1/2 或 1/4 尺寸的缓冲上，处理完再缩放贴回。视觉上抖动/噪点类效果对分辨率不敏感，性能和收益都划算。
4. **如果必须反复读写**，就显式声明 `{ willReadFrequently: true }`，让浏览器选对路径（CPU 路径对反复读写更快，对绘制更慢——认这个账，别让它随机摇摆）。
5. **测的时候专门确认路径**：`about:gpu` 看加速状态；DevTools Performance 里看 Paint/Raster 的耗时是否突然翻了 10 倍。

---

## 6. 准确测 FPS 和掉帧的可信方法

### 6.1 为什么 rAF 轮询不可信

【规范/文档】web.dev 的《Towards an animation smoothness metric》明确列了 rAF 轮询的 7 个问题：

1. 每个脚本都要自己搭一套轮询循环。
2. 会占关键路径（测量本身消耗预算）。
3. 持续轮询会**阻止 `requestIdleCallback` 拿到长空闲块**（超过一帧的空闲）。
4. 同理，也会阻止浏览器调度其他长任务（更久的 GC、后台/推测性工作）。
5. 采样开关一开一关，就会**漏掉超预算的那些帧**（恰恰是你想测的）。
6. 浏览器使用可变刷新率时（省电模式、可见性状态），会**误报**。
7. **最重要的一条：它捕捉不到所有类型的动画更新**——纯合成器动画（transform/opacity 在合成线程上跑）在主线程被阻塞时依然流畅，但 rAF 采样器完全看不到，它只会报「0 fps」。

第 7 条对 canvas + DOM 混合页面是致命的：你的 DOM 动画可能一直很流畅，同时 rAF 采样器因为 canvas 卡顿而报 0。

**结论**：rAF 轮询只能作为**辅助信号**，且只在短测量窗口内开启。

### 6.2 可用的现场测量代码

```js
/**
 * 测量一段交互窗口内的帧间隔分布 + 长动画帧归因。
 * 只在需要的时候开，测完立刻停。
 */
function measureFrames(label, { sampleRate = 1 } = {}) {
  if (Math.random() > sampleRate) return () => {};   // 抽样，避免全量上报

  const frames = [];
  const longFrames = [];
  let rafId = requestAnimationFrame(function tick(t) {
    frames.push(t);
    rafId = requestAnimationFrame(tick);
  });

  let observer = null;
  if (PerformanceObserver.supportedEntryTypes?.includes('long-animation-frame')) {
    observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        longFrames.push({
          ms: Math.round(entry.duration),
          blocking: Math.round(entry.blockingDuration),
          forcedLayout: Math.round(entry.forcedStyleAndLayoutDuration),
          script: entry.scripts?.[0]?.sourceURL,
          fn: entry.scripts?.[0]?.sourceFunctionName,
        });
      }
    });
    observer.observe({ type: 'long-animation-frame', buffered: false });
  }

  return function stop() {
    cancelAnimationFrame(rafId);
    observer?.disconnect();

    // 刷新率没有 API 可查：用观测到的最快间隔的 10 分位估计
    const gaps = [];
    for (let i = 1; i < frames.length; i++) gaps.push(frames[i] - frames[i - 1]);
    gaps.sort((a, b) => a - b);
    const expected = gaps.length ? Math.max(8, gaps[Math.floor(gaps.length * 0.1)]) : 16.7;

    // 判据：gap 超过 1.5 倍刷新间隔 ≈ 至少丢了一帧
    let late = 0;
    for (const g of gaps) if (g > expected * 1.5) late++;

    const p95 = gaps.length ? gaps[Math.floor(gaps.length * 0.95)] : 0;

    console.table({
      label,
      frames: frames.length,
      lateFrames: late,
      latePercent: ((late / Math.max(gaps.length, 1)) * 100).toFixed(1) + '%',
      estimatedHz: Math.round(1000 / expected),
      p95GapMs: p95.toFixed(1),
      maxGapMs: (gaps[gaps.length - 1] || 0).toFixed(1),
      longFrames: longFrames.length,
    });
    if (longFrames.length) console.table(longFrames.slice(0, 5));
  };
}

// 用法：
const stop = measureFrames('glitch-burst', { sampleRate: 0.1 });
setTimeout(stop, 3000);
```

### 6.3 度量口径：别看平均 FPS

【规范/文档】web.dev 的建议是把指标从「FPS」改成「**掉帧比例**」：

| 指标 | 定义 |
|---|---|
| **Average Percent Dropped** | 所有非空闲帧中，未完整呈现的比例 |
| **Worst Case Percent Dropped** | 按 **1 秒滑动窗口**统计的最差值 |
| **P95 Percent Dropped** | 按 **1 秒滑动窗口**统计的 95 分位 |

为什么必须用滑动窗口：**单次丢帧用户可能看不出来，连续丢帧才叫卡顿**。平均值会掩盖这个区别——「平均 58fps」听起来没问题，但如果是每秒卡一坨 3 帧连丢，体验很差。

web.dev 还把帧分了状态（用来算 smoothness 分数）：

| 状态 | 含义 |
|---|---|
| No Update Desired | 空闲、重复上一帧 |
| Fully presented | 主线程在期限内提交，或本就不需要主线程更新 |
| Partially presented | 只有合成器更新（主线程迟到的更新没有视觉变化，或不属于影响流畅度的动画） |
| Dropped frame | 需要更新但没有 |
| Stale frame | 渲染出来了，但 GPU 在 vsync 期限前没提交上屏 |

### 6.4 PerformanceObserver 可用的类型

| 类型 | 阈值 | 用途 | 浏览器支持 |
|---|---|---|---|
| `longtask` (`PerformanceLongTaskTiming`) | 主线程连续占用 ≥ **50ms** | 主线程阻塞；TTI / TBT 的基础 | Chrome 58+，Chromium 系 |
| `long-animation-frame` (LoAF) | 帧耗时 ≥ **50ms** | 更好的归因：脚本来源、`forcedStyleAndLayoutDuration`、`blockingDuration` | Chromium 系 |
| `event` (Event Timing) | — | 输入延迟 → INP | Chromium 系 |

```js
// 长任务（>50ms）
new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    console.log('longtask', entry.duration.toFixed(1) + 'ms',
                entry.attribution?.map(a => a.containerName || a.name));
  }
}).observe({ type: 'longtask', buffered: true });
```

**Long Tasks vs LoAF 的区别**：Long Tasks 看的是「任务」，LoAF 看的是「帧」。LoAF 解决了 Long Tasks 的两个短板——归因更准（能指出是哪个脚本/函数）、覆盖面更广（包含渲染工作）。要做动画性能归因，优先用 LoAF。

**阈值参考**：

- 【规范/文档】50ms 是「长任务」的定义线，来自 RAIL 模型：用户输入应在 50ms 内处理完，以保证 100ms 内给出可见响应。
- 【规范/文档】INP 指标的实际阈值宽松到 **200ms**（考虑慢设备）。
- 【经验区间】对于 60fps 动画，50ms 已经太晚了——**一帧的预算是 16.67ms，超过就是丢帧**。50ms 的意义是「用户已经能感觉到卡」，不是「动画还流畅」。

### 6.5 DevTools 的正确用法

| 工具 | 位置 | 看什么 |
|---|---|---|
| **Frame Rendering Stats** | DevTools → Command Menu → Show Rendering → 勾选 | 顶部浮层：当前/平均 FPS、GPU 显存、**每帧呈现状态的柱状图**（绿=按时呈现，红=丢弃/部分呈现）。注意：报告的是**完全呈现的帧**，所以数字会低于 rAF 计数 |
| **Performance 面板 Frames 轨道** | Performance 录制 | 每帧一个 tile，标注 `Frame` / `Dropped Frame` / `Partially Presented Frame`。丢帧是红色斜纹块，垂直对齐下方主线程轨道就能找到元凶 |
| **Forced Reflow 洞察** | Performance 面板带洞察的录制 | 直接指出触发强制重排的代码位置 |
| **Paint profiler** | Performance 录制设置里启用 | 层列表 + 每层创建的原因 |
| **Performance HUD** | `chrome://flags/#show-performance-metrics-hud` | 实时的 Core Web Vitals + 实验性的 Percent Dropped Frames |
| **about:gpu** | 地址栏 | `Canvas: Hardware accelerated` 确认加速路径 |

trace 级别的分析（需要更深的归因时）：

- `TrackerValidation` 事件 → 哪些动画在跑
- `PipelineReporter` 事件 → 每帧的完整时间线 + 阻塞原因分解
- `EventLatency` 事件 → 输入驱动的动画从输入到可见更新耗时

### 6.6 测量时不要做的事

| 不要做 | 原因 |
|---|---|
| 用 `setTimeout` 驱动测量循环 | 最小间隔被钳到 4ms，Chrome 绘制命令延迟执行，读数无意义 |
| 用 `Date.now()` 计时 | 受 NTP 校时影响，精度不足 |
| 在测量代码里做重活 | 测量本身会污染预算 |
| 只看平均 FPS | 掩盖突发掉帧（见 6.3） |
| 长开 rAF 轮询 | 阻塞 `requestIdleCallback`，干扰浏览器调度，反而制造卡顿 |
| 只测桌面 | 移动端填充率、带宽、内存上限完全不同 |
| 只测无负载状态 | 必须测「真实负载」：canvas 在画、DOM 在动、有网络回调 |

---

## 7. 移动端 Safari 的特殊限制

iOS 的约束和其他浏览器**不是量级差异，是性质差异**——很多限制是硬性的，撞上就是功能不可用，不是变慢。下面逐条标出。

### 7.1 画布尺寸：硬上限

| iOS 版本 | 单张画布面积上限 | 依据 |
|---|---|---|
| ≤ 17 | **16,777,216 像素**（2^24，即 4096×4096） | WebKit bug 145998；MDN 也记载 iOS 有这个限制 |
| 18+ | **67,108,864 像素**（2^26，即 8192×8192） | WebKit bug 271002（2024 年 3 月提交） |

**这是面积上限，不是单边上限**：`4096×4096` 可以，`4097×4096` 不行；但 `8192×2048` 如果总面积没超也可以。

触发后果：

```
Canvas area exceeds the maximum limit (width * height > 16777216).
```

并且 **`getContext('2d')` 返回 `null`**——你的渲染代码会静默地什么都不做或抛错。必须在创建画布前就检查尺寸。

```js
// 安全尺寸计算：按面积上限等比缩
function safeCanvasSize(w, h, maxPixels = 16777216) {
  const area = w * h;
  if (area <= maxPixels) return { w: Math.floor(w), h: Math.floor(h) };
  const scale = Math.sqrt(maxPixels / area);
  return { w: Math.floor(w * scale), h: Math.floor(h * scale) };
}
```

注意：`16384×16384` 这类尺寸在桌面 Chromium 上可能可行（受 2^28 面积限制），在 iOS 上直接崩——**必须按最严的平台设上限**。

### 7.2 画布内存：另一个硬上限

- 【来源：WebKit bug 195325 / PQINA 实测】iOS Safari 对**整个页面所有画布的总后备存储**有上限：
  - iOS 12 时期约 **224 MB**（有报告称曾从 448MB 下调到 224MB）
  - iOS 15+ 约 **384 MB**
  - 具体值随设备内存浮动
- 超限的报错是 `Total canvas memory use exceeds the maximum limit (384 MB)`，后果同样是 `getContext('2d')` 返回 `null`。

算一笔账：

```
4096 × 4096 × 4 字节 = 64 MiB   ← 一张满额画布
384 MB / 64 MiB = 6 张             ← 6 张就到底了
```

而 glitch 项目常见的做法（变体表 + 多层画布 + 离屏缓冲）**很容易就超过 6 张**。

**Safari 的独有坑**：Safari 释放画布的决定比别的浏览器慢得多——即使你不再引用它，它还会留一段时间。所以「用完就不管」会累积到超限。

**解法：主动释放**

```js
// 强制 Safari 释放画布的后备存储
function releaseCanvas(canvas) {
  canvas.width = 0;
  canvas.height = 0;
  // 有些版本需要 1 而不是 0
  // canvas.width = 1; canvas.height = 1;
}
```

配套注意：报告指出 Safari 存在**跨会话缓存**或**刷新后不重算可用内存**的问题——超限之后刷新页面，警告**可能仍然存在**，要刷新多次或清缓存才消失。所以测试时必须用干净会话，别被上一次的状态误导。

**实践建议**：

| 做法 | 说明 |
|---|---|
| 分层不要超过 3 层 | 每层都是全额后备存储 |
| 变体表设 LRU 上限 | 按 `总像素数` 而不是 `条目数` 计账 |
| DPR 上限设 2 | DPR=3 时全屏画布 = 3.9 倍像素，收益远小于风险 |
| 尺寸变化时复用画布 | 改 `width` 会重新分配，但比新建一个更安全 |
| 明确释放离屏画布 | 每次 `releaseCanvas` 都是必要的 |
| 用 `performance.memory` 或 `measureUserAgentSpecificMemory()` 监控 | 不是所有浏览器都有，作为辅助 |

### 7.3 滚动与 rAF

- 【文档/历史】iOS Safari 长期以来在**用户滚动（尤其是惯性/momentum 滚动）期间限制或暂停页面 JS 执行**，以保证合成器维持 60fps。这是「scroll-linked JS 在 iOS 上体验差」的根源。
- 【文档】没有单一的「在 X 版本修复」公告。行为随 iOS 版本逐步改善，但相关怪癖仍有记录：
  - WebKit bug 187449：惯性滚动期间无法设置 `scrollTop`
  - WebKit bug 238616：rAF 内读到的滚动位置不准（长期未彻底解决）
  - 一个 rAF 周期内可能触发多个 scroll 事件
- **实践结论**：**不要在 iOS 上做滚动联动的逐帧动画**。如果必须联动，用 CSS 的 `position: sticky` / `scroll-driven animations` / transform 由合成器处理，不要用 JS 每帧读 `scrollY` 再算。

对本项目的映射：如果 glitch 效果需要「随滚动增强」，那么应该用滚动位置**设一个 CSS 变量或触发一次状态切换**，让合成器去插值，而不是每帧读滚动位置重画 canvas。

### 7.4 OffscreenCanvas 与 Worker rAF

| 特性 | Safari 支持起始版本 |
|---|---|
| `OffscreenCanvas`（2D 上下文） | Safari **16.4** 起常见引用；Safari 17 起完整 |
| Web Worker 内的 `requestAnimationFrame` | Safari / iOS **16.4**（2023 年 3 月） |

依据：caniuse 的 `offscreencanvas` 与 `wf-request-animation-frame-workers` 条目，以及 MDN 的 `DedicatedWorkerGlobalScope.requestAnimationFrame`。

**意思就是**：如果你的目标包含 iOS 16.3 及更早，canvas-in-Worker 这条路走不通，必须回退到主线程渲染。建议做成**渐进增强**：

```js
const supportsOffscreen = typeof OffscreenCanvas !== 'undefined'
  && typeof Worker !== 'undefined'
  && 'transferControlToOffscreen' in HTMLCanvasElement.prototype;

if (supportsOffscreen) {
  startWorkerRender();
} else {
  startMainThreadRender();     // 降级：减少粒子数、降低分辨率
}
```

**回退路径要提前设计**，别等用户反馈才补——因为回退时的性能预算和主路径完全不同。

### 7.5 120Hz ProMotion：默认拿不到

这是最容易误解的一条：

- 【文档】iPhone 的 ProMotion 屏幕面板是 120Hz，但 **Safari 默认把页面渲染更新钳制在接近 60fps**，通过实验特性「Prefer Page Rendering Updates near 60fps」（默认开启）实现。
- 【文档】关掉这个 flag 理论上能解锁 120Hz，但在 iPhone Pro 上这条路直到 **iOS 18** 才修好（WebKit bug 272165，约 iOS 18.0 beta 2 修复）。iPad Pro 和 Mac 上的 ProMotion 更早就遵从了这个 flag。
- 【文档】即使关掉 flag，部分内容（尤其 PWA）仍停在 60fps。
- **滚动本身可以用 120Hz，但 JS 的 rAF 回调不一定。**

**实践结论**：不要假设 iOS 上能跑 120Hz，也不要为 120Hz 做 8ms 预算设计。**按 60Hz / 16.67ms 设计，在支持高刷的平台上当作额外余量。**

### 7.6 其他 iOS 注意事项

| 事项 | 说明 |
|---|---|
| canvas 硬件加速 | Safari 一直走 GPU 路径（CoreGraphics/Core Animation），但 `getImageData` 同样会造成回读代价 |
| `will-change` 的内存代价 | 移动端显存紧张，层的代价比桌面更严重。**绝对不要**在移动端批量提升层 |
| 上下文丢失 | iOS 在内存压力下会丢弃 WebGL 上下文（`webglcontextlost`），需要监听并重建。Canvas 2D 不会通知你，只会静默失败 |
| 低电量模式 | 可能降低刷新率或限制部分能力，测量要在正常模式和低电量模式下**各测一次** |
| `devicePixelRatio` | iOS 上常见 3（3×3 = 9 倍像素）。全屏 canvas 在 DPR=3 上是 1080×1920×9 的填充量，通常应该主动把 DPR 钳到 1.5–2 |
| 后台标签页 | rAF 暂停（与其他浏览器一致），但 iOS 上标签页被系统回收更激进，状态要能重建 |
| 页面可见性 | iOS 上切换 App 立即触发 `visibilitychange`，恢复时**必须重置时间基准**（见 3.5） |

### 7.7 iOS 适配的最小检查清单

写代码前先跑一遍这几条：

- [ ] 所有 canvas 面积 ≤ 16,777,216 像素（按 iOS 17 的严格值）
- [ ] 页面内 canvas 后备存储总量 ≤ 200 MB（给 384MB 留出余量）
- [ ] 所有离屏 canvas 用完主动 `width = height = 0`
- [ ] 变体表有按像素数计账的容量上限
- [ ] `devicePixelRatio` 有上限（建议 ≤ 2）
- [ ] 不做滚动联动的逐帧 JS 动画
- [ ] OffscreenCanvas 不可用时能降级运行
- [ ] 时间基准在 `visibilitychange` 时重置
- [ ] 在真实 iPhone 上测过（模拟器不复现填充率和内存限制）

---

## 8. 针对 glitch 效果的具体取舍

glitch art 的主流技法和它们的性能属性（结合本文前面的数字）：

| 技法 | 是否需要像素回读 | 建议实现 | 性能定位 |
|---|---|---|---|
| **切片位移 / 扫描线撕裂** | **不需要** | `drawImage(src, sx, sy, sw, sh, dx, dy, dw, dh)` 直接用源矩形错位 | 便宜，可每帧跑满屏 |
| **RGB 通道分离** | **不需要** | 用 `globalCompositeOperation = 'lighter'` + `filter` 或彩色叠层 | 便宜到中等 |
| **区块位移 / datamosh** | 不需要 | 同样用源矩形 + 偏移 | 便宜 |
| **镜像切片** | 不需要 | `ctx.scale(-1, 1)` + 源矩形 | 便宜 |
| **残影 / ghost echo** | 不需要 | 主画布上叠一层半透明自身副本（`globalAlpha` + `drawImage`） | 便宜，但有 overdraw |
| **抖动 / 半调（Bayer）** | 不需要（预处理） | 预渲染几张抖动图案，用 `globalCompositeOperation` 混合 | 便宜 |
| **正弦扭曲** | 不需要 | 逐列 `drawImage`（列数 = 调用次数），或用 CSS `filter` / SVG 位移 | 中等，受列数限制 |
| **噪点** | 不需要 | 预渲染 N 张噪声图循环 `drawImage`（别每帧生成） | 便宜 |
| **像素排序（pixel sorting）** | **需要** | 只在**小区域 + 低分辨率**缓冲上做 | **昂贵，必须限域** |
| **位深压缩 / posterize** | **需要** | 或改用 `filter: contrast()` + CSS 实现无需回读 | 昂贵 |
| **文字乱码 / zalgo** | 不需要 | DOM 层面处理，配合 `text-shadow` / 变换 | DOM 成本，注意 forced reflow |

**核心原则**：

1. **能用 `drawImage` 源矩形做到的，绝不走像素回读**。上表里 12 个技法有 10 个都能纯用绘制原语实现。
2. 必须走像素回读的（pixel sorting、posterize），**把处理面积压到全屏的 1/4 或更小**，或者**把处理帧率降到 15–20fps**（抖动类效果低频更新反而更「像 glitch」）。
3. 单帧内**只做一种重像素操作**，不要叠加。
4. 噪声/抖动这类静态图案，**预渲染 8–16 张循环播放**，成本接近零。

**性能预算示例**（1080p 全屏，60fps）：

```
纯 drawImage 切片位移 20 次      → 轻松 60fps
+ RGB 分离 3 次合成             → 仍然轻松
+ 半透明残影 1 次全屏叠加        → 注意 overdraw，约 3× 填充
+ 1/4 分辨率 pixel sorting      → 每帧约 31 MB 上传，可能吃紧
+ 全屏 pixel sorting（每帧）     → 498 MB/s 上传，移动端直接放弃
```

---

## 9. 参考链接

### 渲染管线与合成
- web.dev — Rendering performance（管线五阶段）
  https://web.dev/articles/rendering-performance
- web.dev — Stick to Compositor-Only Properties and Manage Layer Count
  https://web.dev/articles/stick-to-compositor-only-properties-and-manage-layer-count
- web.dev — Simplify paint complexity and reduce paint areas
  https://web.dev/articles/simplify-paint-complexity-and-reduce-paint-areas
- web.dev — Jank busting for better rendering performance（帧预算、rAF vs 定时器）
  https://web.dev/articles/speed-rendering

### 强制同步布局
- web.dev — Avoid large, complex layouts and layout thrashing
  https://web.dev/articles/avoid-large-complex-layouts-and-layout-thrashing
- Chrome for Developers — Forced reflow（性能洞察，建议阈值 30ms）
  https://developer.chrome.com/docs/performance/insights/forced-reflow
- Chrome for Developers — Analyze runtime performance（DevTools Performance 教程）
  https://developer.chrome.com/docs/devtools/performance

### Canvas 优化
- MDN — Optimizing canvas
  https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas
- web.dev — Improving HTML5 Canvas performance（预渲染、批处理、分层）
  https://web.dev/articles/canvas-performance
- Chrome for Developers — It's always been you, Canvas2D（willReadFrequently、性能改进）
  https://developer.chrome.com/blog/canvas2d
- Chrome for Developers — Taking advantage of GPU acceleration in the 2D canvas
  https://developer.chrome.com/blog/taking-advantage-of-gpu-acceleration-in-the-2d-canvas/
- web.dev — OffscreenCanvas 入门
  https://web.dev/articles/offscreen-canvas
- MDN — HTMLCanvasElement（尺寸上限说明）
  https://developer.mozilla.org/en-US/docs/Web/HTML/Element/canvas
- MDN — CanvasRenderingContext2D.getImageData()
  https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/getImageData

### 动画时间轴
- MDN — Window.requestAnimationFrame()
  https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame
- MDN — Anatomy of a video game（游戏循环）
  https://developer.mozilla.org/en-US/docs/Games/Anatomy
- Gaffer On Games — Fix Your Timestep!（固定步长 + 累加器 + 250ms clamp）
  https://gafferongames.com/post/fix_your_timestep/
- HTML 规范 — Animation frame callbacks
  https://html.spec.whatwg.org/multipage/imagebitmap-and-animations.html#dom-animationframeprovider-requestanimationframe

### 性能测量
- web.dev — Towards an animation smoothness metric（rAF 轮询的 7 项缺陷、Percent Dropped Frames）
  https://web.dev/articles/smoothness
- web.dev — Custom metrics（PerformanceObserver 用法）
  https://web.dev/articles/custom-metrics
- web.dev — Optimize long tasks
  https://web.dev/articles/optimize-long-tasks
- web.dev — Are long JavaScript tasks delaying your Time to Interactive?（50ms 阈值、RAIL）
  https://web.dev/articles/long-tasks-devtools
- Chrome for Developers — Long Animation Frames API（LoAF 字段与归因）
  https://developer.chrome.com/docs/web-platform/long-animation-frames
- MDN — PerformanceLongTaskTiming
  https://developer.mozilla.org/en-US/docs/Web/API/PerformanceLongTaskTiming
- Chrome for Developers — How to measure browser graphics performance（基准测试方法论）
  https://developer.chrome.com/blog/how-to-measure-browser-graphics-performance

### will-change 与层
- MDN — will-change CSS property（使用警告与最佳实践）
  https://developer.mozilla.org/en-US/docs/Web/CSS/will-change

### iOS Safari 限制
- WebKit Bugzilla 145998 — iOS canvas 面积上限 16777216
  https://bugs.webkit.org/show_bug.cgi?id=145998
- WebKit Bugzilla 271002 — iOS 18 提升到 8192×8192
  https://bugs.webkit.org/show_bug.cgi?id=271002
- WebKit Bugzilla 195325 — 画布内存总上限
  https://bugs.webkit.org/show_bug.cgi?id=195325
- WebKit Bugzilla 272165 — iPhone Pro 的 120Hz 渲染路径
  https://bugs.webkit.org/show_bug.cgi?id=272165
- WebKit Bugzilla 238616 — rAF 中的滚动位置问题
  https://bugs.webkit.org/show_bug.cgi?id=238616
- WebKit Bugzilla 187449 — 惯性滚动期间无法设置 scrollTop
  https://bugs.webkit.org/show_bug.cgi?id=187449
- PQINA — Canvas Area Exceeds The Maximum Limit
  https://pqina.nl/blog/canvas-area-exceeds-the-maximum-limit
- PQINA — Total Canvas Memory Use Exceeds The Maximum Limit（384MB、释放方法）
  https://pqina.nl/blog/total-canvas-memory-use-exceeds-the-maximum-limit
- caniuse — OffscreenCanvas
  https://caniuse.com/offscreencanvas
- caniuse — requestAnimationFrame in Web Workers
  https://caniuse.com/wf-request-animation-frame-workers
- MDN — DedicatedWorkerGlobalScope.requestAnimationFrame
  https://developer.mozilla.org/en-US/docs/Web/API/DedicatedWorkerGlobalScope/requestAnimationFrame

---

## 10. 一页速查

```
预算
  60Hz = 16.67ms   120Hz = 8.33ms   rAF 回调建议 < 15ms
  建议分配：JS 6ms / 绘制 4ms / DOM+合成 2ms / 留白 4ms

画布
  单层全屏 1080×1920 = 207 万像素，60fps = 1.244 亿像素/秒
  iOS ≤17 面积上限 16,777,216 px   iOS18 = 67,108,864 px
  iOS 页面总画布内存 ≈ 224MB（老）/ 384MB（iOS15+）
  全屏 putImageData = 498 MB/s 上传带宽 → 别做

drawImage
  整数坐标 / 不缩放 / 紧贴的离屏画布 / alpha:false
  禁用：shadowBlur、每帧 fillText、每帧改 canvas.width

强制布局
  offset* / client* / scroll* / getBoundingClientRect / getComputedStyle
  干净布局读是 <0.1ms，dirty 时强制整棵重排
  读-写分离 → 100 次布局变 1 次
  单次强制重排不应 > 30ms

时间轴
  纯视觉：progress = (ts - start) / duration
  物理：固定 DT + 累加器 + clamp(250ms)
  绝不 x += speed；绝不用 setTimeout(16) 驱动动画
  visibilitychange 时重置 lastTime 和 accumulator

合成
  只有 transform / opacity 能跳过 layout + paint
  移动元素要提升层，但每层要显存 → 用脚本开关 will-change，用完摘掉
  滚动/过渡期间合成目标 4–5ms

测量
  唯一可信判据：gap > 1.5 × 刷新间隔 = 丢帧
  看 Average / Worst / P95 Percent Dropped，不看平均 FPS
  LoAF 做归因，Frame Rendering Stats 做现场观察
  rAF 轮询看不到纯合成器动画 → 只能当辅助
```

---

*最后更新：基于上述引用来源整理。标注为「经验区间」的数字需在本项目目标设备上实测替换。*
