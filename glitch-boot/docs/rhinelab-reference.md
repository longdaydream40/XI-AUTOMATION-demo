# RhineLabUI 白底开场动画：源码级拆解 + 其他工业风 boot sequence 与黑白故障艺术参考

> 调研时间：本机实际 clone 后逐文件阅读源码。
> 调研对象：`https://github.com/LBEILC/RhineLabUI`
> 本地副本：`/tmp/RhineLabUI`（`git clone --depth 1`）
> 提交：`12cc5e4013acb9408f753ff71de6b8492299b7c8`（2026-10-08 22:52:38 +0800，`Merge pull request #17: add experimental gamepad support with input fixes`）
> 规模：`src/` 共 14061 行（其中 `.ts` 10254 行）；仓库 242 MB（含 `verification/` 截图与 `reference/` 帧提取工具）
> 许可：`package.json` 声明 `"license": "MIT"`；**但使用的 Novecento 字体不随 MIT 转让**（见 1.9）

**可信度声明（先说清楚，免得你拿去当证据用）**

- 下面所有代码片段都是从 `/tmp/RhineLabUI` 里**原样摘出来的**，没有改写、没有补全。
- 我**没有**跑起来这个项目（需要 `npm ci` + 模型资源），所以「代码怎么写」我能保证，「跑起来什么手感」我不能保证。
- 仓库里 `verification/*.md` 有一段自述：轨迹是「逐帧目测 + 测量脚本拟合」，作者自己明确写了「不声称拿到了原视频工程中的原始动画曲线」。这句话很重要——它的数值**长得像真数据但不是真数据**，抄的时候要知道这一点。
- 第 2、3 部分的外部链接我都发过 HTTP 请求验证可达（Codrops 与 CodePen 返回 403 是反爬，不代表链接失效，其内容来自搜索引擎抓取结果）。

---

## 1. RhineLabUI 的「白底开场」是怎么做出来的

**摘录规则（先说清楚，后面不再重复）**：以下代码块均为**逐字摘录**，字符串/标识符/数值未做任何改动。为控制篇幅，我允许了两类纯格式变化：① 原码中被 Prettier 拆成多行的调用，我合并回单行（因此可能少一个尾逗号）；② 长数组/关键帧表按原值重新换行排列。含 `...` 或「（已截断）」标记的地方是**真省略**。我已用脚本把全文所有 RhineLabUI 数字序列与源码逐串校对过，**数值无一处偏差**。

### 1.0 一句话结论

它**不是**视频，**也不是**纯 CSS 动画。它是一个 **DOM + SVG 的手写重播器**：

- 一条**纯函数时间轴** `bootMotion(appTime) → 一帧所有属性的数值快照`（无状态、可任意跳帧、可倒放）；
- 一个**纯写入器** `BootSequence.update(time)`，把快照逐个塞进 DOM/SVG 属性；
- 所有关键帧数值**以原片 25fps 的帧号为索引**，用一张手写的表 + 单调三次插值驱动。

这套结构的价值在于：**拖动进度条、倒放、跳帧、减少动效降级，全是免费拿到的能力**。这是这个项目最值得抄的部分，比它的视觉更值得抄。

---

### 1.1 架构：三层分离

| 层 | 文件 | 职责 |
| --- | --- | --- |
| 时间轴（纯计算） | `src/boot-motion.ts`（140 行） | 输入 `appTime`，输出一帧的完整数值快照 |
| 曲线/关键帧表 | `src/boot-tracks.ts`、`boot-logo-tracks.ts`、`boot-orbit-tracks.ts` | 存测量出来的关键帧，提供插值器 |
| 写入器（纯输出） | `src/boot.ts`（274 行 `BootSequence` 类） | 把快照写进 DOM/SVG 的 `style`、`d`、`transform` |
| 逐字排版 | `src/boot-lettering.ts` + `boot-lettering-art.json` | 字符级字形拼装与逐字显隐 |
| 循环驱动 | `src/main.ts` `bootFrame()` | 每帧 `rAF` 调用，同时驱动音频与后续三维舞台 |

`main.ts` 里的驱动极短（`src/main.ts:1217` 起）：

```ts
  audio.updateBoot(t, frozenTime !== null);
  const motion = bootSequence.update(t);
```

注意这两行的顺序：**音频先、视觉后，两者读同一个 `t`**。这就是它音画同步的全部秘密——不是音频去追动画，而是两者都从同一个时间源派生。

---

### 1.2 时间轴组织方式

#### (1) 时间基准：appTime 0 = 原片第 5 秒，单位是帧不是秒

`src/boot-motion.ts:1-2` 的原文注释：

```ts
// Original footage is 25 fps. App time zero corresponds to video time 5 s.
// Discrete editorial cuts use frame numbers; spatial motion uses continuous time.
```

```ts
export function bootMotion(appTime: number) {
  const t = appTime + 5;
  const f = Math.floor(t * 25 + 0.00001);
```

`+0.00001` 是浮点防抖——避免 `25 × 恰好整数秒` 掉到前一帧。

**白底起点怎么来的**：`src/main.ts` 里 `completeStartup()` 直接把播放起点设成 `1.76`（appTime），于是 `t = 6.76`，即原片 6.76 秒那张白场：

```ts
  const fade = motionActive("boot") ? 600 : 0;
  bootStart =
    performance.now() / 1000 -
    (reviewParams.has("time") ? Number(reviewParams.get("time")) : 1.76);
  if (!reviewParams.has("time")) bootStart += fade / 1000;
```

`+ fade/1000` 是等 600ms 的加载遮罩淡出再开始打字；文档里对应那句「首次播放延后 600ms，以便加载遮罩完全淡出后再输入第一个字」。

#### (2) 阶段机（step）：五个阶段用时间阈值硬切

```ts
  const step =
    t < 9.12
      ? "access"
      : t < 11.12
        ? "logo"
        : t < 19.48
          ? "auth"
          : t < 22.76
            ? "scan"
            : "welcome";
```

这个 `step` 会写进 DOM（`this.stage.dataset.bootFrame = String(s.f)` / `$("#stage").dataset.boot = step`），然后由 CSS 属性选择器接管一些「整段级」的显隐，例如 `src/style.css`：

```css
[data-boot="access"] .brand,
[data-boot="access"] .powered,
[data-boot="logo"] .brand,
[data-boot="logo"] .powered {
  opacity: 0;
}
[data-boot="scan"] .scan {
  opacity: 1;
  transform: scale(1);
}
```

**为什么要这个 step？** 因为纯数值驱动的代价是「每帧都要算」。阶段级的东西（某个元素整段亮着）用 CSS 一次性切完，比每帧写 `style.opacity` 更省。这是「连续量进 JS、离散量进 CSS」的分工。

#### (3) 三种时间曲线，各管一类属性

**A. 连续缓动——只用于「开始/结束本身就是设计意图」的地方：**

```ts
export const progress = (t: number, a: number, b: number) =>
  Math.max(0, Math.min(1, (t - a) / (b - a)));
export const smooth = (p: number) => p * p * (3 - 2 * p);
```

用得很抠门，全程只有几处，例如退场与白场：

```ts
  // 函数体里先算一次，供多个属性派生
  const exit = smooth(progress(t, 26.56, 26.92));
```
```ts
    // 返回对象里直接算的
    white: smooth(progress(t, 26.16, 26.88)),
```

**B. 离散帧号命中——用于「原片就是硬切」的地方：**

```ts
const at = (f: number, frames: number[]) => frames.includes(f);
```

**C. 单调三次 Hermite 插值（`track()`）——用于所有测量出来的空间运动。** 这是整个项目的技术核心，`src/boot-tracks.ts:5` 起：

```ts
export function track(keys: readonly Key[], frame: number): number {
  if (frame <= keys[0][0]) return keys[0][1];
  const last = keys.length - 1;
  if (frame >= keys[last][0]) return keys[last][1];
  const slope = (i: number) =>
    (keys[i + 1][1] - keys[i][1]) / (keys[i + 1][0] - keys[i][0]);
  const tangent = (i: number) => {
    if (i === 0) return slope(0);
    if (i === last) return slope(last - 1);
    const a = slope(i - 1),
      b = slope(i);
    if (a * b <= 0) return 0;
    const h0 = keys[i][0] - keys[i - 1][0],
      h1 = keys[i + 1][0] - keys[i][0];
    const w0 = 2 * h1 + h0,
      w1 = h1 + 2 * h0;
    return (w0 + w1) / (w0 / a + w1 / b);
  };
  let i = 0;
  while (frame > keys[i + 1][0]) i++;
  const h = keys[i + 1][0] - keys[i][0],
    p = (frame - keys[i][0]) / h;
  return (
    (2 * p ** 3 - 3 * p ** 2 + 1) * keys[i][1] +
    (p ** 3 - 2 * p ** 2 + p) * h * tangent(i) +
    (-2 * p ** 3 + 3 * p ** 2) * keys[i + 1][1] +
    (p ** 3 - p ** 2) * h * tangent(i + 1)
  );
}
```

**这个函数的选择是整个项目的精髓**，文件顶部的注释写得很清楚：

```ts
// Monotone cubic interpolation preserves measured speeds between source frames;
// unlike easing each interval separately, it does not stop at every keyframe.
```

翻译一下：如果用 `easeInOut` 分段缓动，**每到一个关键帧速度就归零**，动画会「一顿一顿的」。而原片是从视频里量出来的，速度是连续的。用 Fritsch–Carlson 单调 Hermite（`a * b <= 0 → tangent = 0` 那段就是防过冲的单调性修正），速度自然连续，还不会在极值点抖出去。

**证据链有多硬？** 关键帧表密到离谱。举 `boot-tracks.ts` 里权限圆环的半径轨迹：

```ts
    radius: value([
      [487, 2000],
      [492, 1540],
      [497, 1095],
      [500, 895.5],
      [505, 650],
      [510, 492],
      [515, 385.5],
      [520, 320.5],
      [524, 287.5],
      [527, 275],
      [530, 270],
      [535, 265.5],
      [540, 262],
      [545, 258],
      [550, 255],
      [555, 252.5],
      [560, 250],
      [568, 246],
    ]),
```

半径从 2000 收到 246 px，每 5 帧一个测量点，连 `895.5` / `287.5` 这种半像素都留着——这是脚本从 1920×1080 视频里量出来的（`reference/measure-boot.py`、`measure-scan-detail.py`、`measure-boot-logo.py`），不是手搓的。

#### (4) 加分项：逆向恢复天然成立

因为 `bootMotion` 是**纯函数**、`update()` 是**幂等写入**（每帧重新设置全部属性，不依赖上一帧状态），所以：

- 往前拖、往回拖、随机跳，画面都对；
- 项目自带的回归检查里有「507 帧正反序一致性」「跨阶段倒退」「倒退恢复」这几项。

对比一下常见写法（`setTimeout` 链 + 类切换动画）：拖回去必然错乱。**要做可交互的 boot 动画，必须走这条纯函数路线。**

---

### 1.3 逐字输入：三种不同的做法，三种不同的目的

这是这个项目最有教育意义的地方——它**没有**用统一的打字机组件，而是根据「原片当时是什么节奏」选了三种不同实现。

#### (1) ACCESS 行：硬编码「每帧显示几个字」

`src/boot-motion.ts:20`：

```ts
const accessCounts = [
  1, 1, 3, 4, 5, 6, 9, 11, 12, 14, 17, 18, 19, 20, 22, 23, 25, 26,
];
```

然后：

```ts
    access: "ACCESS PERMISSION REQUIRED".slice(
      0,
      f < 170 ? 0 : accessCounts[Math.min(17, f - 170)],
    ),
    accessOpacity: f >= 170 && f < 227 ? (f === 226 ? 0.25 : 1) : 0,
```

**关键在 `[1, 1, 3, 4, ...]` 这个数组**：它不是等速的。第 170 帧只出 1 个字，171 帧还是 1 个（**停一帧**），然后突然跳到 3 个、4 个、5 个、6 个，接着又跳到 9 个、11 个……

这是在复刻原片里那种**「机器解析信号」式的不均匀吐字**：开头卡一下，然后成块地涌出来。而不是人类打字的匀速。

那一帧的「停」很重要。全部匀速输出会立刻变成「打字机特效」，一帧的停顿立刻变成「设备在识别」。

注意还带了 `f === 226 ? 0.25 : 0` —— 第 226 帧单独掉到 25% 透明度，这是原片的**“文字变淡”那一帧**，下一帧才清空。

#### (2) 身份验证行：参数化线性逐字

```ts
const typed = (text: string, f: number, start: number, end: number) =>
  text.slice(
    0,
    f < start
      ? 0
      : Math.min(
          text.length,
          1 + Math.floor(((f - start) * (text.length - 1)) / (end - start)),
        ),
  );
```

**注意 `1 +`**：起始帧立刻出第 1 个字符，不是从 0 开始。这个 `1 +` 在视觉上区分「一帧没字」和「刚打了一个字」，很细但有用。

用处：

```ts
    logoLetters: typed("RHINE·LAB", f, 232, 255),
```

```ts
  if (f < 363) {
    auth = typed("ID CONFIRMED", f, 282, 295);
    if (f >= 320) auth += " : " + typed("JOYCE MOORE", f, 321, 339);
  } else if (f < 421) auth = typed("REQUEST RECEIVED", f, 367, 389);
  else {
    auth = typed("START PROCESSING", f, 423, 440);
    if (f >= 449)
      auth += ".".repeat(Math.min(3, 1 + Math.floor((f - 449) / 4)));
    if (at(f, [479, 485, 486])) auth = "              SING...";
  }
```

三个细节值得单独拿出来：

- **分段拼接**：`ID CONFIRMED` 打完（第 295 帧）之后**停了 25 帧**，第 320 帧才开始补 ` : JOYCE MOORE`。这不是「打完名字」，是「先确认身份，再补姓名」——叙事节奏靠帧号间隙做出来的。
- **省略号用 4 帧一个点**：`Math.floor((f - 449) / 4)`，比逐帧密集可信得多。
- **故障缺字是硬编码的**：`if (at(f, [479, 485, 486])) auth = "              SING...";` —— 三帧里把整行替换成带 14 个空格的 `SING...`。**这是复刻原片的一次信号丢失**，不是 bug。他们把它当成编排的一部分写死进了时间轴。

#### (3) 字形级逐字：`BootLettering` + 预生成的 SVG 字形图

这是最重的一层。`src/boot-lettering.ts` 不给文字，而是**按字符建格子**，每个格子塞一个 SVG path：

```ts
      const letters = art.letters.map((letter) => {
        const cell = document.createElement("span");
        cell.className = "boot-phrase-letter";
        cell.style.width = `${letter.width}em`;
        if (letter.path) {
          const svg = document.createElementNS(ns, "svg");
          svg.classList.add("boot-letter-art");
          svg.setAttribute("viewBox", `0 0 ${letter.width * art.units} ${art.units}`);
          svg.setAttribute("focusable", "false");
          const path = document.createElementNS(ns, "path");
          path.setAttribute("d", letter.path);
          svg.append(path);
          cell.append(svg);
        }
        node.append(cell);
        return cell;
      });
```

数据来自 `src/boot-lettering-art.json`（29,697 字节）。真实开头（**已截断**，只保留第一个字母 A）：

```json
{"access":{"text":"ACCESS PERMISSION REQUIRED","weight":"Normal","units":1000,"letters":[{"width":0.732,"path":"M543 614.0 621 800.0H708L410 100.0H321L23 800.0H110L188 614.0ZM512 540.0H219L296 356.0C322 293.0 363 194.0 364 193.0H366C367 194.0 408 293.0 435 357.0Z"},{...
```

**为什么要这样做？** 因为要复刻的字型是 Novecento Sans Wide，是商业字体。他们的处理方式是（`verification/BOOT-LETTERING.md` 原文）：

> 根据两个来源许可中将字母作为轮廓图形导入的条款，项目仅发行十段预先制作的固定文字图形，不嵌入 OTF 或 Webfont。

也就是说：**用有授权的字体制成轮廓图形，只发行图形段落，不发行字体文件。** 每个字符带自己的 `width`（单位 em），拼起来就是排版。

然后显隐逻辑极简，且**只改变化的那部分**：

```ts
  setText(value: string) {
    if (this.value === value) return;
    this.value = value;
    this.label.textContent = value;
    const active = value ? this.phrases.find((p) => p.text.startsWith(value)) : undefined;
    this.host.classList.toggle("boot-lettering-fallback", Boolean(value && !active));
    for (const phrase of this.phrases) {
      const visible = phrase === active;
      if (phrase.node.hidden === visible) phrase.node.hidden = !visible;
      if (!visible) continue;
      phrase.letters.forEach((letter, i) => {
        const hidden = i >= value.length;
        if (letter.hidden !== hidden) letter.hidden = hidden;
      });
    }
  }
```

`if (this.value === value) return;` 和 `if (letter.hidden !== hidden)` 这两个早退是**性能关键**。原文注释在 `boot.ts`：

```ts
    // Preserve the SVG text node once each revealed letter is in place. Replacing
    // it every frame invalidates glyph rasterization under the moving HUD.
```

**坑记录**：他们最初每帧无条件 `textContent = ...`，结果在 HUD 变换下 650ms 内产生 20 次节点替换、字形闪动。改成「只在内容变化时赋值」后，同一时段替换次数为 0。

还有一个更隐蔽的坑，构造函数里的注释：

```ts
    // Bind after collecting the original ring paths. Phrase artwork also has
    // SVG paths, and must never be included in the scan's animated geometry.
```

**文字图形也是 `<path>`，扫描圆环选择器 `".scan path"` 会误抓文字路径。** 所以必须先收圆环路径、再绑定文字。这类「同一选择器命中两种语义元素」的坑，任何 DOM+SVG 混排的 boot 动画都会踩。

#### (4) 打字音与逐字严格同源

`src/typing-rhythm.ts` 全文逻辑只有一件事：**反推出「哪一帧新增了可见字符」**。

```ts
export const TYPING_FRAMES: readonly number[] = [
  [170, 187],
  [282, 295],
  [320, 339],
  [367, 389],
  [423, 440],
  [449, 457],
].flatMap(([start, end]) => {
  const frames: number[] = [];
  let previous = 0;
  for (let frame = start; frame <= end; frame++) {
    const motion = bootMotion(frame / 25 - 5);
    const text = frame < 200 ? motion.access : motion.auth;
    const count = text.replace(/\s/g, "").length;
    if (count > previous) frames.push(frame);
    previous = count;
  }
  return frames;
});

export function hasTypingBetween(previousVideoTime: number, videoTime: number) {
  return TYPING_FRAMES.some(
    (frame) =>
      frame / 25 > previousVideoTime + 1e-6 && frame / 25 <= videoTime + 1e-6,
  );
}
```

看它在干什么：**它调用 `bootMotion()` 本身来推算打字时刻**。因为时间轴是纯函数，音频模块可以「问」视觉模块「这一帧你会不会多出一个字」。

音频侧 `src/audio.ts:642` 只有一行：

```ts
    if (hasTypingBetween(previous, time)) this.play("key");
```

**每帧最多一次按键音，且必然发生在有字出现的那一帧。** 没有独立计时器、没有 `setInterval`、没有漂移。这是单时间源架构送的第二份红利。

（注释里还有一句：`Glitch restoration at frames 479/485/486 is not new typing.` —— 故障帧不触发按键音。这种细节说明他们是拿原片音频反推的。）

---

### 1.4 Logo 绘制技术：一条闭合路径 + `pathLength=1` + dash 窗口

原片里的莱茵生命标志是**一笔连续画完的**（带弧线、交叉、末尾缺口）。实现方式：

#### (1) 把三段断笔画合并成一条闭合贝塞尔轮廓

`src/brand.ts:7`：

```ts
export const bootMarkContour =
  "M295 73C295 41 273 15 240 15C221 15 207 23 192 38C186 43 181 47 176 52C127 96 103 128 70 128C38 128 15 101 15 70C15 39 37 15 70 15C103 15 127 48 156 75C182 99 208 128 240 128C273 128 295 105 295 73Z";
```

末尾 `Z` 闭合。两个圆环部分各用两段三次贝塞尔（`C295 41 273 15 240 15` 等）拼出来，中间靠 `176 52 → 70 128` 那段的切线过渡。

`boot.ts` 里注入并归一化长度：

```ts
    this.contour.setAttribute("d", bootMarkContour);
    this.contour.setAttribute("pathLength", "1");
```

**`pathLength="1"` 是整段技巧的支点。** 它把整条路径的「长度」重新定义成 1，于是 dash 参数直接变成 0~1 的比例，不用去调 `getTotalLength()`，也不受缩放影响。

#### (2) 用 dash 窗口表示「笔画头尾各自独立移动」

```ts
    this.contour.style.strokeDasharray = `${s.logo.length} ${1 - s.logo.length}`;
    this.contour.style.strokeDashoffset = String(-s.logo.start);
    this.contour.setAttribute("stroke-width", String(s.logo.strokeWidth));
```

`dasharray = [可见长度, 剩余长度]`；`dashoffset = -start` 把可见窗口沿路径前移。于是：

- **起点 `start` 动 = 笔画尾巴在动**
- **长度 `length` 动 = 笔画头部在动**
- 两者独立 → 可以做出「笔尖往前冲，尾巴慢慢跟上来」的效果

这跟 Vivus（见 2.5）那些库的做法**不一样**：Vivus 是同步推进头尾（等效只动 length）；这里是**两个端点各自有轨迹**，所以能做「先加速拉开、然后尾巴追上」的细节。

#### (3) 关键帧表：全部按帧采出来

`src/boot-logo-tracks.ts` 开头（片段）：

```ts
// Position along the single shared contour, unwrapped across its closing point.
// These are the visible stroke's trailing/leading ends, not whole-logo opacity.
const draw = [
  [229, -0.02, -0.0198],
  [230, -0.0195, -0.011],
  [231, -0.016, 0.009],
  [232, -0.0095, 0.047],
  [233, 0.0025, 0.1135],
  [234, 0.0215, 0.2205],
  [235, 0.048, 0.365],
  [236, 0.0735, 0.504],
  [237, 0.094, 0.6155],
  [238, 0.109, 0.7045],
  [239, 0.122, 0.7755],
  [240, 0.133, 0.835],
  [241, 0.1425, 0.884],
  [242, 0.1505, 0.927],
  [243, 0.1575, 0.964],
  [244, 0.164, 0.996],
  [245, 0.1695, 1.023],
  [246, 0.1745, 1.0475],
  [247, 0.1785, 1.0685],
  [248, 0.183, 1.087],
  [249, 0.187, 1.103],
  [250, 0.19, 1.1175],
  [251, 0.1935, 1.13],
  ...
] as const;
```

两个观察：

1. **值超过 1**（比如 `1.1645`）——注释里的 `unwrapped across its closing point` 就是这个意思：**跨越闭合点时不回绕**，用超出 1 的连续数值表达「绕回开头继续画」。如果 mod 1，插值会瞬间从 1 跳到 0，笔画会闪。
2. **头尾差值随帧增长**：229 帧长度≈0，236 帧 `0.504 - 0.0735 = 0.43`，237 帧 `0.6155 - 0.094 = 0.52` —— 早期**尾巴追不上头**，笔画在「拉长」，这正是 `length` 单独增长的效果。

#### (4) 描边宽度也是从 0 长起来的

```ts
    strokeWidth: track(
      [
        [229, 0.25],
        [230, 2.8],
        [231, 8],
        [232, 16],
        [233, 23.5],
        [234, 26],
      ],
      frame,
    ),
```

6 帧内从 0.25 到 26。**不是「先有细线再变粗」，而是笔画一开始就是正在成形的。**

（`0.25` 而不是 `0` 是我**推断**的意图，源码未注释：SVG 里 `stroke-width: 0` 什么都不画，给个极小值可以让第 229 帧就存在一个亚像素的起点，而不是整段消失。）

#### (5) 加减号：加号先旋转落定，方点拉成横线

```ts
    plusX: track([[246, 155], [247, 123.3], [248, 104], [249, 93.53], [250, 86.52], [251, 81.78], [252, 78.48], [254, 74.26], [256, 72.96], [260, 72.6]], frame),
    minusX: track([[246, 155], [247, 186.82], [248, 206.14], [249, 216.66], [250, 223.47], [251, 228.21], [252, 231.77], [254, 236.06], [256, 237.57], [260, 237.1]], frame),
    minusWidth: track([[246, 15], [256, 15], [257, 23], [258, 31], [259, 35.5], [260, 38], [262, 42], [264, 44], [268, 46]], frame),
    plusAngle: track([[255, 0], [256, -3], [257, -22], [258, -45], [259, -62], [260, -70], [262, -80], [265, -87], [270, -90]], frame),
```

关键：**两个符号从同一个 x=155 出发**，第 246 帧开始分别向左（72.6）和向右（237.1）**展开**。加号还需要额外旋转 -90° 才「落正」。

写入端写在 `boot.ts`：

```ts
    this.plus.setAttribute(
      "transform",
      `translate(${s.logo.plusX} 70) rotate(${s.logo.plusAngle}) scale(${s.logo.symbolScale}) translate(-69 -70)`,
    );
    this.minus.setAttribute(
      "d",
      `M${-s.logo.minusWidth / 2} 0h${s.logo.minusWidth}`,
    );
    this.minus.setAttribute(
      "transform",
      `translate(${s.logo.minusX} 70) scale(${s.logo.symbolScale})`,
    );
```

注意加号那段 `translate(x 70) rotate(...) scale(...) translate(-69 -70)` —— **三段变换夹一个 `translate(-69 -70)` 是把它自己的旋转中心挪到符号中心**。SVG 没有 `transform-origin`（老实现里），所以只能用「先平移到原点 → 旋转 → 平移回去」的写法。

减号的 `d` **每帧重算**：`M${-w/2} 0h${w}`，从 15 拉到 46。所以「方点变横线」不是缩放，是**真的在改路径**。

#### (6) 绘制完成后：缺口沿轮廓移动

Logo 画完后（第 420 帧起）还有一段：印刷标志上原有的小缺口（打断笔画的那一段）会**沿着轮廓移动**。

```ts
const movingCut = [
  [420, 0.1835],
  [425, 0.184],
  [430, 0.1885],
  [435, 0.2],
  [440, 0.2205],
  [450, 0.2925],
  [455, 0.3485],
  [460, 0.421],
  [465, 0.5095],
  [470, 0.614],
  [475, 0.722],
  [480, 0.827],
  [485, 0.9195],
  [486, 0.9365],
] as const;
```

```ts
  const cut = track(movingCut, frame);
  const start = frame < 420 ? track(drawStart, frame) : cut + 0.0275;
  const end = frame < 420 ? track(drawEnd, frame) : cut + 1;
  return {
    offsetX: track(leftEdge, frame) - 520,
    start,
    length: Math.max(0, Math.min(1, end - start)),
    ...
```

**`cut + 0.0275` 和 `cut + 1`** —— 420 帧后「起点」变成「缺口位置 + 0.0275」，「终点」变成「缺口位置 + 1」。因为总长归一化成 1，`+1` 就是整圈。于是 dash 窗口变成 `[cut+0.0275, cut+1]`，**唯一不可见的部分就是那个 0.0275 宽的小窗口，且它在移动**。

用一组 dash 参数同时表达「画出来」和「缺口在跑」，很省。

#### (7) 落定：整块左移用另一条轨迹

```ts
const leftEdge = [
  [260, 814], [261, 813], [262, 812], [263, 808], [264, 803], [265, 794],
  [266, 781], [267, 763], [268, 740], [269, 716], [270, 691], [271, 668],
  ...
  [294, 518],
] as const;
```

```ts
    this.el(".boot-logo").style.transform = `translate(${s.logo.offsetX}px, 1px)`;
```

`offsetX = 轨迹值 - 520`。**用绝对测量值减去目标位置**，而不是写「移动了 296px」。好处是：如果以后改布局，只要改那个 520，轨迹不用动。

（顺带说明：`translate(..., 1px)` 那个 `1px` 是亚像素对齐微调，硬编码的。）

---

### 1.5 身份接入与权限验证：两条独立视觉线

#### (1) 身份接入（auth 阶段）

DOM（`src/main.ts` 内联模板）：

```html
    <div class="auth-status"><span>▪</span> <span id="auth-message"></span><i></i></div>
```

CSS（`src/style.css`）：

```css
.auth-status {
  position: absolute;
  left: 931px;
  top: 529px;
  font-size: 22px;
  display: flex;
  align-items: center;
  gap: 12px;
  white-space: nowrap;
  opacity: 0;
}
.auth-status > span:first-child {
  font-size: 14px;
}
.auth-status i {
  width: 3px;
  height: 22px;
  background: #282b26;
  animation: blink 0.8s steps(1) infinite;
}
```

三个视觉元素：一个 **▪ 方块（14px，比正文小）**、正文、**3×22px 的方块光标**。

**光标用 `steps(1)` 而不是线性闪烁**——`steps(1)` 是硬切，符合「数字信号」的语感；线性淡入淡出会显得软。

`[data-mode="boot"] .auth-status { animation: none; }` 与 `[data-mode="boot"] .auth-status i { display: none; }` —— 在某些模式下（比如它自己的对照页）**光标整个关掉**。

文本内容全部来自 1.3(2) 那三行状态机。

#### (2) 权限验证（scan 阶段）：圆环收拢

这是整段最复杂的一块。DOM 只有 6 条 `<path>` + 2 个橙色点 + 1 个中心点：

```html
    <div class="scan"><svg viewBox="0 0 1920 1080" aria-hidden="true"><g fill="none" stroke="#080a08" stroke-width="2" stroke-linecap="round"><path/><path stroke="#fff"/><path/><path/><path/><path/><circle class="orbit-dot" r="8" fill="#ed821b" stroke="none"/><circle class="orbit-dot" r="8" fill="#ed821b" stroke="none"/><circle class="scan-core" cx="960" cy="540" r="5" fill="#080a08" stroke="none"/></g></svg><span>PERMISSION AUTHORIZED</span></div>
```

**所有几何都是每帧重算的 `d`**，不是 CSS 动画。圆弧用一个小工具函数生成（`src/boot.ts:6`）：

```ts
const arc = (r: number, start: number, sweep: number, x = 960, y = 540) => {
  const point = (a: number) => `${x + Math.cos(a) * r},${y + Math.sin(a) * r}`;
  if (sweep >= Math.PI * 1.999)
    return `M${point(start)}A${r},${r} 0 1 1 ${point(start + Math.PI)}A${r},${r} 0 1 1 ${point(start + Math.PI * 2)}`;
  return `M${point(start)}A${r},${r} 0 ${sweep > Math.PI ? 1 : 0} 1 ${point(start + sweep)}`;
};
```

**为什么 `sweep >= 2π` 要特判成两段？** 因为 SVG 的 arc 命令**画不出完整圆**（`A` 两端点重合时按规范不画）。所以满圆必须拆成两个半圆。任何"要用弧段参数化圆"的人都会踩这个坑。

写入端：

```ts
    this.scanPaths[0].setAttribute("d", arc(r, scan.outerStart, scan.outerSweep));
    this.scanPaths[0].setAttribute("stroke-width", "2.4");
    this.scanPaths[1].setAttribute("d", arc(scan.whiteRadius, scan.whiteStart, scan.whiteSweep));
    this.scanPaths[1].setAttribute("stroke-width", "4");
    const inner = scan.innerStart;
    this.scanPaths[2].setAttribute("d", arc(scan.innerRadius, inner, scan.innerSweep));
    this.scanPaths[3].setAttribute("d", arc(scan.innerRadius, inner + Math.PI, scan.innerSweep));
    s.scanOrbit.sides.forEach((side, i) => {
      this.scanPaths[i + 4].setAttribute("d", arc(side.radius, side.start, side.sweep, side.x, side.y));
      this.scanPaths[i + 4].style.opacity = s.scanOrbit.sideVisible ? "1" : "0";
    });
```

**四条弧各自有独立的半径/起始角/弧长**：黑外环（2.4px）、白环（4px）、两条内弧（相位差 π，即同一个圆的对侧两段）。

轨迹全部在 `scanTrack()`：黑环、白环、内环各 3 条轨迹，加上轨道点角度/半径/点半径、两种弧端圆点半径。**加起来一个函数里 15 条关键帧表。**

`innerStart` 那条能看出用心程度——它在扫描期间**稳步正向旋转**：

```ts
    innerStart: rad * value([
      [487, -20], [490, -4.25], [492, 14], [495, 48.75], [497, 69.25], [500, 93.25],
      [505, 121.25], [510, 141], [515, 155.5], [520, 166.5], [527, 178], [530, 181],
      [535, 187.75], [540, 192], [545, 195.25], [550, 197.75], [555, 199.75],
      [560, 200.75], [568, 201.5],
    ]),
```

而 `innerSweep` 同时从 0 长到 136° —— **两条内弧一边转一边长**，最后停在 136°，不闭合。这就是「扫描中」而不是「扫完」的语感。

#### (3) 字距收束：`letterSpacing` 从 40px 收到 0

```ts
    scanTracking: track(
      [
        [487, 40], [492, 28], [497, 18], [500, 14], [505, 8], [510, 4],
        [515, 1.7], [520, 0.5], [527, 0], [568, 0],
      ],
      frame,
    ),
```

```ts
    this.el(".scan > span").style.letterSpacing = `${s.scanTracking}px`;
    this.el(".scan > span").style.setProperty("--boot-phrase-tracking", `${s.scanTracking}px`);
    this.el(".scan > span").style.fontSize = `${s.scanFont}px`;
```

**同一个值写两处**：一次给浏览器原生 `letter-spacing`，一次写进 CSS 变量 `--boot-phrase-tracking`。

为什么要写变量？因为 `PERMISSION AUTHORIZED` 是 `BootLettering` 渲染的——每个字符是一个独立 `<span class="boot-phrase-letter">`，字符间距由 CSS 控制（`src/boot-lettering.css`）：

```css
.boot-phrase-letter {
  position: relative;
  display: block;
  flex: 0 0 auto;
  height: 1em;
  margin-inline-end: var(--boot-phrase-tracking, 0px);
}
.boot-phrase-letter:last-child { margin-inline-end: 0; }
```

**逐字拆成绝对定位的 span 之后，原生 `letter-spacing` 对它们无效**，所以必须用 margin 模拟，并且必须由 JS 每帧同步。这是「字符级动画」必然要付的税：你会失去所有原生排版特性（字距、连字、kerning），得自己补。

同一个变量还负责修复字体差异：

```css
#auth-message { --boot-phrase-tracking: -0.00909em; }
.welcome-company { --boot-phrase-tracking: -0.5px; }
```

`-0.00909em` 这种值就是「换字体后字宽变了，用负 margin 挤回去」。

#### (4) 弧端圆点 + 橙色轨道点 + 中心点

**弧端圆点**（`caps`）——每条弧的两端各挂一个圆，半径随时间收缩到 0：

```ts
    this.caps.forEach((cap, i) => {
      const angle = i ? scan.whiteStart : scan.outerStart + scan.outerSweep;
      const radius = i ? scan.whiteRadius : r;
      cap.setAttribute("cx", String(960 + Math.cos(angle) * radius));
      cap.setAttribute("cy", String(540 + Math.sin(angle) * radius));
      cap.setAttribute("r", String(i ? scan.whiteCap : scan.blackCap));
    });
```

```ts
    blackCap: value([[487, 45], [504, 35], [510, 20], [515, 10], [520, 5], [525, 2.5], [535, 2], [550, 0], [568, 0]]),
    whiteCap: value([[487, 40], [492, 30], [497, 22], [502, 16], [507, 10], [512, 5], [520, 1.5], [540, 0], [568, 0]]),
```

**黑环端点从 45px 收到 0，白环从 40px 收到 0，但不同步**（黑环拖到 550 帧才归零，白环 540 帧）。用两个不同的衰减表做「两个环不是同一个物体」的错觉。

**橙色轨道点**（只有 2 个，相位差 π）：

```ts
    const orbit = scan.orbit;
    this.orbitDots.forEach((dot, i) => {
      dot.setAttribute("cx", String(960 + Math.cos(orbit + i * Math.PI) * scan.orbitRadius));
      dot.setAttribute("cy", String(540 + Math.sin(orbit + i * Math.PI) * scan.orbitRadius));
      dot.setAttribute("r", String(scan.dotRadius));
    });
```

```ts
    orbit: rad * value([[487, 70], [492, 33], [493, 13.2], [494, -5.8], [495, -24.2], [496, -41.4], [497, -57.2], [498, -71.4], [499, -84.2], [500, -96], [505, -140.8], [510, -172.3], [515, -195.5], [520, -213.5], [527, -234], [530, -238.8], [535, -247.7], [540, -254.7], [545, -260.1], [550, -264], [555, -266.9], [560, -268.8], [568, -270]]),
```

角度**负向**增长（70° → -270°），也就是逆时针；而且 492~500 帧每帧一个测量点，因为这里有「弧段开始分离」的加速。

**橙色是全片唯一的高饱和色**（`fill="#ed821b"`）。黑白底 + 一个橙色点，视觉重力全被它吃掉了。这是「黑白 + 单强调色」的经典用法。

**中心图形**（`scanOrbitTrack`）——这段最有意思，作者专门纠正过一次理解错误：

```ts
  const sourceFrame = Math.floor(frame + 0.00001);
  // Large core flashes are editorial cuts. The small core then grows gently
  // as six satellites appear in three-frame steps, with continuing orbit phase.
  const flash = [546, 547, 549, 550].includes(sourceFrame);
  const coreRadius = flash
    ? track([[546, 42.93], [550, 42.43]], frame)
    : track([[545, 0], [548, 7.96], [551, 9.89], [553, 10.63], [555, 11.08], [559, 11.45], [564, 11.45], [568, 11.27]], frame);
```

- **546/547/549/550 四帧是「闪变」**：中心点突然胀到 ~43px。因为它是硬切，所以不插值整段，只在两个关键帧之间算。
- 非闪变帧：中心点从 0 长到 11.45 然后回缩到 11.27（**结尾在缩**，这个是细节）。

```ts
    satellites: Array.from({ length: 6 }, (_, i) => {
      const phase = angle + (i * Math.PI) / 3;
      return {
        x: 959.5 + Math.cos(phase) * distance,
        y: 539.5 + Math.sin(phase) * distance,
        radius: track(dotGrowth, frame - 548 - i * 3),
      };
    }),
```

**六颗卫星点：`frame - 548 - i * 3`** —— 每颗点延迟 3 帧出现，共 18 帧错峰。半径用同一张 `dotGrowth` 表，只是起点不同。**这是「用一个函数 + 相位偏移」代替「六个独立动画」的写法。**

```ts
const dotGrowth = [
  [-1, 0], [0, 0.8], [1, 1.7], [2, 2.35], [3, 2.85], [4, 3.15],
  [5, 3.45], [7, 3.8], [10, 4.1], [15, 4.25], [20, 4.25],
] as const;
```

注意它**不是等速长起来的**（0.8, 0.9, 0.65, 0.5, 0.3, ...）——先快后慢，像电容充电。而且 `[-1, 0]` 这个负数键放在最前面，是为了让 `track()` 的边界判断在 `frame - 548 - i*3 < 0` 时直接返回 0。

另外两个写在文档里的重要修正（`verification/BOOT-MOTION.md`）：

> 原片中小圆不是绕大圆公转：551→568 帧，左圆心约从 (828,552) 到 (832,540)，右圆心约从 (1090,527) 到 (1087,539)，半径从约 38.3 降至 37.2 px；以稳定位置上的自转为主，只保留这段轻微收拢。

> 左弧顺时针、右弧逆时针，角度跨 360° 时展开为连续数值。

**「以为在公转，实际是自转」** —— 这条对做故障/仪表类动画很关键：**先量，再判断运动类型**。凭直觉猜「环在转」会做出完全不同的东西。

小圆的中心点也在缓慢收拢（每帧一个测量值）：

```ts
const sides = [
  [543, 827.5, 561, 1091, 518, 38.7, 260, 250, 0, 0],
  [544, 827.5, 561, 1091, 518, 38.7, 260, 250, 3, 3],
  ...
  [568, 831.61, 539.51, 1086.55, 539.48, 37.15, 599.44, -403.94, 332.25, 338.7],
] as const;
const columns = Array.from({ length: 9 }, (_, i) =>
  sides.map((row) => [row[0], row[i + 1]] as const),
);
```

**表是「每帧一行 × 9 列」的矩阵，然后用 `columns` 转置成 9 条关键帧表。** 这种「人类按帧读、代码按通道用」的中间表示很好用——量数据的时候按帧记最省事，用的时候按属性取最方便。转置只有两行代码。

注释还写了：`Angles are unwrapped: the left arc turns clockwise, the right arc counterclockwise.` 又是 **unwrapped（不回绕）**。

#### (5) 黑白闪切：四帧的完整参数

```ts
  const scanGlitch = at(f, [525, 526, 528, 529]);
```

```ts
    ringScale: scanGlitch ? 1.94 : 1,
    ringOpacity: scanGlitch ? 0.32 : track([[487, 0], [488, 0.18], [490, 0.6], [493, 1]], frame),
    ringBlur: scanGlitch ? 2.2 : 0,
```

```ts
    const group = this.scanPaths[0].parentElement!;
    group.setAttribute("transform", `translate(960 540) scale(${s.ringScale}) translate(-960 -540)`);
    group.style.opacity = String(s.ringOpacity);
    group.style.filter = `blur(${s.ringBlur}px)`;
```

**故障 = 三个属性同帧突变**：整组放大到 1.94×、透明度掉到 0.32、加 2.2px 模糊。零过渡、零缓动，一帧到位、一帧还原。

注意它是改 **`<g>` 的 `transform` 属性**而不是 CSS transform：`translate(960 540) scale(...) translate(-960 -540)` 又是「平移到中心 → 缩放 → 平移回去」。用属性而不是 CSS 的原因大概是：SVG 的 `transform` 属性不受 CSS 属性优先级/层叠影响，和每帧写的 `d` 是同一种「直接改属性」的路径，心智负担更低。

`blur()` 加在 `<g>` 上——**滤镜加在容器元素上比逐个 path 加便宜得多**（只一次合成）。故障帧只有 4 帧，成本可忽略；但如果要做持续抖动的故障，这里是第一个要优化的点。

---

### 1.6 欢迎转场

#### (1) DOM 结构（四层叠在一起）

```html
    <div class="welcome"><div class="welcome-panel"></div><div class="welcome-heading">WELCOME TO</div><div class="welcome-company"><strong>RHINE LAB.LLC.</strong><strong class="welcome-highlight" aria-hidden="true">RHINE LAB.LLC.</strong></div><div class="welcome-database">INTERNAL DATABASE</div><div class="welcome-logo">${logo}</div></div>
```

五个元素：黑底板、标题、公司名（**同样的文字两份**）、底部小字、标志。定位（`src/style.css`）：

```css
.welcome {
  left: 720px;
  top: 403px;
  width: 480px;
  height: 340px;
  transform-origin: 50% 44%;
  transition: none;
}
.welcome-heading {
  position: relative;
  z-index: 1;
  line-height: 65px;
  font-size: 55px;
  white-space: nowrap;
}
.welcome-panel {
  position: absolute;
  top: -59px;
  left: 5px;
  width: 470px;
  height: 392px;
  background: #080a08;
}
.welcome-company {
  position: absolute;
  top: 67px;
  left: 35px;
  width: 410px;
  height: 60px;
}
.welcome-company strong {
  display: block;
  position: absolute;
  inset: 0;
  padding: 5px 8px;
  background: transparent;
  color: #080a08;
  font-size: 48px;
  line-height: 50px;
  white-space: nowrap;
  letter-spacing: -0.5px;
}
.welcome-company .welcome-highlight {
  background: #080a08;
  color: #eeede8;
}
```

**公司名两份文字的机制**：两份 `<strong>` 用 `position: absolute; inset: 0` **完全重叠**，一份是「黑字无底」，另一份（`.welcome-highlight`）是「白字黑底」。然后对**第二份**做 `clip-path` 从左往右揭开：

```ts
    this.el(".welcome-highlight").style.clipPath =
      `inset(0 ${100 * (1 - s.highlight)}% 0 0)`;
```

于是视觉上就是**一块黑底从左往右扫过白色文字**。这就是 `verification/BOOT-MOTION.md` 里说的「黑底从左至右扫过名称」。

**为什么用两份文字而不是一份 + 动画背景宽度？** 因为两份重叠文本的**字形落点完全一致**（同一字体、同一定位），黑底边缘扫过时不会因为重排抖。用动画宽度的话，文字会被 background 的宽度变化影响（如果用了 padding/背景裁切）。

**参数化而非百分比**：`highlight` 是归一化 0~1，具体像素在轨迹里：

```ts
const highlightKeys: readonly Key[] = [
  [588, 4], [589, 39], [592, 225], [593, 261], [594, 288], [595, 310],
  [596, 328], [597, 343], [598, 356], [599, 366], [600, 375], [601, 382],
  [602, 389], [603, 394], [604, 398], [605, 402], [606, 405], [607, 407],
  [608, 408], [609, 409], [610, 410], [611, 410],
];
export const companyTrack = (frame: number) =>
  track(highlightKeys, frame) / 410;
```

`/ 410` 是归一化宽度（`--highlight: 100%` → `inset(0 0 0 0)`）。关键在**速度**：588→592 四帧内从 4 冲到 225（飞扫），596→611 用 15 帧才从 328 爬到 410（**长尾缓收**）。注释里那句就是这个意思：

```ts
// Frames 590–591 cut the layer out; its spatial trajectory keeps advancing.
```

#### (2) 七帧闪变序列表

```ts
  const welcomeIntro = [1, 0, 0.28, 0, 1, 0, 0];
  const flashIndex = f - 569;
```

```ts
    welcomePanel: flashIndex >= 0 && flashIndex < 7 ? welcomeIntro[flashIndex] : 0,
    welcomeInk: flashIndex >= 0 && flashIndex < 7 ? [0, 0, 0.2, 1, 0, 0, 0.25][flashIndex] : 1,
```

**`welcomePanel` 是黑底板的透明度，`welcomeInk` 是标题墨色在黑/白之间跳。** 两张 7 元素数组并排放在一起，一眼就能看出编舞：

| 相对帧 | panel（黑底板） | ink（标题） | 视觉 |
| --- | --- | --- | --- |
| 0 (569) | 1 | 0 | 全黑底 + 白字 |
| 1 (570) | 0 | 0 | **黑底消失**，白底白字 → 全白 |
| 2 (571) | 0.28 | 0.2 | 黑底半回，字微灰 |
| 3 (572) | 0 | 1 | 白底黑字 |
| 4 (573) | 1 | 0 | 黑底白字 |
| 5 (574) | 0 | 0 | 全白 |
| 6 (575) | 0 | 0.25 | 淡灰 |

背景色不是用 `color` 而是用 RGB 插值的 `rgb(...)` 写死：

```ts
    this.el(".welcome-heading").style.color =
      themeAmount > .0001 ? "var(--theme-ink)" : `rgb(${255 * (1 - s.welcomeInk)} ${255 * (1 - s.welcomeInk)} ${255 * (1 - s.welcomeInk)})`;
```

**这是一个「黑↔白反相闪切」，不是 RGB split，也不是抖动。** 对黑白配色项目来说这是最正统的故障语言：**信号极性反转**。它天然不引入颜色、天然高对比、天然符合"信号出了问题"的叙事。

`themeAmount > .0001 ? "var(--theme-ink)"` 是主题适配的兜底：如果用户切了配色主题，就用主题墨色而不是硬编码的黑白。

#### (3) 其他离散闪断

```ts
    companyVisible: f >= 588 && !at(f, [590, 591]),
    companyMask: at(f, [594, 595]),
    databaseOpacity: f < 626 || at(f, [628, 629, 631, 634]) ? 0 : 1,
```

```ts
    this.opacity(".welcome-company", s.companyVisible);
    this.el(".welcome-company").style.opacity = String(
      s.companyVisible ? (s.companyMask ? 0.65 : 1) : 0,
    );
    this.companyInk[1].querySelector("span")!.style.opacity = s.companyMask
      ? ".06"
      : "1";
```

- **590/591 两帧整块消失**（图层被切出去），但轨迹继续推进。
- **594/595 两帧是「灰闪」**：整块到 65% 透明，同时**第二份（黑底那份）文字压到 0.06** —— 也就是黑底几乎透明，露出下面的黑字。这就是「保留灰色遮罩、微弱反相文字及未扫过的文字」。
- **INTERNAL DATABASE 的 4 帧抖断**：628/629/631/634 四帧不连续（不是 628~631 连续四帧），这种「不规则的断续」比规律闪一下更像真实干扰。

#### (4) 退场：不是一个淡出，是五个参数一起动

```ts
  const exit = smooth(progress(t, 26.56, 26.92));
```

```ts
    welcomeScale: 1 - 0.46 * exit,
    welcomeOpacity: 1 - Math.pow(exit, 3),
    exitBlur: 8 * exit,
    exit,
    backgroundOpacity: t < 26.92 ? 1 : 0,
    white: smooth(progress(t, 26.16, 26.88)),
```

```ts
    this.el(".welcome").style.transform = `scale(${s.welcomeScale})`;
    this.el(".welcome").style.filter =
      `blur(${s.exitBlur}px) invert(${s.exit * 0.22}) sepia(${s.exit}) saturate(${1 + s.exit * 5}) hue-rotate(${s.exit * 115}deg)`;
```

拆开看：

- **缩小到 54%**（`1 - 0.46 × exit`），`transform-origin: 50% 44%` 偏上，所以是「往中心塌陷」不是原地缩。
- **透明度用 3 次方**（`1 - exit³`）：前段几乎不变，最后猛地掉。**退场不应该是匀速淡出。**
- **模糊 0→8px**：失焦。
- **一串 SVG/CSS filter 串联**：`invert(0.22) sepia(exit) saturate(1+5×exit) hue-rotate(115×exit)` —— 参数很小（invert 最多 22%、hue-rotate 最多 115°），**是「颜色漂移」不是「变成彩色」**。这段是唯一一处会引入颜色的地方，而且幅度被压得很低。
- **白场从 26.16 就开始涨，比 exit（26.56）早 10 帧**。所以顺序是：白场先起 → 内容再缩模糊 → 26.92 时黑底直接切掉（`backgroundOpacity: t < 26.92 ? 1 : 0`，硬切，没有过渡）。

**白场用 `smooth()` 而不是 `progress()`**：`smooth` 是 smoothstep，两端速度为零。**白场进出都要停得住，不能一帧到位**——这是唯一一处非硬切的转场，选择是对的。

#### (5) 糙点：CSS 与 JS 抢同一个属性

`.welcome` 在 CSS 里定义了：

```css
.welcome {
  ...
  transform-origin: 50% 44%;
  transition: none;
}
```

而 JS 每帧写 `style.transform = scale(...)`。同时基础样式里还有一段旧版遗留（`src/style.css` 靠前的定义）：

```css
.welcome {
  position: absolute;
  top: 403px;
  left: 0;
  width: 100%;
  text-align: center;
  font-size: 55px;
  font-weight: 700;
  line-height: 1.05;
  opacity: 0;
  transform: translateY(14px);
  transition:
    opacity 0.7s,
    transform 1s;
}
```

同一文件里 `.welcome` 被定义了两次，靠后定义（`left: 720px; top: 403px; ...; transition: none`）覆盖前者。`transition: none` 就是在**赌 JS 每帧写值能压住 CSS 过渡**——能用，但这是脆的：只要有人给 `.welcome` 加个 `transition: all`，整个动画会开始「缓动追缓动」，看起来像糊了一层。

**要抄这套的东西，第一条纪律就是：JS 每帧写的属性，CSS 里一律 `transition: none`。**

---

### 1.7 音频：三轨混音 + 事件表

```ts
export const BOOT_CUES: readonly { time: number; sound: Sound }[] = [
  { time: 9.16, sound: "brand" },
  { time: 11.84, sound: "confirm" },
  { time: 19.48, sound: "scan" },
  { time: 21.84, sound: "confirm" },
  { time: 22.76, sound: "welcome" },
  { time: 23.52, sound: "text-reveal" },
  { time: 25.04, sound: "text-reveal" },
  { time: 26.92, sound: "array" },
  { time: 30.68, sound: "open" },
  { time: 34.3, sound: "inspect" },
];
```

**每个 cue 的时间戳和视觉轨迹的关键帧是同一批数字**（9.16 = logo 阶段起点；19.48 = scan 起点；22.76 = welcome 起点；26.92 = 退出）。这是因为两边都从原片量出来的。

混音分四段：

```ts
    const phase = time < 22.76 ? 0 : time < 26.92 ? 1 : time < 34.3 ? 2 : 3;
    if (phase !== this.bootMix && this.context) {
      this.bootMix = phase;
      const gains = [
        [0.48, 0.32, 0.18],
        [0.68, 0.55, 0.32],
        [0.9, 0.72, 0.65],
        [0.72, 0.36, 0.12],
      ][phase];
      this.stemGains.forEach((g, i) =>
        rampLevel(g.gain, gains[i], this.context!.currentTime, 0.9),
      );
    }
```

**三轨 stem 在阶段切换时用 0.9 秒斜坡换增益**，而不是切歌。这是音乐制作里的「stem mixing」，用在开场里效果就是「氛围是连续演进的」。

跳帧保护：

```ts
    if (
      frozen ||
      previous === null ||
      time < previous ||
      time - previous > 0.3
    ) {
      this.stopEffects();
      return;
    }
```

**倒退（`time < previous`）和跳帧（`> 0.3s`）时不补播 cue，直接静默。** 这一点很关键——如果拖动进度条时把过去 20 秒的 cue 全补播出来，会变成噪音轰炸。

`if (type === "key") this.playedKeys++;` —— 有按键计数器，说明这个是被自动化测试验证过的（可以断言「一次播放里按了几次键」）。

---

### 1.8 降级与可访问性

- `reduce motion` 用户直接跳过整段（`if (!motionActive("boot")) setMode("archive")`，`setMode("archive")` 会 `bootSequence.reset()`）。
- `reset()` 是**真正的复位**，不是关掉：

```ts
  reset() {
    // Restore shared corner branding when skipping at any intermediate frame.
    [".brand", ".powered"].forEach((key) =>
      this.el(key).removeAttribute("style"),
    );
    this.brandLines.forEach((node) => node.removeAttribute("style"));
    this.el(".powered").innerHTML = this.poweredHTML;
    this.opacity("#boot-background", 0);
  }
```

**`this.poweredHTML` 在构造时就存下来了**（`this.poweredHTML = this.el(".powered").innerHTML;`）——因为 `powered` 那行会被 `BootLettering` 重建 DOM，跳过时得塞回原始 HTML。**「每帧改 DOM 的地方，都要留一条还原路径」**，这是硬性要求。

- 入口门（`StartupGate`）管三件事：等音频解锁、防重复点击、失败可降级。状态机 `"loading" | "waiting" | "starting" | "error" | "started"`。
- 关键细节：`aria-disabled` 而不是 `disabled`，注释写了原因：

```ts
    // aria-disabled preserves keyboard focus while repeated input is ignored.
    this.button.setAttribute("aria-disabled", "true");
```

**用 `disabled` 会丢焦点**，屏幕阅读器和键盘用户会掉出流程。这个坑值得记。

- 声音失败时给一条「关闭声音并进入」的路（`.entry-silent`），选了之后**保存偏好**（`prefs.sound = false; saveAudioPrefs();`），下次不再问。

---

### 1.9 字体与许可（法务上必须知道的一条）

`src/boot-lettering.ts` 顶部：

```ts
declare const __RHINE_NOVECENTO__: boolean;
const letterings = new Set<BootLettering>();

/** Only a locally installed, licensed kit enables native webfont rendering. */
export async function loadBootWebfonts() {
  if (!__RHINE_NOVECENTO__) return false;
  const faces = ["Normal", "DemiBold", "Bold"].map(weight => new FontFace(
    `Rhine Novecento ${weight}`,
    `url("${assetUrl(`fonts/novecento/webFonts/NovecentoSansWide${weight}/font.woff2`)}") format("woff2")`,
    { weight: "400", style: "normal", display: "swap" },
  ));
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      Promise.all(faces.map(face => face.load())),
      new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error("Novecento load timeout")), 8000); }),
    ]);
    faces.forEach(face => document.fonts.add(face));
    letterings.forEach(lettering => lettering.useWebfonts());
    return true;
  } catch (error) {
    console.warn("Novecento kit unavailable; retaining authored phrase graphics.", error);
    return false;
  } finally { clearTimeout(timeout); }
```

**这套设计（形状与字形来源分离）值得重点抄：**

1. 默认发行的是**图形**（`boot-lettering-art.json`），不是字体；
2. 检测到有授权的本地字体包（构建期变量 `__RHINE_NOVECENTO__`），**只换字形来源，保留格子宽度与时间轴**：

```ts
  useWebfonts() {
    // Retain the measured cells and the reveal timeline. Only the glyph source
    // changes: actual WOFF2 text replaces each pre-authored SVG drawing.
    for (const phrase of this.phrases) {
      phrase.node.style.setProperty("--boot-webfont-family", `"Rhine Novecento ${phrase.weight}"`);
      phrase.letters.forEach((letter, i) => {
        letter.replaceChildren();
        letter.dataset.letter = phrase.text[i];
        letter.classList.add("boot-font-letter");
      });
    }
    this.host.dataset.letteringRenderer = "webfont";
  }
```

3. 字体对上还有**基线补偿**（`boot-lettering.css`）：

```css
.boot-font-letter::before {
  content: attr(data-letter);
  position: absolute;
  left: 0;
  /* The official font's 1021/-179 metrics place its 1em line baseline at
     .921em. Move it to the same .8em baseline as the authored artwork. */
  top: -0.121em;
  ...
}
```

**`1021 / -179` 的 ascender/descender 让基线落在 0.921em，为了对齐图形版 0.8em 的基线，上移 0.121em。** 换字体必做的一步，靠 `vertical-align` 调不准，只能算。

`verification/BOOT-LETTERING.md` 里还有两份真实来源说明：Normal/DemiBold 来自 DaFont 免费包，Bold 来自 MyFonts 桌面包，字重选择用像素 MSE 拟合（DemiBold 0.03689 vs Bold 0.06343 → 选 DemiBold）。

**对你的 glitch-boot 项目的直接含义**：如果你要复刻某个商业字体的工业感，别直接把 woff2 塞进仓库。要么用开源替代（见第 3 部分），要么走「图形化 + 本地字体可选」这条路。

---

### 1.10 从 RhineLabUI 能直接搬走的 8 条工程经验

1. **时间轴是纯函数，写入器是幂等输出。** 输入时间、输出全部属性；不读上一帧、不存状态。换来跳帧/倒放/拖动/测试全部免费。
2. **关键帧用帧号索引，不用秒。** 视频参考素材是 25fps，帧号是整数、不累积浮点误差、和音频事件可以对得上。
3. **空间运动用单调三次 Hermite，不要分段缓动。** 后者每到一个关键帧速度归零，肉眼看得出来是「一顿一顿」。
4. **圆弧用「半径 + 起始角 + 弧长」三条独立轨迹参数化。** 而不是 dasharray 或者 `rotate`。这样才能做出「一边转一边长」「两个环不同步」。
5. **离散故障帧用「帧号白名单」硬切，不要做插值。** `at(f, [525, 526, 528, 529])` 比什么都清楚。
6. **文字和音频必须同源。** 音频模块去调时间轴函数算「这帧有没有新字」，而不是自己开计时器。
7. **每帧写 DOM 的地方都要（a）早退判断，（b）留还原路径。** 否则字形重栅格化闪动 + 跳过时状态残留。
8. **`pathLength="1"` + `strokeDasharray` 是 SVG 笔画绘制的最优解。** 不用 `getTotalLength()`、不受缩放影响、可以单独控制头尾。

---

## 2. 其他「科技感/工业风 boot sequence」开源实现与经典案例

按「能直接借鉴什么」排序。所有 URL 已实测可达。

### 2.1 TerminalTextEffects（TTE）— 终端文本特效引擎

- 仓库：https://github.com/ChrisBuilds/terminaltexteffects
- 文档/展厅：https://chrisbuilds.github.io/terminaltexteffects/
- PyPI：https://pypi.org/project/terminaltexteffects/
- 语言：Python；MIT；搜索结果标注 4287 stars（未复核）
- 本地用法：`cat your_text | tte decrypt --typing-speed 2 --ciphertext-colors 008000 00cb00 00ff00 --final-gradient-stops eda000 --final-gradient-steps 12 --final-gradient-direction vertical`

**可借鉴点（这是本清单里「故障语言词汇量」最丰富的一个）：**

内置 40 种效果，其中和 boot 动画直接相关的：

| 效果 | 说明 | 用途 |
| --- | --- | --- |
| `decrypt` | 电影式解密：密文字符逐个落定为明文 | 权限验证文字 |
| `vhstape` | 行左右抖 + 失去细节 | 故障帧 |
| `errorcorrect` | 字符先出现在错误位置，再逐个被纠正 | 「加载出错又自愈」 |
| `matrix` | 数字雨，末尾有落幕与字符解析阶段 | 背景 |
| `laseretch` | 激光逐字蚀刻 | Logo 出现的替代方案 |
| `synthgrid` | 网格填充字符，溶解成最终文字 | 转场 |
| `unstable` | 字符先乱，爆散到边缘再重组 | 「重启」式转场 |
| `burn` / `crumble` | 燃烧 / 崩解成尘再重组 | 关机 |
| `beams` | 光束扫过画布照亮字符 | 扫描线 |

**它的工程架构比效果本身更值得看：**

> All effects are iterators which return a string representing the current frame.

**效果 = 一个迭代器，每次 `next()` 吐出一帧字符串。** 这跟 RhineLabUI 的「纯函数时间轴」是同一个思路的两种实现（一个是拉取式迭代器、一个是无状态查表），都避免了「动画状态和渲染状态耦合」。

它还暴露了「Paths / Waypoints / 运动缓动，支持贝塞尔曲线」「Scene、图层、符号/颜色变化」——想在公司内做终端启动画面的话，直接 `pip install terminaltexteffects` 就能用。

**注意边界**：它是**终端字符串**渲染，不是像素或 DOM。你没法直接搬到网页里，能搬的是**效果的运动模型**。

---

### 2.2 Alien (1979) MU/TH/UR 6000 终端 — 工业风 boot sequence 的原型

这是**这个类型的最重要的历史参照**，两条理由：

1. **它的 boot 是「机器在自检」而不是「在打字」**：屏幕上是绿色字符块随机闪现、横条随机出现消失、然后才是成行文字。因为 1979 年的显示设备就是这样。
2. **它是「文本 + 随机字符块 + 横条」三层叠加**，不是单一文字流。这个结构至今仍是工业风 boot 动画的默认配方。

**有真实可运行的复刻作品：**

**(a) CodePen: Alien MU-TH-UR 6000 Computer UI**
- https://codepen.io/tkmoney/pen/qBoVGWy
- 源码镜像：https://gist.github.com/vforge/c35de355ea5d730df227209ae371eb92
- 技术栈：GSAP + SplitText + Web Audio

真实代码片段（来自 gist，`BootScreen` 类）：

```js
    this.bars_elm = [];
    for(var b = 0; b < this.num_bars; b++){
      let bar_elm = document.createElement('div');
      bar_elm.classList.add('bar_elm');
      this.bars_container.appendChild(bar_elm);
      let bar_glow = document.createElement('div');
      bar_glow.classList.add('bar_glow');
      bar_elm.appendChild(bar_glow);
      gsap.set(bar_elm,{
        background:'#80ff10',
        '--glow-opacity':0,
        width:"random(15,100)%",
        height:"random(1,2)%",
        position:'absolute',
        top:"random(0,100)%",
        left:"random(-25,75)%",
        opacity:0
      });
      gsap.set(bar_glow,{
        width:'100%',
        height:'100%',
        boxShadow:'0px 0px 5px #80ff10, 0px 0px 15px #80ff10, 0px 0px 20px #80ff10',
        opacity:'var(--glow-opacity)'
      })
```

**横条的三个关键设计：**

```js
    b_tl.set(bar_elm,{
      width:"random(15,100)%",
      height:"random(1,2)%",
      top:"random(0,100)%",
      left:"random(-25,75)%",
    })
    b_tl.to(bar_elm,{opacity:1,'--glow-opacity':1,delay:"random(0,2.5)",duration:0.05,ease:'expo.out'})
    b_tl.to(bar_elm,{opacity:0, '--glow-opacity':0,duration:"random(0.2,0.5)"})
```

1. **`left:"random(-25,75)%"` 允许负值** —— 横条会伸出画面外，看起来像"束流"而不是"贴纸"。
2. **`delay: random(0,2.5)` 每轮重新随机**（`repeatRefresh:true`），所以永远不会形成规律。
3. **升起 0.05s、落下 0.2~0.5s** —— **亮得快、暗得慢**，这是荧光/CRT 余辉的正确物理直觉。反过来就会像 LED 闪烁。

**随机字符屏的结构：**

```js
      for (var n = 0; n < this.line_sections; n++) {
        let sec = document.createElement("div");
        gsap.set(sec,{
          display:'inline-block',
          opacity:0,
          gridRow:1,
          fontSize:'2vh',
          justifySelf:gsap.utils.random(['start','end','center'])
        });
        ...
        sec.innerHTML = `<span class='char'>${char}</span>×8`;
        gsap.set([...sec.querySelectorAll('.char')].slice(0, gsap.utils.random(2,7)),{opacity:1});
```

也就是：**每行分 4 段，每段填同一个字符 8 遍，然后只让其中随机 2~7 个字符可见。** 结果是一段「断续的字符块」，而不是整齐的文字。**这是最省代码的「随机字符墙」实现，一秒就能抄。**

再加：

```js
    for(var ls = 0; ls < (this.line_section_elms.length/3); ls++){
      let lse = gsap.utils.random(this.line_section_elms);
      gsap.set(lse,{opacity:1});
    }
```

**只让 1/3 的段亮着**——密度控制。

**音频的处理方式（和 RhineLabUI 完全不同，也值得看）：**

```js
  detailsScreenAnimation(){
     let tl = gsap.timeline();
     this.details_screen.querySelectorAll('.detail_line').forEach(function(line_elm,index){
      tl.set(line_elm,{'--text-shadow-opacity':0});
      tl.fromTo(line_elm.querySelectorAll('.char'),{ opacity:0 },{
        opacity:1,
        stagger:0.01,
        duration:0.01,
        onComplete:function(){
          gsap.fromTo(line_elm,
            {'--text-shadow-opacity':1},
            { '--text-shadow-opacity':0, duration:1, ease:'expo.out' })
          if (this.detail_beep_sound) {
            let s = this.detail_beep_sound.clone();
            s.play();
            s.sourceNode.playbackRate.value = gsap.utils.random(0.9, 1.5);
          }
        }
      });
```

**三条可借鉴的：**

1. **`stagger:0.01, duration:0.01`** —— 每个字符 10ms，间隔 10ms。等于「一帧一个」。比任何 tick 都精确。
2. **字符出现后套一层辉光衰减**：用 CSS 变量 `--text-shadow-opacity` 从 1 到 0 用 `expo.out` 收 1 秒。**「字先亮一下再落到常态」** —— 这是屏幕字符的关键质感，只做透明度不做辉光的话会像贴纸。
3. **每个字符的音效用 `playbackRate = random(0.9, 1.5)` 变调**，避免听出是同一个采样。**这是打字音不烦人的唯一秘诀。**

另外它的命令序列本身就是一个「数据结构驱动的脚本」：

```js
 cmd_seq: [
 { type: "boot" },
 { type: "delay", t: 2 },
 { type: "clear" },
 { type: "line", copy: "INTERFACE 2037 READY FOR INQUIRY", has_underline: true },
 ...
```

**把 boot 内容抽成 `{type, copy, delay}` 数组**，然后顺序转成一条 GSAP timeline。这是纯文本终端 boot 最省事的写法。

**(b) 其他 MUTHUR 复刻**
- https://github.com/zero-ability/codevember-13-mu-th-ur-plus-audio —— 带 Alien 原片音效采样（`AlienScroll.wav` / `AlienWrite.wav` / `AlienNostromoStartup.mp3`）
- https://github.com/alexpritt/muthur6000 —— React 版，给跑团用的玩家界面
- https://jcar.github.io/muthur-terminal/ —— 网页版 MU-TH-UR 终端

**(c) 电影本身的分析参考资料（写设计文档时可以引用）**
- Typeset In The Future《Alien》专题：https://typesetinthefuture.com/2014/12/01/alien/ —— 有屏幕字体（City Light 光学拉伸）、CRT 显示的历史考证、"boot screen 上的船号"等具体细节
- NeoCities 上的 MU/TH/UR 条目：https://checkplease.neocities.org/couchto4k/p/mother-muthur-and-the-company —— 有一段很好的设计解读：「Company 的界面（那个白色小房间）是整艘船上唯一没有使用痕迹的空间」

**可借鉴点总结**：Alien 那套的价值在于**「随机的密度感」**——横条、字符块、成行文字三层各自的呼吸节奏不同。不要把所有东西对齐到同一个节拍上。

---

### 2.3 React Bits — Faulty Terminal（网页端 CRT 终端 shader，单色）

- 演示：https://reactbits.dev/backgrounds/faulty-terminal
- 文档：https://reactbits.dev/docs/components/faulty-terminal
- 仓库：https://github.com/DavidHDev/react-bits
- 技术栈：React + `ogl`（轻量 WebGL）+ GLSL 片元着色器
- 默认参数就是**单色终端**：`tint = '#ffffff'`、`scanlineIntensity = 0.3`、`curvature = 0.2`、`pageLoadAnimation = true`

**这是我找到的**最接近「黑白 + 故障」的现成网页实现**，而且是 shader 级的，全部参数可调。**

真实的 fragment shader 核心（来自其 README/shadcn 分发版）：

```glsl
float digit(vec2 p){
    vec2 grid = uGridMul * 15.0;
    vec2 s = floor(p * grid) / grid;
    p = p * grid;
    vec2 q, r;
    float intensity = pattern(s * 0.1, q, r) * 1.3 - 0.03;

    if(uUseMouse > 0.5){
        vec2 mouseWorld = uMouse * uScale;
        float distToMouse = distance(s, mouseWorld);
        float mouseInfluence = exp(-distToMouse * 8.0) * uMouseStrength * 10.0;
        intensity += mouseInfluence;
        float ripple = sin(distToMouse * 20.0 - iTime * 5.0) * 0.1 * mouseInfluence;
        intensity += ripple;
    }

    if(uUsePageLoadAnimation > 0.5){
        float cellRandom = fract(sin(dot(s, vec2(12.9898, 78.233))) * 43758.5453);
        float cellDelay = cellRandom * 0.8;
        float cellProgress = clamp((uPageLoadProgress - cellDelay) / 0.2, 0.0, 1.0);
        float fadeAlpha = smoothstep(0.0, 1.0, cellProgress);
        intensity *= fadeAlpha;
    }

    p = fract(p);
    p *= uDigitSize;
    ...
    float isOn = step(0.1, intensity - f);
    float brightness = isOn * (0.2 + y * 0.8) * (0.75 + x * 0.25);
    return step(0.0, p.x) * step(p.x, 1.0) * step(0.0, p.y) * step(p.y, 1.0) * brightness;
}
```

**`uUsePageLoadAnimation` 那 5 行是整个开源界最值得抄的「页面进场」技巧**，它是：

1. 给每个格子算一个稳定的伪随机数 `cellRandom`（用 `sin(dot(s, vec2(12.9898, 78.233))) * 43758.5453` 这个经典 hash）；
2. 把它映射成 0~0.8 的**每格延迟**；
3. 用全局进度 `uPageLoadProgress - cellDelay` 除以 0.2 得到每格进度；
4. `smoothstep(0,1,progress)` 做软边。

**结果：屏幕按随机顺序逐格亮起。** 不是整体淡入、不是扫过、不是抖——是「格子被逐个点亮」。这是非常有质感的进场，而且实现只有 5 行、零额外开销（在 shader 里）。

还有故障位移：

```glsl
vec3 getColor(vec2 p){
    float bar = step(mod(p.y + time * 20.0, 1.0), 0.2) * 0.4 + 1.0;
    bar *= uScanlineIntensity;
    float displacement = displace(p);
    p.x += displacement;

    if (uGlitchAmount != 1.0) {
      float extra = displacement * (uGlitchAmount - 1.0);
      p.x += extra;
    }

    float middle = digit(p);
    const float off = 0.002;
    float sum = digit(p + vec2(-off, -off)) + digit(p + vec2(0.0, -off)) + digit(p + vec2(off, -off)) +
                digit(p + vec2(-off, 0.0)) + digit(p + vec2(0.0, 0.0)) + digit(p + vec2(off, 0.0)) +
                digit(p + vec2(-off, off)) + digit(p + vec2(0.0, off)) + digit(p + vec2(off, off));
    vec3 baseColor = vec3(0.9) * middle + sum * 0.1 * vec3(1.0) * bar;
    return baseColor;
}
```

**`off = 0.002` 那 9 次采样是廉价 bloom**：中心 + 8 邻域按 0.9 : 0.1 混合，就是「字的辉光溢出到隔壁格子」。**不需要真的做后期 bloom。** 这是 shader 里最常用的省钱技巧。

色彩：

```glsl
void main() {
    time = iTime * 0.333333;
    vec2 uv = vUv;
    if(uCurvature != 0.0){ uv = barrel(uv); }
    vec2 p = uv * uScale;
    vec3 col = getColor(p);
    if(uChromaticAberration != 0.0){
      vec2 ca = vec2(uChromaticAberration) / iResolution.xy;
      col.r = getColor(p + ca).r;
      col.b = getColor(p - ca).b;
    }
    col *= uTint;
    col *= uBrightness;
    if(uDither > 0.0){
      float rnd = hash21(gl_FragCoord.xy);
      col += (rnd - 0.5) * (uDither * 0.003922);
    }
    gl_FragColor = vec4(col, 1.0);
}
```

**注意 `col *= uTint`** —— 因为整体乘了一个统一色（默认白），**RGB 分裂在这种单色下会退化成"亮度通道的分裂"，不会引入彩色**。这正是黑白 + 故障在 shader 层最优雅的做法。

**注意 `uChromaticAberration` 默认是 0**。作者默认关掉了。**做黑白风格时你应该保持它是 0**，否则一旦 tint 不是纯灰，就会有颜色。

**License 注意**：React Bits 的组件通过 shadcn CLI 分发（`npx shadcn@latest add @react-bits/FaultyTerminal-JS-TW`），是**复制到你项目里**的模式。使用前自己去仓库确认当前许可证条款。

---

### 2.4 cool-retro-term — 真实 CRT 模拟的参考实现

- 仓库（原版，Qt/QML）：https://github.com/Swordfish90/cool-retro-term
- WebGL 移植版：https://github.com/remojansen/cool-retro-term-webgl
- 页面：https://chrisbuilds.github.io/terminaltexteffects/ （同类审美参考）

**为什么值得看**：它虽然是终端模拟器，不是 boot 动画，但**「CRT 电子束」这件事它做到了物理级**。WebGL 版列出的效果清单：

- Screen curvature distortion（屏幕曲率）
- Phosphor glow / bloom（荧光辉光）
- Scanlines and rasterization（扫描线）
- RGB shift / chromatic aberration（色偏移）
- Flickering and static noise（闪烁与噪点）
- **Burn-in / phosphor persistence（余辉）**
- **Horizontal sync distortion and jitter（行同步失真）**

**「Phosphor persistence（荧光余辉）」是黑白 CRT 质感的最后一块拼图**，也是最常被忽略的。实现方式是保留上一帧输出、按强度衰减混合——也就是说**它是有状态的**，不能像 FaultyTerminal 那样纯 shader 无状态算。

如果你要做「黑白 + 故障 + 工业感」，我建议的顺序是：

1. 先做静态框架（扫描线 + 曲率 + 噪点）——纯 shader，零状态；
2. 再做故障（位移 + 反相闪切 + 抖动）——帧号驱动，离散；
3. 最后加余辉（拖尾）——需要帧缓冲，复杂度陡增。

**第 3 步不做也不会难看。** cool-retro-term 的价值在于让你知道「完整的 CRT 该有哪些参数」，而不是让你全抄。

**RhineLabUI 的加载遮罩不是 CRT 风格**，它是「白底 + 居中 Logo + 一条扫描线」，实现在 `src/style.css:1514` 起：

```css
.loading {
  position: absolute;
  inset: 0;
  background: #e8e5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  z-index: 50;
  transition: opacity 0.6s;
}
.loading.loaded {
  opacity: 0;
  pointer-events: none;
}
.loading > i {
  width: 180px;
  height: 1px;
  background: #bab3a5;
  position: relative;
  margin-top: 20px;
  overflow: hidden;
}
.loading > i:after {
  content: "";
  position: absolute;
  inset: 0;
  width: 60px;
  background: #414639;
  animation: loading 1.3s ease-in-out infinite;
}
```

**加载进度条是「1px 高的线 + 60px 的实体块在 180px 轨道里来回跑」**，不是百分比进度（因为没法预知加载进度）。而且 `.loading.loaded` 就是 `opacity: 0` + `transition: opacity 0.6s` —— 这 0.6s 正好对应 `completeStartup()` 里那段 `const fade = motionActive("boot") ? 600 : 0;`。**遮罩的淡出时长和动画的延后时长是同一个常量手抄两遍**，是个小的耦合隐患（改一处忘另一处就会看到白底上突然冒出第一个字）。

（顺带：`.reduce-motion .loading > i:after` 在 1777 行有单独覆盖，减少动效时这条扫描线要停。黑白/工业风项目里这种「辅助动效也要降级」的点很容易漏。）

如果你想加 CRT 质感，这一层是最便宜的下手位置，参考 §2.4 的参数清单。

---

### 2.5 Vivus — SVG 描边绘制库（Logo 出现的通用方案）

- 仓库：https://github.com/maxwellito/vivus
- 演示：https://maxwellito.github.io/vivus/
- 无依赖，纯 JS

**它的核心原理和 RhineLabUI 手写的 Logo 绘制完全一致**，README 里讲得很直白：

> To get this effect, the script uses the CSS property `strokeDashoffset`. This property manages the stroke offset on every line of the SVG.

它提供的动画类型：

| type | 行为 |
| --- | --- |
| `delayed`（默认） | 每条路径同时开始，最后一条稍有延迟 |
| `sync` | 所有线同时开始、同时结束 |
| `oneByOne` | 一条接一条，**每条时长按长度分配以保证匀速** |
| `script` / `scenario` / `scenario-sync` | 用 `data-delay` / `data-duration` / `data-async` 属性逐路径编排 |

关键参数：

- **`duration`（默认 200 帧）** 和 **`delay`（默认 0 帧）**——**它用帧不用秒**。这跟 RhineLabUI 用帧号是同一个判断。
- **`dashGap`（默认 2）** —— README 明确解释了它是干什么的：「Increase it in case of glitches at the initial state of the animation.」**初始状态下描边起点/终点会有残留像素，加一点额外间隙把它吃掉。** 这是这个效果最经典的坑。
- `pathTimingFunction` / `animTimingFunction`：接受「输入 0~1 返回 0~1」的普通 JS 函数，不用 cubic-bezier。

**它还解决了两个 RhineLabUI 没遇到的通用问题：**

1. **`strokeDashoffset` 只对 `<path>` 生效**，所以它附带一个 `pathformer`，把 `circle` / `rect` / `line` / `polyline` 转成 path。
2. **`non-scaling-stroke` 在动画中缩放会失效**——README 说要在 resize 时调 `recalc()`。

**结论**：如果你要做的 logo 是**多条独立笔画**，用 Vivus 省事；如果是**一条连续路径 + 头尾独立控制**（像莱茵生命那种一笔画），Vivus 的 API 不够用，还是得像 RhineLabUI 那样自己算 dash 窗口。

---

### 2.6 补充：两个可以看但是要打折的参考

**(a) `scificn-ui` — 复古科幻组件库**
https://github.com/baxy5/scificn-ui ｜ 演示 https://www.scificn.dev/
React + Tailwind v4 + Radix，通过 shadcn CLI 分发。93 stars（搜索结果标注，未复核）。
有意思的地方是它内置了**三套配色主题**，其中一套就叫 **ALIEN**（`#E0D5BE` 骨白 + `#ff8800` 琥珀）：
> | **SCI-FI** (default) | `#00ed3f` green | Phosphor terminal |
> | **STAR WARS** | `#1a6dff` blue | Holographic readout |
> | **ALIEN** | `#E0D5BE` bone | Warm organic dark |

**可借鉴**：它的「骨白 + 琥珀」配色（`#E0D5BE` / `#ff8800`）非常接近工业风 boot 需要的调子。但组件本身是静态样式组件，**没有 boot 时序逻辑**，别指望拿它当动画参考。

**(b) JARVIS / HUD 系组件库**
搜到一批（`@masterdeepak15/jarvis-ui`、`bhanustark/Futuristic-UI`、`nocoo/matrix`、`Davood121/jenman` 等）。它们普遍都是冷色/青色发光风格（`#00CFFF` / `#00FFF7`），**与黑白配色方向相反**，而且多为低星新仓库。
**可取的一点**：`jarvis-ui` 的 `JBootScreen` 是「5 阶段 boot 覆盖层」这个抽象本身是对的（阶段划分而不是单一组件），但实现没法参考。

---

## 3. 黑白配色 + 故障艺术：能站得住的参考

这一节分三层：**理论**（判断什么算好）、**黑白故障艺术的正统案例**（视觉语汇）、**Web 上的可复用实现**（代码）。

### 3.1 理论层：故障艺术的美学边界

**Rosa Menkman —《Glitch Studies Manifesto》**（2010）
- 未命名/未命名/未命名/未命名 → 文章本体：http://rosa-menkman.blogspot.com/2010/04/glitches-vs-glitch-art.html
- 《A Vernacular of File Formats》（databending 方法论手册）

这是故障艺术领域**引用最多的一手文本**。里面有两句对做 UI 动画直接有用：

> The glitch has no solid form or state through time; it is often perceived as an unexpected and abnormal mode of operandi, a break from (one of) the many flows (of expectations) within a technological system. But as the understanding of a glitch changes when it is being named, so does the equilibrium of the (former) glitch itself: the original experience of a rupture moved passed its momentum and vanished into a realm of new conditions.

> But for some, mostly the audience on the receptive end, these designed errors are still experienced as the breaks of a flow and can therefore righteously be called glitches. They don't know that these works are constructed via the use of a filter.

**翻译成工程规则：**

- **故障的力量来自「断裂」而不是「效果」**。一个持续闪的 glitch shader 看两秒就变成背景噪音。
- **断裂必须发生在「预期流」上。** 屏幕应该看起来「本来在正常运行」，然后被打断。如果画面从头到尾都在抖，就没有任何东西被打断了。
- **「被设计出的错误」也可以是故障艺术**——Menkman 自己承认这一点。所以你不必真的去破坏数据。

**对 glitch-boot 的直接含义**：**先让画面正常 3 秒，再故障。** 或者至少让故障有「密度曲线」：稀疏 → 密集 → 突然静默。RhineLabUI 干的就是这件事——它整段动画只有 **4 帧**（525/526/528/529）是真闪切，加上 628/629/631/634 四帧和 594/595 两帧灰闪。**总共不到 10 帧的故障，撑起了整个片子的"系统感"。**

### 3.2 黑白故障艺术的正统案例

#### (1) Ryoji Ikeda — test pattern / datamatics

- test pattern：https://www.ryojiikeda.com/project/testpattern/
- datamatics：https://www.ryojiikeda.com/project/datamatics/
- YCAM 项目页：https://www.ycam.jp/en/archive/works/test-pattern/
- YCAM 介绍会稿：https://special.ycam.jp/datamatics/en/testpattern.html

**这是「黑白 + 数据 + 故障」这个方向最重要的一手案例**，而且它本身就是「屏幕测试」——和 boot sequence 是同一个语义家族。

自述核心（官方页原文）：

> test pattern is a system that converts any type of data (text, sounds, photos and movies) into barcode patterns and binary patterns of 0s and 1s. Through its application, the project aims to examine the relationship between critical points of device performance and the threshold of human perception.

> The velocity of the moving images is ultra-fast, some hundreds of frames per second, providing a performance test for the audio and visual devices, as well as a response test for one's perceptions.

> Projecting dynamic computer-generated imagery in pared down black and white with striking colour accents...
> From 2D sequences of patterns derived from **hard drive errors** and studies of software code...

**五条可以搬的语汇：**

1. **数据 → 条形码/二进制图案。** 你的 boot 里的每一行日志都可以映射成宽窄不一的竖条。这是「把数据可视化成本该是数据的形状」。
2. **纯黑 + 纯白，无灰阶。** 没有渐变的接口才有硬件感。
3. **"pared down black and white with striking colour accents"** —— 极度克制的黑白 + 极少数强调色。**和 RhineLabUI 那个橙色点（`#ed821b`）是完全同一个策略。**
4. **速度本身就是内容。** 几百 fps 的闪烁不是"快"，是"超过你能看清的阈值"——不确定性本身就是信息。网页里等价做法：**在两帧内完成的硬切**（RhineLabUI 的 `at(f, [...])` 就是这个）。
5. **来源是错误**：hard drive errors。故障的素材应该来自真实系统的失败痕迹（CRC 错误、掉帧、坏块、校验和），不是随便抖。

**注意**：这是**装置/演出艺术**，没有开源代码。它的价值是视觉语言和概念框架。

#### (2) Kim Asendorf — ASDFPixelSort（像素排序）

- 仓库：https://github.com/kimasendorf/ASDFPixelSort
- 作者站：https://kimasendorf.com/mountain-tour/pixel-sorting-meeting-chaos-half-way/
- 2010 年发布，2012 年开源；Processing（.pde）

**为什么特别适合黑白**：它的排序模式**前两个就是 white 和 black**。源码头部：

```
/********

 ASDF Pixel Sort
 Kim Asendorf | 2010 | kimasendorf.com
 
 
 Sorting modes
 
 0 = white
 1 = black
 2 = bright
 3 = dark
 
 */
```
```
// threshold values to determine sorting start and end pixels
// using the absolute rgb value
// r*g*b = 255*255*255 = 16581375
// 0 = white
// -16581375 = black
// sort all pixels whiter than the threshold
int whiteValue = -12345678;
// sort all pixels blacker than the threshold
int blackValue = -3456789;
// using the brightness value
// sort all pixels brighter than the threshold
int brightValue = 127;
// sort all pixels darker than the threshold
int darkValue = 223;
```

核心算法（真的就这么短）：

```java
  int x = 0;
  int xEnd = 0;
  while (xEnd < img.width-1) {
    switch (mode) {
    case 0:
      x = getFirstNoneWhiteX(x, y);
      xEnd = getNextWhiteX(x, y);
      break;
    ...
    }
    if (x < 0) break;
    int sortingLength = xEnd-x;
    color[] unsorted = new color[sortingLength];
    color[] sorted = new color[sortingLength];
    for (int i = 0; i < sortingLength; i++) {
      unsorted[i] = img.pixels[x + i + y * img.width];
    }
    sorted = sort(unsorted);
    for (int i = 0; i < sortingLength; i++) {
      img.pixels[x + i + y * img.width] = sorted[i];
    }
    x = xEnd+1;
  }
```

**算法本质：按行（或列）扫描，把「阈值之间的连续像素段」按亮度排序。** 结果是拉长的条纹/涂抹，那种"像素在流动"的经典 glitch 观感。

**黑白版本的特别之处**：用 mode 0（white）时，只有比阈值更亮的连续段会被排序——**在纯黑背景的白字上，这个效果会把文字横向"拉丝"，而黑色背景纹丝不动**。这正是黑白故障最需要的：**破坏只发生在亮的部分**。

**性能注意**：`sort()` 是 Processing 内置；JS 移植的话对小图可以用 `Array.prototype.sort`，全屏分辨率会卡（每次排序 O(n log n) × 段数）。**在 boot 动画里应该只对文字层做，不要对全屏做。**

理论补充（Sarah Zucker 为作者站写的文章）：

> There is no actual "glitch" in this glitch: it's not borne of a mistake, but rather, a generative mechanism with great precision.

**「精确的生成机制」而不是「事故」——这就是你该做的事。**

#### (3) 其他 1-bit / 单色故障方向

- **1-bit 抖动（dithering）**：Bayer 2×2/4×4/8×8 有序抖动 + 二值阈值。
  参考实现（Warp Dither Lab，含真实 GLSL 参数表）：https://git.xszz.org/pulkitxm/claude-directory/blob/main/shaders/warp-dithering-shader
  它把 7 种程序化形状场（simplex/warp/dots/wave/ripple/swirl/sphere）经阈值压成一位。**这是「黑白 + 数字化」的底层语言**：所有灰阶都被还原成点阵。
  在 boot 动画里对应的是：**「正在解析」的阶段用抖动图案，解析完成后才出清晰文字**。
- **databending 方法论**：Rosa Menkman《A Vernacular of File Formats》
  核心手法是改文件头参数（raw、bmp 的宽高/通道）、复制粘贴数据块、跨格式转换。里面有一段对 BMP 的说明很实在：
  > The BMP file format is uncompressed; every bit that indexes a bitmap pixel value is packed within a linear row, "upside-down" with respect to normal image raster scan order, starting in the lower right corner, advancing row by row from the bottom to the top.
  **注意**：这一套是"对文件本体"的破坏，网页动画里**不要真去 databend 图片**（不可预览、不可复现、体积爆炸）。要的是它的**视觉结果**，用参数化方式重建。

### 3.3 Web 上的可复用实现（含真实代码）

#### (1) `glitch-canvas` — 参数化、可种子复现

- 仓库：https://github.com/snorpey/glitch-canvas

```js
var glitchParams = {
	seed:       25, // integer between 0 and 99
	quality:    30, // integer between 0 and 99
	amount:     35, // integer between 0 and 99
	iterations: 20  // integer
};
```
```js
	glitch( { seed: 25, quality: 30 } )
		.fromImage( image )
		.toDataURL()
		.then( function( dataURL ) {...} );
```

**它的参数设计值得学**：只有 4 个参数，其中 **`seed` 是整数**——意味着**同样的 seed 永远产生同样的故障**。

**这为什么重要**：RhineLabUI 把故障帧写死成 `at(f, [525, 526, 528, 529])`——**同一帧永远同一个故障**。如果故障是随机的，第一遍看到的和录屏看到的就不一样，也没法做视觉验收。

> 这是做 boot 动画的硬约束：**故障必须是可复现的。** 用 `seed = f`（帧号当种子）就能同时拿到「看起来随机」和「完全可复现」。

它支持浏览器和 node（`toDataURL()` / `toBuffer()` / `toJPGStream()` 等），可以做构建期预渲染。「input → 变换 → output」的链式 API 也很干净。

#### (2) `Canvas UI — Glitch` — WebGL 逐帧故障 + 参数化

- 文档/演示：https://canvasui.dev/docs/components/glitch

参数接口：

```ts
export interface GlitchOptions {
  intensity?: number;      // Overall strength of the glitch (0 to 2).
  interval?: number;       // Seconds between glitch bursts. 0 keeps the glitch running constantly.
  duration?: number;       // How long each burst lasts in seconds.
  slices?: number;         // Number of horizontal slices the tear snaps to. Lower is chunkier.
  shift?: number;          // How far the torn slices shift sideways, in CSS pixels.
  rgbShift?: number;       // Chromatic RGB split during bursts, in CSS pixels.
  blocks?: number;         // Amount of corrupted block artifacts during bursts (0 to 1).
  noise?: number;          // Analog noise and scanline flicker during bursts (0 to 1).
}
```

**`interval` 和 `duration` 分开，就是「断裂 vs 效果」的正确建模**：`interval` 是两个故障之间的**正常时间**，`duration` 是故障本身的长度。默认 `interval: 3, duration: 0.4` —— **正常 3 秒，故障 0.4 秒**。这个比例（约 7.5:1）可以直接拿来用。

它的时间线逻辑：

```ts
  function advanceTimeline(delta: number) {
    time += delta;
    if (config.interval <= 0) { envelope = 1; return; }
    const sinceBurst = time - burstAt;
    const duration = Math.max(config.duration, 0.05);
    if (sinceBurst >= 0 && sinceBurst < duration) {
      const tail = 1 - Math.pow(sinceBurst / duration, 2);
      envelope = tail * (0.7 + 0.3 * hash(burstSeed + Math.floor(time * 24)));
    } else {
      envelope = 0;
      if (sinceBurst >= duration) {
        burstAt = time + Math.max(config.interval, 0.3) * (0.75 + 0.5 * Math.random());
        burstSeed = Math.floor(Math.random() * 1000);
      }
    }
  }
```

三个要点：

1. **`const tail = 1 - Math.pow(sinceBurst / duration, 2);`** —— 故障的**包络是二次衰减**，一开始最强然后快速减弱。**不是方波**。
2. **`envelope = tail * (0.7 + 0.3 * hash(...))`** —— 在衰减上乘一个 0.7~1.0 的随机量，**每次故障的强度都不同**。
3. **`burstAt = time + interval * (0.75 + 0.5 * Math.random())`** —— **间隔本身也是随机的**（±25%）。如果用固定间隔，节奏会变成节拍器。

shader 里的位移：

```glsl
  if (e > 0.001) {
    float band = floor(uv.y * uSlices);
    float pick = hash12(vec2(band, uSeed));
    float tear = step(1.0 - 0.3 * min(e, 1.0), pick);
    float dir = hash12(vec2(band, uSeed + 13.0)) * 2.0 - 1.0;
    guv.x += tear * dir * e * uShift / uResolution.x;

    float sub = floor(uv.y * uSlices * 7.0);
    float micro = hash12(vec2(sub, uSeed + 29.0));
    guv.x += (micro - 0.5) * e * uNoise * 3.0 / uResolution.x;

    vec2 cell = floor(guv * vec2(10.0, uSlices * 0.5));
    float br = hash12(cell + uSeed * 0.0173);
    if (br > 1.0 - 0.14 * uBlocks * min(e, 1.0)) {
      vec2 jump = vec2(hash12(cell + uSeed + 3.1) - 0.5, hash12(cell + uSeed + 7.7) - 0.5);
      guv += jump * vec2(0.08, 0.02) * e;
    }
  }
```

**`float dir = hash12(...) * 2.0 - 1.0;`** —— **位移方向也是随机的（正或负）**。如果所有切片都往同一边偏，看起来像"页面歪了"；方向一随机，立刻变成"信号撕裂"。

**色调处理决定了黑白能否成立**：

```glsl
  float split = uRgbShift * e / uResolution.x;
  vec4 c = page(guv);
  float r = page(guv + vec2(split, 0.0)).r;
  float b = page(guv - vec2(split, 0.0)).b;
  vec4 col = vec4(r, c.g, b, c.a);
```

这是标准 RGB split：**分别取样 R 通道的左偏移和 B 通道的右偏移**。在**纯黑白内容上，这个操作本身是"安全的"**（黑白的 R=G=B，偏移后会露出边缘），但会让边缘出现轻微彩色。**如果黑白是硬要求，把 `rgbShift` 设成 0，或者把 split 后的结果再过一遍 `luma()` 变回灰。**

```glsl
    float row = floor(vUv.y * uResolution.y);
    float flicker = hash12(vec2(row, uSeed + 41.0));
    float lines = step(0.985 - 0.01 * uNoise * e, flicker);
    col.rgb += (grain * 0.22 + lines * 0.35) * uNoise * min(e, 1.0) * col.a;
```

**`row = floor(vUv.y * uResolution.y)` —— 噪点是"逐行"而非"逐像素"的。** 这让噪点看起来像**行同步干扰**而不是相机 ISO 噪点。**黑白 + 行噪点 = CRT 信号**；逐像素噪点 = 胶片颗粒。**两者完全不同。**

#### (3) `errorhead` — WebGL 故障工作台（网页端 glitch 效果全集）

- 仓库：https://github.com/eg0pr0xy/errorhead
- React 19 + TypeScript + Vite + Three.js + Tailwind

自述是「30+ 信号操控系统」，功能清单里有几项是前面没有的：

- **datamoshing**（帧间运动向量污染）
- **macroblock destruction**（宏块破坏——直接模拟视频压缩失败）
- **temporal echo / motion sculpture**（时间回响）
- **Audio-reactive modulation（mic / video / imported music）**

**两个值得注意的设计：**

1. **`Landing gate before editor entry (ENTER)`** —— 进入编辑器前有一个「ENTER」门。**这跟 boot sequence 是同一个交互母题**（RhineLabUI 的 `StartupGate` 也是这个），而且它解决了一个真实问题：浏览器音频需要用户手势才能播放。
2. **`Canvas remains blank until media source is valid (no fake test pattern)`**
   **不要放假测试图。** 如果没素材就保持黑屏。这条反直觉但是对的：一个假的彩条测试图会立刻暴露「这是个 demo」，而一个黑屏 + 等待提示是「系统在等输入」。

#### (4) Codrops — CSS `clip-path` 故障分层

- https://tympanus.net/codrops/2017/12/21/css-glitch-effect/（curl 返回 403 是反爬，链接有效）

核心是**同一张图叠 5 层**，除第一层外每层有不同 `clip-path` + `translate` + `background-blend-mode`：

```css
/* Set the background colors for the glitch images*/
.glitch__img:nth-child(2) {
	background-color: var(--blend-color-2);
	background-blend-mode: var(--blend-mode-2);
}
```
```css
.glitch__img:nth-child(n+2) { opacity: 0; }
.glitch:hover .glitch__img:nth-child(n+2) { opacity: 1; }
```
```css
.glitch:hover .glitch__img:nth-child(2) {
	transform: translate3d(var(--gap-horizontal),0,0);
	animation: glitch-anim-1-horizontal var(--time-anim) infinite linear alternate;
}
.glitch:hover > .glitch__img:nth-child(5) {
	animation: glitch-anim-flash 0.5s steps(1,end) infinite;
}
```

`clip-path` 的动画是**手写的百分比 polygon 序列**，刻意写得「不规律」：

```css
@keyframes glitch-anim-1-horizontal {
	0% { clip-path: polygon(0 2%, 100% 2%, 100% 5%, 0 5%); }
	10% { clip-path: polygon(0 15%, 100% 15%, 100% 15%, 0 15%); }
	20% { clip-path: polygon(0 10%, 100% 10%, 100% 20%, 0 20%); }
	30% { clip-path: polygon(0 1%, 100% 1%, 100% 2%, 0 2%); }
	40% { clip-path: polygon(0 33%, 100% 33%, 100% 33%, 0 33%); }
	50% { clip-path: polygon(0 44%, 100% 44%, 100% 44%, 0 44%); }
	60% { clip-path: polygon(0 50%, 100% 50%, 100% 20%, 0 20%); }
	70% { clip-path: polygon(0 70%, 100% 70%, 100% 70%, 0 70%); }
	80% { clip-path: polygon(0 80%, 100% 80%, 100% 80%, 0 80%); }
	90% { clip-path: polygon(0 50%, 100% 50%, 100% 55%, 0 55%); }
	100% { clip-path: polygon(0 70%, 100% 70%, 100% 80%, 0 80%); }
}
```

**注意第 10%、30%、40% 这些关键帧的矩形是"零高"的**（`100% 15%, 0 15%` 上下边界相同）—— 也就是**那一层完全不可见一瞬**。文章原文：

> The slices will go from tiny, to a bit larger and also nothing, leaving a "pause" on some of the frames and then starting again from another position.

**「什么都没有」的帧是故意留的。** 有停才有断。

而最后一层只闪不切：

```css
@keyframes glitch-anim-flash {
	0% { opacity: 0.2; transform: translate3d(var(--gap-horizontal), var(--gap-vertical), 0); }
	33%, 100% { opacity: 0; transform: translate3d(0,0,0); }
}
```

**两帧内消失，然后三分之二的时间什么都不做。** `steps(1,end)` 保证是硬闪不是淡入。

**对黑白项目的适用性**：这套技术**完全基于 `clip-path` + `translate` + `opacity`，不涉及颜色通道**，可以直接搬到黑白界面。**这是纯 CSS 条件下做黑白故障最可行的一条路。**

#### (5) Nick Hart — SVG filter 故障（黑白下最实用的一套）

- https://www.nickhart.co.uk/2021/04/18/animated-svg-cyberpunk-logo-with-filters/

**它是单图/单 SVG 的实现，靠 `feTurbulence` + `feDisplacementMap`：**

```html
<filter id="Analog_noise">
    <feTurbulence 
        type="fractalNoise" 
        baseFrequency="0.0001 0.0001"
        numOctaves="1" 
        result="warp"
    ></feTurbulence>
    <feDisplacementMap 
        xChannelSelector="R"
        yChannelSelector="G" 
        scale="30" 
        in="SourceGraphic" 
        in2="warp"
    />
</filter>
```

**动画靠改 `baseFrequency` 的 x 分量：**

```js
const analogNoiseTl = analogNoise().pause();

function analogNoise() {
  let turbVal = { val: 0.000001 };
  const turb = document.querySelector("#Analog_noise feTurbulence");

  const tl = gsap.timeline({
    onUpdate: function () {
      turb.setAttribute("baseFrequency", "0 " + turbVal.val);
    }
  });

  tl.to(turbVal, 0.2, { val: 0.9 });
  tl.to(turbVal, 0.2, { val: 0.000001 });

  return tl;
}
```

**这是整个清单里最重要的一条黑白故障技巧：**

**`baseFrequency="0 N"` 里 x=0、只动 y 分量 → 产生纯横向位移场。** `feTurbulence(baseFrequency="0.001 10")` 也一样——**只要让一个轴的分量为 0 或极端不对等，就能得到方向单一的条纹**（见他的 `screenLines` 滤镜）。这对故障来说至关重要：**各向同性的噪声看起来像脏了，各向异性的噪声看起来像信号坏了。**

而且它**完全不动颜色**。黑白内容进去，黑白内容出来，只是被位移场撕开。**如果你要做「黑白 + 故障」，`feDisplacementMap` 比 RGB split 更合适。**

他还给了那个经典的**屏幕噪点滤镜**：

```html
<filter id="noise" x="0vw" y="0vh" width="100vw" height="100vh">
    <feFlood flood-color="#808080" result="neutral-gray" />
    <feTurbulence in="neutral-gray" type="fractalNoise" baseFrequency="0.3" seed="1" numOctaves="10" stitchTiles="stitch" result="noise" />
    <feColorMatrix in="noise" type="saturate" values="0" result="destaturatedNoise" />
    <feComponentTransfer in="desaturatedNoise" result="theNoise">
        <feFuncA type="table" tableValues="0 0 0 0.2 0" />
    </feComponentTransfer>
    <feBlend in="SourceGraphic" in2="theNoise" mode="soft-light" result="noisy-image" />
</filter>
```

拆解：

- `feFlood` 铺一层中灰做基底；
- `feTurbulence` 生成噪声；
- **`feColorMatrix type="saturate" values="0"` —— 强制去饱和，这是黑白项目的必需品**；
- `feComponentTransfer` + `feFuncA table` 把噪声的 alpha 曲线压成**极窄的一段**（大部分为 0，只有中间一档为 0.2）—— 噪声变成了**稀疏的亮点**，而不是均匀的灰；
- `feBlend mode="soft-light"` 柔和叠加。

配套动画：

```css
body:after {
  animation: screenNoise 2s steps(10) infinite;
  filter: url(#noise);
  content: "";
  height: 300%;
  left: -50%;
  opacity: 0.12;
  position: fixed;
  top: -110%;
  width: 300%;
  z-index: 0;
}
```

**三个细节：**

1. **`steps(10)` 而不是 linear** —— 噪点必须以「跳」为单位变化，线性过渡会糊成雾气。
2. **元素放大到 300% 并偏移出屏** （`left: -50%; top: -110%; height/width: 300%`）—— 这样 `translate` 动画可以在不露边的情况下到处推。**这是做"噪点背景"的标准尺寸设定。**
3. **`opacity: 0.12`** —— 极低。噪声一旦超过 0.2 就会开始摧毁对比度。**黑白项目对噪点透明度极其敏感。**

引用来源他自己也标了（Codrops 的 "SVG filters 101" 系列 + 一个 Stack Overflow 的噪声滤镜），属于可以放心借鉴的公共知识。

---

## 4. 落到「glitch-boot」上的取舍建议

把上面三部分合起来，黑白 + 故障 + boot 的**技术选择优先级**是这样：

| 需求 | 推荐做法 | 参考 |
| --- | --- | --- |
| 时间轴 | 纯函数 + 帧号关键帧 + 单调 Hermite | RhineLabUI §1.2 |
| 逐字输入 | 每帧字数表（不要匀速）；字符级 span 需要手写字距 | RhineLabUI §1.3 |
| Logo 出现 | 单路径 + `pathLength=1` + dash 窗口；或多路径用 Vivus | RhineLabUI §1.4 / Vivus |
| 扫描/权限圆环 | 半径 + 起始角 + 弧长 三条轨迹参数化；满圆必须拆两段 | RhineLabUI §1.5 |
| 故障本体 | **帧号白名单硬切**，四帧一组（放大 + 掉透明度 + 模糊） | RhineLabUI §1.5(5) |
| 黑白故障（不引入颜色） | ①黑白反相闪切（`invert`）；②`clip-path` 切片位移；③`feDisplacementMap` 各向异性位移；④行噪点 | §1.6(2) / §3.3(4) / §3.3(5) |
| 故障节奏 | `interval ≈ 3s` / `duration ≈ 0.4s`；包络二次衰减；间隔 ±25% 随机 | Canvas UI §3.3(2) |
| 故障可复现 | `seed = 帧号` | glitch-canvas §3.3(1) |
| 打字音 | 由时间轴反推「哪一帧有新字」；每字变调 0.9~1.5× | §1.3(4) / §2.2 |
| 字符辉光 | 出现时套一层 `text-shadow` 衰减（1→0，expo.out，约 1s） | §2.2 |
| 页面进场 | 逐格随机延迟点亮（shader 里 5 行） | FaultyTerminal §2.3 |
| 降水动效 | 白场用 smoothstep，其他一律硬切 | §1.6(4) |
| 字体 | 图形化发行，字体可选加载；换字体要算基线补偿 | §1.9 |

**需要留意的三个反模式**（我从源码和文档里读出来的实际教训）：

1. **不要用统一匀速打字。** RhineLabUI 那 4 帧的停顿和 `[1,1,3,4,5,6,9,...]` 的跳跃，就是「机器感」和「打字机特效」的分界线。
2. **不要用 RGB split 做黑白故障。** 它会引入颜色。用反相、`clip-path` 切片、`feDisplacementMap` 更正统，而且更像「信号」而不是「视频特效」。
3. **不要让故障持续发生。** Menkman 那句话的工程含义：故障要打断一个「正常流」，正常流不存在时故障就不成立。RhineLabUI 全程不到 10 帧故障，剩下 400 多帧都是「正常运行」。

---

## 5. 参考链接总表

**RhineLabUI（本次主讲）**
- 主仓库：https://github.com/LBEILC/RhineLabUI （MIT；`src/` 14061 行）
- 在线体验：https://rhine.lubeiluchen.cc/
- 壁纸版（已拆分为独立仓库）：https://github.com/LBEILC/RhineLabWallpaper
- 参考原 PV（明日方舟「莱茵生命：访问」）：https://www.bilibili.com/video/BV1rr4y1b7sz/

**boot sequence 开源实现**
- TerminalTextEffects（Python，40 种效果，decrypt / vhstape / laseretch）：https://github.com/ChrisBuilds/terminaltexteffects ｜ https://chrisbuilds.github.io/terminaltexteffects/
- Alien MU-TH-UR 6000 UI（CodePen）：https://codepen.io/tkmoney/pen/qBoVGWy ｜ 源码镜像：https://gist.github.com/vforge/c35de355ea5d730df227209ae371eb92
- Alien 控制台 + 原片音效（CodePen 导出）：https://github.com/zero-ability/codevember-13-mu-th-ur-plus-audio
- MU-TH-UR 6000（React）：https://github.com/alexpritt/muthur6000
- MU-TH-UR 终端（网页）：https://jcar.github.io/muthur-terminal/
- Typeset In The Future《Alien》设计考证：https://typesetinthefuture.com/2014/12/01/alien/
- MU/TH/UR 设计解读（NeoCities）：https://checkplease.neocities.org/couchto4k/p/mother-muthur-and-the-company
- React Bits · Faulty Terminal（WebGL 单色终端 shader）：https://reactbits.dev/backgrounds/faulty-terminal ｜ https://reactbits.dev/docs/components/faulty-terminal ｜ https://github.com/DavidHDev/react-bits
- cool-retro-term（CRT 模拟）：https://github.com/Swordfish90/cool-retro-term ｜ WebGL 移植：https://github.com/remojansen/cool-retro-term-webgl
- Vivus（SVG 描边绘制）：https://github.com/maxwellito/vivus ｜ https://maxwellito.github.io/vivus/
- Codrops · SVG Drawing Animation：https://tympanus.net/codrops/2013/12/30/svg-drawing-animation/
- scificn-ui（复古科幻组件库，含 ALIEN 配色）：https://github.com/baxy5/scificn-ui ｜ https://www.scificn.dev/

**黑白 + 故障艺术**
- Rosa Menkman · glitches vs glitch art（Glitch Studies Manifesto 节选）：http://rosa-menkman.blogspot.com/2010/04/glitches-vs-glitch-art.html
- Rosa Menkman · A Vernacular of File Formats（databending 方法）：https://www.scribd.com/document/134624471/Lofi-Rosa-Menkman-A-Vernacular-of-File-Formats
- Ryoji Ikeda · test pattern：https://www.ryojiikeda.com/project/testpattern/ ｜ YCAM 页：https://www.ycam.jp/en/archive/works/test-pattern/
- Ryoji Ikeda · datamatics：https://www.ryojiikeda.com/project/datamatics/
- Kim Asendorf · ASDFPixelSort：https://github.com/kimasendorf/ASDFPixelSort ｜ 文章：https://kimasendorf.com/mountain-tour/pixel-sorting-meeting-chaos-half-way/
- glitch-canvas（种子可复现）：https://github.com/snorpey/glitch-canvas
- Canvas UI · Glitch（WebGL，interval/duration 包络）：https://canvasui.dev/docs/components/glitch
- errorhead（WebGL 故障工作台）：https://github.com/eg0pr0xy/errorhead
- Codrops · CSS Glitch Effect（clip-path 分层）：https://tympanus.net/codrops/2017/12/21/css-glitch-effect/
- Nick Hart · Animated SVG Cyberpunk logo with filters（feTurbulence + feDisplacementMap）：https://www.nickhart.co.uk/2021/04/18/animated-svg-cyberpunk-logo-with-filters/
- 1-bit WebGL2 抖动 shader（Bayer 2×2/4×4/8×8）：https://git.xszz.org/pulkitxm/claude-directory/blob/main/shaders/warp-dithering-shader

---

## 6. 我没能确认的部分（不要当成事实）

1. **RhineLabUI 的动画在真机上什么手感，我没验证。** 没构建、没运行。
2. **`verification/*.md` 里那些"通过 N 项检查"的结论，我引用的是它的自述**，没有复跑 `scripts/check-boot-*.mjs`。
3. **仓库的原始帧提取工具（`reference/*.py`）需要本地 MP4 才能复现**，我拿不到原片，所以那些关键帧数值的"正确性"我无法独立验证——我只能证明**代码里确实写着这些数字，并且被用于驱动动画**。
4. **`curvature`、`blur` 等 CSS filter 的跨浏览器一致性我没测。** Safari 对 `filter: blur()` 加在 SVG `<g>` 上的行为有历史差异，这块真机可能不一致。
5. **第 2 部分里带星数的条目，星数来自搜索引擎快照，没有去 GitHub API 复核。** 我明确标了「搜索结果标注」。
6. **两个 URL 的 HTTP 返回是 403**（`codepen.io/tkmoney/pen/qBoVGWy`、`tympanus.net/codrops/2017/12/21/css-glitch-effect/`）。这是反爬拦截，不代表链接失效——它们的正文我通过搜索引擎抓取读到了，代码片段是真实的。但如果你的环境要"必须返回 200"的证据，这两条需要你自己再确认一次。
7. **React Bits 的许可证我没有逐字读过。** 它是 shadcn 分发（把代码复制进你的项目），我建议你用之前自己去仓库看 LICENSE 和当前的条款——这种组件库的分发条款有过变更记录。
