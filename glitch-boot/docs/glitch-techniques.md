# Glitch Art 技法清单 —— Canvas / CSS 可实现版

> 检索日期：2026-10-08（UTC）
> 检索方式：Exa 联网检索 + 逐条 HTTP 状态校验（`curl -L`，可访问性已验证）
> 说明：本文所有参考链接均为真实存在的页面，已实测返回 200。CodePen 对无头请求返回 403 是反爬策略，该 Pen 已通过内容抓取确认存在。

---

## 0. 先给结论：12 个技法的实时性总表

先看这张表再决定做哪几个。**"能不能逐帧实时渲染"的答案差异极大**，有些是白送的，有些再怎么优化也做不到全分辨率 60fps。

| # | 技法 | 实现路径 | 逐帧实时（60fps） | 成本档 |
|---|------|----------|------------------|--------|
| 1 | pixel sorting 像素排序 | Canvas2D 逐行排序 / WebGPU 并行基数排序 | ❌ 全分辨率 CPU 不可行<br>⚠️ 局部窗口/降采样可行<br>✅ WebGPU 可行 | 极高 |
| 2 | datamosh 区块位移 | Canvas2D 块拷贝 / WebGL 双纹理 | ✅ 完全可行 | 极低 |
| 3 | scanline tearing 扫描线撕裂 | Canvas2D 逐条 drawImage / WebGL UV 偏移 | ✅ 完全可行 | 极低 |
| 4 | RGB channel shift 通道分离 | Canvas2D 偏移混合 / ImageData / WebGL 三次采样 | ✅ 完全可行 | 极低 |
| 5 | vertical roll / VHS tracking | Canvas2D 两次 drawImage + 底部噪声带 / WebGL | ✅ 完全可行 | 低 |
| 6 | sine wave distortion 正弦扭曲 | Canvas2D 逐行偏移 / WebGL | ✅ WebGL 完全可行<br>⚠️ Canvas2D 逐行可跑但吃 CPU | 低～中 |
| 7 | dither / Bayer 抖动网屏 | ImageData 量化 / WebGL 阈值矩阵 | ✅ 有序抖动完全可行<br>❌ 误差扩散（Floyd–Steinberg）不可行 | 低 |
| 8 | bitcrush / posterize 位深压缩 | 查表量化 | ✅ 完全可行 | 极低 |
| 9 | ghost echo 残影 | 半透明覆盖 / ping-pong FBO | ✅ 完全可行 | 极低 |
| 10 | mirror slice 镜像切片 | 负宽 drawImage / UV 角度折叠 | ✅ 完全可行 | 极低 |
| 11 | static noise 噪点 | 预生成 tile / 降采样 / WebGL hash | ⚠️ Canvas2D 全分辨率逐像素是瓶颈<br>✅ WebGL / tile 方案可行 | 中（看方案） |
| 12 | text corruption / zalgo | Unicode 组合符号 / 位图化切换 | ⚠️ 60Hz 改 DOM 文本不可行<br>✅ 位图化 + 10~15Hz 可行 | 中 |

**一句话路线建议**：3 + 4 + 5 + 9 + 11 这五个是"白送组合"，全部加起来不到 3ms/帧；1、7（误差扩散）、12 是全套里唯一需要工程取舍的三个。

---

## 1. Pixel Sorting 像素排序

**中文名**：像素排序
**英文名**：Pixel Sorting / ASDF Pixel Sort / glitch sort

### 视觉特征

画面某些水平或垂直条带里，像素被按亮度/色相重新排列，形成"颜料被刮开"的拉丝条纹。它和涂抹的区别在于：**排列后的条带里，颜色分布和原图完全一致，只是顺序变了**——所以仍能认得出原图，但局部像被梳子梳过。颗粒是硬的、有方向的、按行/列组织。

### 算法本质（必须搞清楚的三个参数）

1. **区间怎么划（interval function）**。这是决定"好不好看"的关键，比排序本身重要得多：
   - `threshold`：只有亮度落在 [lower, upper] 之间的连续像素进入排序区间（satyarth 的 `-t/-u` 默认 0.25/0.8）
   - `edges`：先做边缘检测，用边缘当区间边界
   - `random` / `waves`：随机宽度 / 近似等宽波
   - `file`：用另一张黑白图当区间图
   - 以及 Kim Asendorf 原始的四种 mode：white / black / bright / dark（按绝对值或 brightness 定阈值）

   **只排整行 = 得到一条渐变，完全不是 glitch。** 必须让一部分像素"不被排序"留在原地。

2. **按什么排序（sorting function）**：lightness / hue / saturation / intensity（RGB 之和）/ minimum（RGB 最小值）。

3. **方向**：先列后行和先行后列结果不同——**后执行的那一遍主导最终视觉**。Kim 原始脚本是"先竖后横"。

### Canvas 实现要点

```js
// 关键技巧 1：把 4 个通道打包成一个 uint32，移动一个像素 = 一次赋值
const buf = new Uint32Array(imageData.data.buffer);
// 每个像素: r | g<<8 | b<<16 | a<<24  (小端)

// 关键技巧 2：亮度当排序 key 时，用 256 桶计数排序，O(n)，别用带比较器的 .sort()
const BUCKET = 256;
// 对每个区间: 统计 → 前缀和 → 回填。对 1920 宽的一行比 Array.sort 快一个量级

// 关键技巧 3：预计算 LUT，别在像素循环里算 Math.sqrt
const lumLUT = new Uint8Array(256 * 256 * 256); // 太大，别这么做
// 正确做法：把 r/g/b 拆开后用 (r*77 + g*151 + b*28) >> 8 这种整数近似
```

- **区间检测是纯扫描**：一行扫一遍，遇到阈值外侧就切段，切段后再各排各的。不要先收集所有段再处理，会多一轮内存分配。
- 用两个 `ImageData` 乒乓，避免读写的读写污染。
- 用 `setImageData` 之前把整个画面一次性写回，不要逐行 `putImageData`（每次调用都有固定开销）。

### 是否适合逐帧实时渲染

**结论：CPU 全分辨率不行；有条件可行。**

硬数据：一个纯 Python 实现排序 1920×1200 图（默认阈值、45°）需要约 **17 秒**；改成 C++ 多线程 2.1 秒（[DavidMcLaughlin208/PixelSorting](https://github.com/DavidMcLaughlin208/PixelSorting) 里明确给出的对比）。也就是说单帧就已经是 2 秒量级，和 16.7ms 差了三个数量级。

可行的三条路：

1. **局部窗口**：每行只排 ≤64px 的片段，且每帧只轮转处理 1/4 的行。视觉上仍有拉丝，成本降到可控。
2. **降采样**：在 480×270 的缓冲上排序，再放大。代价是像素变粗（这本身反而更符合 glitch 美学）。
3. **GPU 并行排序（唯一能全分辨率的路线）**：需要 GPU 上的**稳定**排序算法。注意 bitonic sort 是 pow2 且**不稳定**，重复 key 的顺序会变；正确做法是并行基数排序（LSD radix，配合并行前缀和）。难点在于"不是所有像素都参与排序"——必须在预处理阶段给每个像素算一个可排序的值，把不参与排序的像素编码成"位置保持"的值，排序后再合并分块边界。完整推导见 [Luke Cochrane: Real-Time Pixel Sorting in the Browser](https://lukecochrane.com/blog/pixel-sorting)。

### 真实参考链接

- Kim Asendorf 原始 Processing 脚本（2010，技法源头）：<https://github.com/kimasendorf/ASDFPixelSort>
- 作者主页：<https://kimasendorf.com/>
- satyarth/pixelsort（Python，区间函数/排序函数最完整的一份文档）：<https://github.com/satyarth/pixelsort>
- DavidMcLaughlin208/PixelSorting（C++/openFrameworks，含视频排序与性能对比数据）：<https://github.com/DavidMcLaughlin208/PixelSorting>
- Jeff Thompson 的 Processing 像素排序示例集（原作 2016 教程里推荐的那份）：<https://github.com/jeffThompson/PixelSorting>
- datamoshing.com 教程（mode 0/1/2 与阈值解释，写作时间早、术语原始）：<http://datamoshing.com/2016/06/16/how-to-glitch-images-using-pixel-sorting/>
- Luke Cochrane 的 WebGPU 实时像素排序（2025-05-21，含并行基数排序完整推导）：<https://lukecochrane.com/blog/pixel-sorting>
- p5.js 像素排序教学（ITP ICM 课程，逐行/随机段/亮度分段三级递进）：<https://github.com/itpresidents/icm-help-sessions-2020/blob/master/session-08/session-08-example.md>

---

## 2. Datamosh / Block Displacement 区块位移

**中文名**：数据糊化 / 区块位移 / 宏块错位
**英文名**：Datamoshing / I-frame removal ("melt") / P-frame duplication ("bloom") / Block displacement

### 视觉特征

两种截然不同的形态，别混为一谈：

- **Melt（融化）**：A 镜头的画面留在屏幕上，B 镜头的运动向量作用在它上面 → 上一幕的人脸被下一幕的镜头运动拉扯、涂抹、糊开。特征是**内容旧、运动新**。
- **Bloom（膨胀/拖影）**：同一组运动向量被反复施加 → 运动中的物体不断拖出自己，像油彩被推着走。特征是**平滑的连续拖尾**，不是定格。
- 两者都有一个共同的视觉签名：**块边界**（8×8 / 16×16 宏块），边缘不是平滑的而是台阶状。

区分"定格"和真 bloom：定格是通过复制**已解码画面**实现的（相邻帧差 = 0）；bloom 是复制**P 帧的运动数据**（相邻帧差 > 0，且位移会累积）。

### 真实成因（理解它才知道怎么伪造）

视频编码里 I 帧是完整画面，P 帧只有"从上一画面复制哪块、放到哪、再补一点残差"。删掉 I 帧后，解码器只能把新镜头的运动施加到它缓存里的旧画面上 → melt。复制 P 帧 → 同一组运动重复施加、没有新内容纠正 → bloom。修到下一个 I 帧才结束。

**关键限制**：H.264 因为 B 帧参考未来帧、多参考帧、以及解码器的错误遮掩机制，删 IDR 很可能只得到灰帧或解码失败，而**不是** melt。想要可复现的结果，要用 MPEG-4 Part 2（Xvid）+ `-bf 0`，只有 I/P 帧、P 帧只参考前一帧。

```bash
# 生成适合 moshing 的源：极少 I 帧、无 B 帧
ffmpeg -i input.mp4 -c:v mpeg4 -vtag xvid -qscale:v 4 -g 9999 -bf 0 -an output.avi
```

### Canvas 实现要点（浏览器能做的"近似"）

浏览器拿不到解码器内部的运动向量（除非上 WebCodecs + FFGlitch 那条路），所以做法是**用上一帧当源，按块做偏移采样**：

```js
// src = 上一帧的离屏 canvas；dst = 当前帧
// motion: 从光流/差分/固定方向得到的每块位移向量
const BS = 16;
for (let by = 0; by < H; by += BS) {
  for (let bx = 0; bx < W; bx += BS) {
    const keepPrev = hash(bx, by, frameSeed) < 0.25;   // 只有部分块"卡住"
    if (!keepPrev) continue;
    const [dx, dy] = motion[by/BS][bx/BS];
    dst.drawImage(src, bx, by, BS, BS, bx + dx, by + dy, BS, BS);
  }
}
```

四个决定成败的细节：

1. **源必须是上一帧，不是当前帧**。用当前帧做偏移只是涂抹（smudge），不是 moshing。
2. **位移向量要累积**：同一个块连续 N 帧用同一个向量反复拷贝，就会产生 bloom 的"滑出去"感。每帧重新随机 = 抖动的噪点，不像 moshing。
3. **不要让所有块都卡住**。25%~40% 的块保留上一帧内容就够，全保留 = 画面完全冻死。
4. **块边缘要硬**：`ctx.imageSmoothingEnabled = false`，否则边缘被插值糊掉，宏块签名消失。

WebGL 版本更划算：两张纹理（当前/上一帧）ping-pong，在 shader 里 `cell = floor(uv * blocks)`，用 hash 决定这个 cell 采样当前帧还是上一帧的 UV 加偏移。成本接近零。

### 是否适合逐帧实时渲染

**完全可以，而且是全套里最便宜的之一。** 成本 = 块数 × `drawImage`。1920×1080 / 16px 块 = 120×68 = 8160 块，只画 30% ≈ 2400 次 `drawImage`，WebGL 路径下几乎是零成本。真实 datamosh 反而**不适合实时**（要离线改码流再重编码），这正是它被"伪造"的原因。

### 真实参考链接

- datamosh-toolkit（技术剖析最扎实：AVI/MP4 容器差异、bloom vs smear 的量化验证、propagate 参数）：<https://jesserweigel.github.io/datamosh-toolkit/>
- datamoshing.com 官方教程（Avidemux 逐步操作 + I/P/B 帧解释）：<http://datamoshing.com/type/video/>
- ffmpeg 官方 wiki：Encode/H.264（**GOP / 关键帧间隔的权威实操参考**：`-g` 控制最大 GOP、`-bf 0` 关 B 帧、`-keyint_min`，datamosh 前后处理要用的编码参数都在这里）：<https://trac.ffmpeg.org/wiki/Encode/H.264>
- Wikipedia: Datamoshing（技法分类与历史脉络，快速建立术语坐标用）：<https://en.wikipedia.org/wiki/Datamoshing>
- FFGlitch（在 JS 里直接改写运动向量/量化参数，datamosh 的正统工具）：<https://ffglitch.org>
- Shaun Ray I-frame datamoshing 视频教程：<https://www.youtube.com/watch?v=fw5QnRevqX4>
- glitchology 的 Avidemux & FFmpeg 完整流程（含故障排查表）：<https://glitchology.com/datamoshing/>

---

## 3. Scanline Tearing / Slice Displacement 扫描线撕裂

**中文名**：扫描线撕裂 / 条带位移 / 横条错位
**英文名**：Scanline tearing / Slice displacement / Line displacement / Sync error

### 视觉特征

画面被若干水平条带切开，某些条带整体左右平移，条带内部内容完全不变（**不变形、不模糊**），边缘是硬切。真实来源是行同步（horizontal sync）丢失——所以条带高度不均匀、只占少数、且出现是**突发式**的（一瞬间抖两下，然后恢复干净）。

它是全套技法里"性价比最高"的一个：**极低的成本，极高的可辨识度**。

### Canvas 实现要点

```js
const slices = 24;            // 条带数（注意：不是"撕裂数"）
const amp = 30;               // 最大位移像素
for (let i = 0; i < slices; i++) {
  const y0 = Math.round(i * H / slices);
  const y1 = Math.round((i + 1) * H / slices);
  const h  = y1 - y0;
  // 只有约 15~30% 的条带参与撕裂
  const r  = hash(i, frameSeed);
  if (r > 0.22) { dst.drawImage(src, 0, y0, W, h, 0, y0, W, h); continue; }
  const dir = hash(i, frameSeed + 13) * 2 - 1;      // -1 ~ 1
  const dx  = Math.round(dir * r * amp);
  dst.drawImage(src, 0, y0, W, h, dx, y0, W, h);
}
```

WebGL 里就一行 UV 偏移（这是 canvasui 的 glitch shader 实际写法）：

```glsl
float band = floor(uv.y * uSlices);
float pick = hash12(vec2(band, uSeed));
float tear = step(1.0 - 0.3 * min(e, 1.0), pick);   // 只有 30% * 强度 的条带触发
float dir  = hash12(vec2(band, uSeed + 13.0)) * 2.0 - 1.0;
guv.x += tear * dir * e * uShift / uResolution.x;
```

四个关键点：

1. **条带高度必须不均匀**。等分 24 条是"滤镜"，随机高度（用 hash 累加）才是"故障"。
2. **只有少数条带动**。全动 = 整个画面在抖，看不出撕裂。
3. **位移要按帧随机，但不能帧帧全变**。用 `floor(time * 12)` 这种"12fps 的随机种子"，让撕裂保持 2~5 帧再换——更强的机械故障感。
4. **突发式出现**。设一个 `interval` 和 `duration`（比如每 3 秒来一次、持续 0.4 秒），中间画面必须完全干净。持续不停闪 = 视觉噪音，也不符合真实信号故障。
5. **职业习惯**：撕裂的同时通常伴随一两条"过亮/全白的行"——那就是真正的同步丢失那一行。

### 是否适合逐帧实时渲染

**完全适合。** Canvas2D 的 `drawImage` 裁切重绘是硬件加速的，1080p 24 条 ≈ 0.2ms。WebGL 版本零成本。CSS 路线也可以（多层伪元素 + `clip-path: inset()` 动画），见第 13 节的 Codrops 项目。

### 真实参考链接

- canvasui Glitch（上面那段 shader 的来源，含 `slices/shift/rgbShift/blocks/noise` 完整参数定义，WebGL + WebGPU 双实现）：<https://canvasui.dev/docs/components/glitch>
- Codrops CSSGlitchEffect（纯 CSS `clip-path` 多层错切，零 JS）：<https://github.com/codrops/CSSGlitchEffect>
- Isonimus/glitch-js（TypeScript，`Effects.slice()` 用水平切片克隆层做位移）：<https://github.com/Isonimus/glitch-js>
- glitchGL（`lineDisplacement` / `syncErrorFreq` / `syncErrorAmount` 三个参数就是条带撕裂与行同步错误）：<https://github.com/naughtyduk/glitchGL>

---

## 4. RGB Channel Shift 通道分离

**中文名**：通道分离 / RGB 错位 / 色差
**英文名**：RGB channel shift / Chromatic aberration / Channel split / RGB split

### 视觉特征

物体边缘出现青-红或黄-蓝色边，像廉价镜头色差或复合视频的色度延迟。**只有边缘有明显偏移、平坦区域看不出来**——这一点决定了它必须在"有对比度的边界"上才有效，纯色块上是看不见的。叠加在文字上时效果最强（字形边缘密集）。

### Canvas 实现要点

三条路，按代价从低到高：

**路 1：三次偏移绘制 + 加色混合（最省，推荐）**

```js
out.globalCompositeOperation = 'lighter';   // 或 'screen'
// R 通道：用 CSS filter 把副本染红（或预生成通道贴图）
out.filter = 'url(#redOnly) brightness(1)'; // 见下方 SVG feColorMatrix
out.drawImage(src,  d, 0);
out.filter = 'url(#greenOnly)';
out.drawImage(src,  0, 0);
out.filter = 'url(#blueOnly)';
out.drawImage(src, -d, 0);
```

配一个静态 SVG 滤镜（放在页面里，只定义一次）：

```html
<svg style="position:absolute;width:0;height:0">
  <filter id="redOnly"><feColorMatrix type="matrix"
    values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"/></filter>
</svg>
```

**路 2：直接改 ImageData（最精确，但慢）**

```js
// 必须从「拷贝」读，从原数组写；否则后面的像素会读到已经被改过的值 → 链式污染
out32[i] = (src32[i + d] & 0x00FF00FF) | (src32[i] & 0x0000FF00);
```

**路 3：WebGL，三次采样（最优）**

```glsl
float split = uRgbShift * e / uResolution.x;
vec4 c = page(guv);
float r = page(guv + vec2(split, 0.0)).r;
float b = page(guv - vec2(split, 0.0)).b;
vec4 col = vec4(r, c.g, b, c.a);
```

关键点：

- **偏移方向可以是各向同性的**：水平分离（左红右青，最常见的"信号错位"）和径向分离（离中心越远偏移越大，是"镜头色差"）是两种不同的联想。想要"数字故障"用水平，想要"廉价镜头"用径向。
- **偏移量别超过 4~8px**（1080p 下）。超过就变成"重影"而不是"色差"。
- **Cb/Cr 分离比 RGB 分离更像 VHS**：把亮度(Y)和色度(Cb/Cr)分开，只位移色度并做水平模糊，就是复合视频的 chroma bleed（RetroTube 就是这么做的）。

### 是否适合逐帧实时渲染

**完全适合。** WebGL 三次纹理采样 = 免费。Canvas2D 的 `filter` + `drawImage` 路线在 1080p 也是亚毫秒级（GPU 合成）。只有全分辨率 ImageData 逐像素那条路（路 2）需要克制——1080p 是 200 万像素，单帧 2~6ms，且强依赖 CPU。

### 真实参考链接

- three.js `RGBShiftShader`（最经典的实现，`amount` / `angle` 两个 uniform）：<https://github.com/mrdoob/three.js/blob/master/examples/jsm/shaders/RGBShiftShader.js>
- canvasui Glitch（`rgbShift` 与撕裂共用同一个突发包络 `e`，因为真实故障里两者是同时发生的）：<https://canvasui.dev/docs/components/glitch>
- RetoTtube（Chrome 扩展，YUV 分离 + chroma 水平模糊 + 延迟，VHS 色度爬行）：<https://github.com/shiiraz/RetroTube>
- stefanlegg/crt-fx（`chromatic: { offset: 2.5 }` 一行参数，另有 10 种磷光掩模）：<https://github.com/stefanlegg/crt-fx>
- MDN `mix-blend-mode`（`screen`/`lighter` 的选择会明显改变观感）：<https://developer.mozilla.org/en-US/docs/Web/CSS/mix-blend-mode>

---

## 5. Vertical Roll / VHS Tracking 垂直滚动

**中文名**：垂直滚动 / 走带跟踪错误 / VHS 追踪带
**英文名**：Vertical roll / VHS tracking error / Head-switching noise / Tape wave

### 视觉特征

VHS 是**一整套**同时发生的现象，不是单一效果。做全套才有味道：

| 子效果 | 视觉 | 成因 |
|--------|------|------|
| vertical roll | 整幅画面缓慢向上或向下滚动 | 场同步丢失，画面在自己上面滚圈 |
| tape wave | 画面整体缓慢的横向蛇形波动 | 磁带张力不均 |
| tracking jitter | 每行细碎的横向抖动 | 磁头跟踪误差 |
| tape crease | 一道横向的"折痕带"缓慢扫过画面 | 磁带物理折痕 |
| head-switching noise | **画面最底部**约 2% 高度的一条撕开的噪声带 | 换头期间的空白期 |
| AC beat | 缓慢滚动的亮度起伏 | 电源频率与场频拍频 |
| chroma bleed | 色彩向右拖出 | 色度副载波延迟 |
| dropout | 随机短促的白/黑横线 | 磁粉脱落 |

### Canvas 实现要点

```js
// 1) 垂直滚动：两次 drawImage 就够了（y 和 y-H）
const roll = (t * rollSpeed) % H;
dst.drawImage(src, 0, 0, W, H - roll, 0, roll, W, H - roll);  // 下半部分下移
dst.drawImage(src, 0, H - roll, W, roll, 0, 0, W, roll);      // 滚出去的部分接回顶部

// 2) 逐行 jitter：一行一画，dx = (noise(y, t) - 0.5) * 0.01 * W
//    注意噪声在 y 方向要连续，否则行与行之间会"碎裂"（那是另一种效果，不是 VHS）

// 3) head-switching 带：底部 2% 直接用噪声+色带覆盖
const bandH = Math.max(2, H * 0.02);
for (let y = H - bandH; y < H; y++) {
  const dy = (y - (H - bandH)) / bandH;
  dst.drawImage(src, 0, y, W, 1, (Math.random()-0.5) * 40 * dy, y, W, 1);
}
// 再叠一条半透明的白/洋红色带
dst.fillStyle = 'rgba(255,255,255,0.6)'; dst.fillRect(0, H - bandH, W, bandH);
```

WebGL 版本（canvasui VHS 的实际写法，可直接抄结构）：

```glsl
// tape wave：整幅横向蛇形
uvn.x += (noise(vec2(uvn.y, t)) - 0.5) * 0.005 * uWave;
// jitter：逐行细抖
uvn.x += (lineNoise - 0.5) * 0.01 * uJitter;
// head-switching：越靠底部越强，同时做色度旋转（col.yzx）模拟色带
float snPhase = smoothstep(max(uSwitchHeight,1e-4), 0.0, uvn.y) * uSwitching;
uvn.y += snPhase * 0.3;
uvn.x += snPhase * ((lineNoise - 0.5) * 0.2);
col = mix(col, col.yzx, clamp(snPhase, 0.0, 1.0));
```

关键点：

- **head-switching 带必须在底部**，而且要有明显的"水波"曲率（不是直线，是微微起伏的边界）。位置错了，任何做过摄像机的人一眼就看出是假的。
- **滚动速度要慢**。真实垂直滚动是 1~3 秒滚一圈。快了就变成"卷轴"像。
- **逐行 jitter 的噪声在垂直方向必须连续**。用 `noise(vec2(uv.y * 100.0, t * 10.0))` 而不是 white noise，否则行与行之间会碎成噪点。
- **别忘 DC 偏移**：VHS 画面整体偏亮、对比度低、饱和度略低，加一层浑浊的亮度/饱和度调整，比任何特效都更能骗过眼睛。

### 是否适合逐帧实时渲染

**完全适合。** Canvas2D 版本：2 次全屏 `drawImage` + 约 1080 次单行 `drawImage`（如果做逐行 jitter）。逐行部分是主要成本，如果只需滚动 + 底部带，成本几乎为零。WebGL 版本全部免费。

### 真实参考链接

- felixturner/bad-tv-shader（**垂直滚动 + 水平失真的标准参考**，`rollSpeed` / `distortion` / `distortion2` / `speed` 四个 uniform 就是这套；演示页：<https://codyvb.github.io/static/>）：<https://github.com/felixturner/bad-tv-shader>
- canvasui VHS（上面那段 shader 的来源；`wave/jitter/crease/switching/switchingHeight/acBeat/grain/scanlines` 参数完整，含逐行噪声的 CPU 侧噪声实现）：<https://canvasui.dev/docs/components/vhs>
- shiiraz/RetroTube（真实产品级的 VHS pass 拆解：scanlines 跟随 `video.currentTime` 而非自由时钟、luma 竖直方向模糊模拟 head-gap smear、色度向右延迟模糊、时间基漂移的小幅垂直摆动）：<https://github.com/shiiraz/RetroTube>
- stefanlegg/crt-fx（`vhs` / `consumer90s` / `terminal` 等 10 个预设，含 color bleed）：<https://github.com/stefanlegg/crt-fx>
- powershot-threejs（analog tape 模式：chroma bleed、tracking errors、dropouts）：<https://github.com/cl0nazepamm/powershot-threejs/>

---

## 6. Sine Wave Distortion 正弦扭曲

**中文名**：正弦扭曲 / 水波纹 / 热浪扭曲
**英文名**：Sine wave distortion / Ripple / Wobble / Warp / Wave equation distortion

### 视觉特征

画面像水面或热空气一样横向起伏，起伏是**连续的、平滑的**，行与行之间的相位逐渐变化。这是它和 scanline tearing 的核心区别：**撕裂是硬切（条带内不变），正弦是软变（连续变形）**。

单独用纯正弦会显得很规则、很假；真实的模拟信号失真通常是**两个不同频率的正弦叠加**（基频 + 谐波），或者幅度随 y 变化。

### Canvas 实现要点

```js
// 逐行偏移：dx 是 y 的连续函数
for (let y = 0; y < H; y++) {
  const ph = y * freq + t * speed;
  // 两个正弦叠加：第二个是谐波，用来打散规则感
  const dx = amp * (Math.sin(ph) * 0.7 + Math.sin(ph * 2.7 + 1.3) * 0.3)
           * falloff(y);   // falloff 让幅度沿 y 变化，别让整幅摆动幅度一样
  dst.drawImage(src, 0, y, W, 1, dx, y, W, 1);
}
```

WebGL：

```glsl
guv.x += sin(uv.y * uFreq + uTime * uSpeed) * uAmp;
// 加一层高频小幅度，做成"信号 + 噪波"
guv.x += (noise(vec2(uv.y * 40.0, uTime * 3.0)) - 0.5) * uAmp * 0.25;
```

关键点：

- **逐行 drawImage 是"能跑但吃 CPU"的量级**：1080 行 = 1080 次调用/帧。在低端设备上是主要瓶颈。**正确做法是在低分辨率离屏缓冲上做**（比如 1/2 或 1/4 尺寸），再放大回来——反正失真正好会让画面变模糊，看不出分辨率损失。
- **幅度要沿 y 变化**：`amp * sin(y/H * π)` 这种"中间大两头小"，或者"顶部大底部小"（模拟屏幕边缘失真），比均匀幅度像得多。
- 如果做成"波纹从某点扩散"，进入波纹方程（ping-pong 迭代）的领域：`wave = (top + left + right + bottom) - 4*center`，然后 `wave *= damping`。这是真的求解二维波动方程，会有真实的传播、反射、干涉。

### 是否适合逐帧实时渲染

**WebGL：完全适合。** 一行代码，零成本。
**Canvas2D：可做但需优化。** 逐行偏移是主流做法，1080 行在桌面 Chrome 上大约 2~5ms/帧（可以接受），手机上会掉帧。加上降采样缓冲后完全没问题。

### 真实参考链接

- canvasui Ripple（**波纹方程的 GPU 完整实现**：`amplitude/speed/wavelength/rings/decay/refraction/dispersion/shine`，含最多 12 个并发波纹的 uniform array 与 CPU 侧的生命周期剪枝；梯度投影 + color-dodge 光泽）：<https://canvasui.dev/docs/components/ripple>
- m1ckc3s/ripple（带噪声扰动的波前过渡：Gaussian 包络定义波前带、FBM 值噪声让波前碎裂成云团状、径向位移、色差采样；附完整的 uniform 控制面板说明）：<https://github.com/m1ckc3s/ripple>
- glslcanvas 多缓冲示例（ping-pong 波动方程 + 鼠标交互，`texture2D(u_buffer1, ...)` 的邻居采样写法）：<https://context7.com/patriciogonzalezvivo/glslcanvas/llms.txt>
- MDN `feTurbulence`（用 SVG 滤镜做无 shader 的噪声扭曲，`baseFrequency` 控制粗糙度，`seed` 动画化）：<https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/feTurbulence>

---

## 7. Dither / Halftone / Bayer 抖动网屏

**中文名**：抖动 / 网点 / 有序抖动
**英文名**：Ordered dithering / Bayer matrix dithering / Halftone / Error diffusion

### 视觉特征

用点阵的**密度**来模拟中间灰阶。1-bit 输出（只有黑白）时，屏幕上的"灰"是黑点白底的统计平均。看得见规则的网纹（Bayer）或有机的颗粒（blue noise / 误差扩散）。这是 8-bit 时代、点阵打印机、Obra Dinn 的整个视觉语言。

### 三条路线的本质区别

| 类型 | 原理 | GPU 可行 |
|------|------|----------|
| **有序抖动 / Bayer** | 每个像素对照一张**固定阈值矩阵**里的值决定取哪个色阶。像素之间**互相独立** | ✅ 可在 shader 里做 |
| **白噪声抖动** | 阈值换成随机数。会有明显的聚簇和空洞（看起来"脏"） | ✅ 但不好看 |
| **蓝噪声抖动** | 阈值矩阵换成蓝噪声（高频能量高、低频被压低）。聚簇和空洞明显减少，观感最自然 | ✅ 只是生成蓝噪声较贵 |
| **误差扩散（Floyd–Steinberg）** | 量化后把误差按扩散矩阵分给**还没处理的邻居** | ❌ **串行依赖，无法并行** |
| **Riemersma** | 沿 Hilbert 曲线遍历，用误差序列而非扩散矩阵 | ❌ 同样串行 |

**这是本节最重要的一句话**：Floyd–Steinberg 和 Riemersma 都是串行的，做不了实时全屏 shader。要实时就用有序抖动（Bayer 或蓝噪声）。

### Bayer 矩阵与实现

```js
// 4x4 Bayer 阈值矩阵（值域 0..15，使用时 /16 归一到 [0,1)）
const BAYER4 = [
   0,  8,  2, 10,
  12,  4, 14,  6,
   3, 11,  1,  9,
  15,  7, 13,  5,
];
// 8x8 同理，由 4x4 递归构造；或用位交错公式在运行时算，省一张表

// 量化 + 抖动（先算查表，别在像素循环里做除法）
const Q = 4;                                  // 每通道 4 级
for (let y = 0; y < H; y++) {
  for (let x = 0; x < W; x++) {
    const th = (BAYER4[(y & 3) * 4 + (x & 3)] + 0.5) / 16;  // 归一到 [0,1)
    // 先加阈值偏移再量化，等价于"把误差空间均匀撒开"
    const v = Math.floor((lum + (th - 0.5) / (Q - 1)) * (Q - 1)) / (Q - 1);
    ...
  }
}
```

GLSL（libretro 那份的实现，直接可用）：

```glsl
float find_closest(int x, int y, float c0) {
  int dither[8][8] = { {0,32,8,40,2,34,10,42}, {48,16,56,24,50,18,58,26}, /* ...8x8... */ };
  float limit = (dither[x][y] + 1) / 64.0;
  return c0 < limit ? 0.0 : 1.0;
}
void main() {
  vec2 xy = vTexCoord * outsize.xy;
  int x = int(mod(xy.x, 8.0));
  int y = int(mod(xy.y, 8.0));
  // 对 R/G/B 分别做，或对灰度做
}
```

关键点：

- **阈值归一化要除以 n²（不是 n²-1），并加 0.5 偏移**。这样阈值集合正好是 `(i+0.5)/n²`，均值恰为 0.5，不会出现"整体偏亮/偏暗"。8x8 用 `(dither+1)/64.0` 就是这个意思。
- **量化要在显示空间做，不要在 linear 空间做**。在 linear-light 上量化会让中间调在编码后明显偏亮。正确顺序：`linearToSrgb` → dither → quantize。
- **必须叠上抖动才有复古味**。只做 posterize 不抖动 = 硬色带（那是第 8 节的效果），叠加抖动才是"像素画"。
- **Halftone（真网点）**和 dither 不是一回事：halftone 是把像素坐标旋转约 45° 后算网格坐标，和亮度比较；网点大小随亮度变化，而不是固定阈值的棋盘花样。做印刷感用 halftone，做 8-bit 感用 Bayer。

### 是否适合逐帧实时渲染

**有序抖动（Bayer / 蓝噪声）：完全适合。** 每像素独立，shader 里两行。
**误差扩散（Floyd–Steinberg / Riemersma）：不适合实时全屏。** 串行依赖，只能离线、静态图、或极小分块降采样。这是硬约束，不是优化问题。

### 真实参考链接

- Surma: Ditherpunk（**本节最该读的一篇**。把白噪声/有序/蓝噪声/误差扩散/Riemersma 全部串起来讲，并且明确说清"误差扩散因为串行所以不适合 shader"，还解释了为什么 Obra Dinn 只能用有序抖动。带可交互 demo）：<https://surma.dev/things/ditherpunk/> ｜ demo：<https://surma.dev/lab/ditherpunk/>
- libretro/glsl-shaders 的 8×8 Bayer 实现（RetroArch 用，上面那段 GLSL 的出处，作者 Martins Upitis）：<https://github.com/libretro/glsl-shaders/blob/master/dithering/shaders/bayer-matrix-dithering.glsl>
- Codrops: Building a Real-Time Dithering Shader（用 `postprocessing` 库把抖动做成后处理 Effect，含 `gridSize` / `pixelSizeRatio` / `grayscaleOnly` / `invertColor` 参数与完整 TS 类）：<https://tympanus.net/codrops/2025/06/04/building-a-real-time-dithering-shader/>
- Maxime Heckel: The Art of Dithering and Retro Shading for the Web（R3F 后处理路线，从白噪声 → Bayer → 蓝噪声 → 色彩量化（hue-lightness 调色板采样）→ 像素化 → CRT 掩模 → 扫描线，一路做到 CRT 全套）：<https://blog.maximeheckel.com/posts/the-art-of-dithering-and-retro-shading-web/>
- The Coding Train #90 Floyd–Steinberg Dithering（串行误差扩散的最直观教学，Processing）：<https://thecodingtrain.com/challenges/90-dithering>
- bdip-core 的 WGSL 实现（4×4 Bayer + `strength` 混合回原图，含矩阵归一化与 `levels` 钳制到 [2,256] 的边界处理）：<https://docs.rs/crate/bdip-core/latest/source/shaders-wip/shaders/console_16bit/console_16bit_dither.wgsl>
- @vshaders/dither（**用位交错公式运行时构造 Bayer 矩阵**而不是存字面量；`bayer2/bayer4/bayer8` + `ditherQuantize3`，含"阈值恰好是 (i+0.5)/n² 的排列"的数学保证）：<https://www.vshaders.com/docs/dither>
- Godot Shaders: Quantized Bayer dither（多级量化的极简写法：`(step(t, fract(COLOR*g)) + floor(COLOR*g))/g`）：<https://godotshaders.com/shader/quantized-bayer-dither/>

---

## 8. Bitcrush / Posterize 位深压缩

**中文名**：位深压缩 / 色阶压缩 / 海报化
**英文名**：Bitcrush / Posterize / Color quantization / Bit depth reduction

### 视觉特征

颜色跳台阶：平滑渐变被压成若干条硬色带（banding），暖色区域出现同心「梯田」，暗部整片糊成一块。和 dither 的区别：**dither 是把台阶藏进网点里，bitcrush 是把台阶赤裸裸露出来**。两者叠用（先量化后抖动，或先抖动后量化）才是完整的复古链路。

### 三种量化粒度

1. **通道位数削减**：`v = v & 0xE0`（保留高 3 位 → 8 级/通道）。最像硬件限制，速度最快。
2. **色阶数削减**（posterize）：`levels = 5` 时 `v = floor(v/255 * (levels-1)) / (levels-1) * 255`。比位数削减更可控，适合做「海报」质感。
3. **调色板量化**：把颜色映射到一组有限的调色板（4 色、Game Boy 绿、CGA 16 色）。最强风格化，但需要最近邻搜索（可以用 32³ 的 3D LUT 近似，成本很低）。

### Canvas 实现要点

```js
// 关键：预计算 256 项查找表，避免像素循环里做除法
const LEVELS = 5;
const LUT = new Uint8Array(256);
for (let i = 0; i < 256; i++) LUT[i] = Math.round(Math.round(i / 255 * (LEVELS - 1)) / (LEVELS - 1) * 255);

// 逐像素：三次查表 + 一次 Uint32 写回
const src = new Uint32Array(imageData.data.buffer);
for (let i = 0; i < src.length; i++) {
  const v = src[i];
  src[i] = (v & 0xFF000000)
         | (LUT[v & 0xFF] << 16)          // 注意端序：小端下低字节是 R
         | (LUT[(v >> 8) & 0xFF] << 8)
         | (LUT[(v >> 16) & 0xFF]);
}
```

**CSS / SVG 路线（不用写一行 canvas 代码）**：

```html
<filter id="posterize">
  <feComponentTransfer>
    <feFuncR type="discrete" tableValues="0 0.25 0.5 0.75 1"/>
    <feFuncG type="discrete" tableValues="0 0.25 0.5 0.75 1"/>
    <feFuncB type="discrete" tableValues="0 0.25 0.5 0.75 1"/>
  </feComponentTransfer>
</filter>
```

`type="discrete"` 就是 posterize，`type="table"` 是任意映射曲线。可以用 `filter: url(#posterize)` 直接套到任意 DOM 元素上。

关键点：

- **别在像素循环里算 `Math.round(v/255*4)/4*255`**。查表之后成本降一个数量级。
- **顺序很重要**：先 bitcrush 再 dither = 网点覆盖色带（推荐）；先 dither 再 bitcrush = 抖动被二次量化毁掉，网纹变成斑块。
- **亮度和色度可以不同位深**：真实模拟设备里 luma 通常比 chroma 位深高（人眼对亮度更敏感）。亮度留 5 位、色度压到 2 位，比全通道统一压缩更像。
- **色带本身可以被利用**：保留色带、只压暗部（或只压某个亮度区间），会有"局部故障"的层次感，比全屏压一遍有设计感。

### 是否适合逐帧实时渲染

**完全适合，而且是全套里最便宜的一个。** 查表 + Uint32 写回，1080p 约 1~3ms。WebGL 里就是一行 `floor(v * levels) / (levels - 1)`。SVG `feComponentTransfer` 路线更是完全免费（GPU 合成）。

### 真实参考链接

- MDN `feComponentTransfer`（`type="discrete"` / `"table"` 的完整语义与示例）：<https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/feComponentTransfer>
- @vshaders/dither 的 `ditherQuantize3`（`levels` 计数语义与"量化在哪个色彩空间做"的坑，含 `levels <= 1` 直接返回原值的边界保护）：<https://www.vshaders.com/docs/dither>
- glitchGL（`bitCrushDepth: 4.0` 就是这一节，和 `signalDropoutFreq` / `datamoshStrength` 组成完整的故障模块）：<https://github.com/naughtyduk/glitchGL>
- Maxime Heckel 文章的「Color quantization」章节（从量化公式到任意调色板的 hue-lightness 最近邻搜索）：<https://blog.maximeheckel.com/posts/the-art-of-dithering-and-retro-shading-web/>
- bdip-core console_16bit 实现（`color_levels` 钳制到 [2,256]，`round` 而非 `floor`，偏移量缩放到"±0.5 个量化步"）：<https://docs.rs/crate/bdip-core/latest/source/shaders-wip/shaders/console_16bit/console_16bit_dither.wgsl>

---

## 9. Ghost Echo / Frame Trails 残影

**中文名**：残影 / 拖尾 / 回声
**英文名**：Ghost echo / Frame trails / Afterimage / Feedback loop / Temporal accumulation

### 视觉特征

运动物体后面跟着一串逐渐变暗的副本，越早越淡，衰减是指数式的。静止画面会缓慢蒸发（"烧屏"感）。如果残影同时被偏移/旋转/缩放，就变成万花筒隧道或螺旋——这是**整个 glitch 体系里视觉上最"贵"的一个效果，成本却最低**。

### Canvas 实现要点（两种，代价差一个量级）

**做法 A：不清屏，用半透明覆盖（一行代码）**

```js
function frame() {
  // 注意：不要 clearRect！用半透明填充代替
  ctx.fillStyle = 'rgba(0, 0, 0, 0.08)';   // 0.08 → 长拖尾；0.3 → 短促；0.01 → 几乎不消散
  ctx.fillRect(0, 0, W, H);
  ctx.drawImage(object, x, y);             // 只画"当前运动的东西"
  requestAnimationFrame(frame);
}
```

这个 0.08 就是**唯一的创作参数**：每帧亮度乘 0.92，10 帧后剩 0.43，100 帧后剩 0.0003。

**做法 B：离屏缓冲乒乓（可控性更高）**

```js
prev.ctx.drawImage(cur, 0, 0);            // 上一帧内容进 prev
cur.ctx.globalAlpha = 0.15;               // 上帧的"残留权重"
cur.ctx.drawImage(prev, 0, 0);
cur.ctx.globalAlpha = 1.0;
cur.ctx.drawImage(object, x, y);          // 再画当前内容
```

WebGL 版本：两个 FBO 乒乓，`prev = texture(prevFrame, uv + offset) * damp + current`。**不能读写同一张纹理**——GPU 是流水线的，读写同一纹理会出现部分像素读到新值、部分读到旧值的竞态，结果是不可预期的垃圾。

### 关键点

| 参数 | 效果 |
|------|------|
| `damp = 0.97` | 长拖尾，缓慢消散 |
| `damp = 0.90` | 短促回弹 |
| `damp = 0.999` | 几乎不消散，画面逐渐被幽灵填满 |
| `damp = 0.5` | 基本只有一层淡淡回声 |
| UV 加固定偏移 | 拖尾有方向，像湿油漆被拖过 |
| UV 加噪声偏移 | 有机消融，笔触缓慢溶散 |
| 采样前一帧时做**旋转+缩放** | 万花筒隧道（scale < 1 向内螺旋，= 1 同心环，> 1 会爆） |

- **缩放因子是命门**：`scale = 0.995` 向内螺旋；`scale = 1.0` 只旋转 → 同心环；`scale > 1.0` 会快速把噪声放大到满屏爆掉。
- **反馈会"跑干"信息**：只靠自己当输入的反馈最终会收敛到单一颜色或同心环（这是 Codeberg 那个 Canvas-Feedback 项目明确指出的局限）。要维持生命力，必须**每帧从外部再注入一点新内容**（画一个点、喂一帧视频），像摄像机永远在引入新画面一样。
- **和 11 号（噪点）的化学作用**：把噪声也一起喂进反馈回路，画面会自己长出有机的纹理，不需要任何额外素材。

### 是否适合逐帧实时渲染

**完全适合，这是性价比之王。** 做法 A 的成本是一次 fillRect；WebGL ping-pong 是两个 FBO 切换 + 一次纹理采样。三维引擎里它就是标准后处理（three.js `AfterimagePass`，`damp` 参数就是上面那个数字）。

### 真实参考链接

- three.js `AfterimagePass`（`damp` uniform 的标准实现，直接可读源码）：<https://github.com/mrdoob/three.js/blob/master/examples/jsm/postprocessing/AfterimagePass.js> ｜ demo：<https://threejs.org/examples/#webgl_postprocessing_afterimage>
- WebGL Fundamentals: Image Processing Continued（**ping-pong FBO 的标准教学**，含 `createAndSetupTexture` / `setFramebuffer` 的完整代码和"为什么要两个纹理"的解释）：<https://webglfundamentals.org/webgl/lessons/webgl-image-processing-continued.html>
- catseye/Canvas-Feedback（1980 年代 Doctor Who 片头那种模拟视频反馈：复制 → 旋转 r 度 → XY 缩放 → 贴回 → r 递增。也诚实说明了"会跑干信息、最终收敛"的局限）：<https://codeberg.org/catseye/Canvas-Feedback>
- shader feedback 教程（从 FBO 到衰减到螺旋隧道的递进，含 `prev.rgb * 0.97` 的逐帧数值演算）：<https://ecency.com/@femdev/learn-creative-coding-36-shader-feedback-loops-and-trails>
- glitchGL（`frameGhostAmount: 0.3` 就是帧幽灵；`stutterFreq` 是"卡帧"，和残影是两种不同的时间故障）：<https://github.com/naughtyduk/glitchGL>

---

## 10. Mirror Slice 镜像切片

**中文名**：镜像切片 / 折叠镜像 / 万花筒
**英文名**：Mirror slice / Mirror fold / Kaleidoscope / Dihedral symmetry

### 视觉特征

画面被镜像复制，出现对称轴；单轴镜像 = 折叠；多轴 + 角度折叠 = 万花筒（D_N 二面体对称）。**关键区分**：镜像切片不一定是对称的漂亮图案——把镜像做**偏移**（镜轴不在画面中心、或者镜像副本被错位叠加），就得到"画面被折过来压在另一块上"的故障感，而不是装饰性的万花筒。

### Canvas 实现要点

```js
// 单轴镜像：drawImage 支持负宽高，比 transform 更省一次状态切换
ctx.drawImage(src, 0, 0, W, H, 0, 0, W, H);                    // 正常的一半
ctx.save();
ctx.translate(W, 0);
ctx.scale(-1, 1);                                              // X 轴翻转
ctx.drawImage(src, 0, 0, W, H, 0, 0, W, H);                    // 镜像的一半
ctx.restore();

// N 重对称（D_N 二面体）：N 个旋转 × N 个镜像
const SEG = 8;
for (let s = 0; s < SEG; s++) {
  for (const flip of [1, -1]) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((s / SEG) * Math.PI * 2);
    ctx.scale(1, flip);        // flip 的这行就是把"风车"变成"万花筒"的那一步
    ctx.translate(-cx, -cy);
    ctx.drawImage(src, 0, 0);
    ctx.restore();
  }
}
```

WebGL 路线更优雅——**极坐标角度折叠**，这是唯一"每个像素只采一次样"的做法：

```glsl
vec2 p = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
float r = length(p);
float a = atan(p.y, p.x);
float sector = 6.2831853 / uSegments;
float af = abs(mod(a, sector) - sector * 0.5);   // 折叠到单个扇区，并在中线处镜像
vec2 q = vec2(cos(af), sin(af)) * r;             // 折叠后的采样坐标
vec3 col = texture(uTex, q * 0.5 + 0.5).rgb;
```

关键点：

- **`abs(mod(a, sector) - sector/2)` 这一步就是镜像**。少了 `abs` 就只是旋转重复（风车），加了 `abs` 才是真正的镜像（万花筒）。这是整个技法的核心一行。
- **中心 r = 0 是奇点**：角度在那里没有定义。必须钳制（中心留一个安静的小圆盘，或平滑过渡到固定采样点），否则会出现一个针尖状的噪点或极锐的风车。且阈值要**分辨率无关**。
- **接缝处理**：正确折叠的相邻扇区位置是连续的（虽然导数方向相反），但纹理过滤和高频内容仍可能露出细缝。优先办法是降低源频率 / 移动采样窗口 / 用导数感知的过滤，而不是加大软掩模（会变成一圈光晕）。
- **WebGL 里还有一条偷懒路线**：`gl.MIRRORED_REPEAT` 纹理环绕模式，配合 UV 被取整到整数格，可以得到硬边的镜像平铺，代价为零。
- **和撕裂叠加**："镜像切片"作为 glitch 用时，镜像轴要跟着 scanline tearing 一起跳——一半画面正常、另一半被镜像错位，那种"接错线"的感觉比对称图案更 glitch。

### 是否适合逐帧实时渲染

**完全适合。** 负宽 `drawImage` 是硬件加速的；WebGL 角度折叠是每像素一次采样（比第 6 节的正弦还便宜）。这是全套里质量/成本比最高的一项。

### 真实参考链接

- Carmen Ansio: The kaleidoscope is a mirror trick（**纯 Canvas2D 的完整实现，代码短且可运行**：`rotate(s/SEG*2π)` + `scale(1, flip)` 的双循环，配 `globalCompositeOperation='lighter'` 的加色叠加和半透明洗屏的衰减。也解释了为什么纯 CSS 做不了——CSS 只能合成已存在的盒子，不能持续重绘刚画的东西）：<https://www.carmenansio.com/articles/kaleidoscope-symmetry-canvas/>
- typeshade: Kaleidoscope 示例（**同一段折叠逻辑同时给出 WGSL 与 GLSL ES 3.00 输出**，含 `fbm` 噪声、`palette` 余弦调色板、vignette；可直接对照检查 `mod` 在负角度下的跨语言差异）：<https://typeshade.dev/guide/examples/kaleidoscope/>
- JP Casabianca: Kaleidoscope Shader: Build a Symmetry Lens（**工程化程度最高的一篇**：极坐标折叠 + 扇区镜像的数学、用"角度/半径灰度诊断图"先验证几何再接纹理、中心奇点的处理策略、接缝诊断 heatmap、CPU 侧 fold 函数作为一致性 oracle 的单元测试）：<https://jpcasabianca.com/journal/kaleidoscope-shader/>
- zebiv-code/kaleidoscope（WebGL2，真实乐器模拟：可透射的玻璃碎片、斜面高光、光学色散、目镜边缘；Symmetry 3–16 折）：<https://github.com/zebiv-code/kaleidoscope/>
- SuperHi: Shaders for the Web — Kaleidoscope（从"采样纹理 → 用半径和角度重采样 → 改变采样角度 → 处理 canvas 像素化和 resize"的循序教学）：<https://www.superhi.com/catalog/shaders-for-the-web/kaleidoscope>

---

## 11. Static Noise 噪点

**中文名**：噪点 / 雪花 / 静电噪声 / 颗粒
**英文名**：Static noise / TV static / Grain / Hash noise

### 视觉特征

三种不同频率的噪点，混用才有层次：

- **白噪点**：满屏细密的随机点，像没信号的电视雪花。亮度均值偏中灰。
- **颗粒（grain）**：叠加在原图上的稀疏扰动，添加 ±0.5 的随机偏移。这是电影/胶片质感，不是雪花。
- **行闪 / dropout**：稀疏的整行亮线或暗线，一帧就消失。这是**间断**噪声，不是连续噪声。

### Canvas 实现要点

**先说性能陷阱**：全分辨率逐像素 `createImageData` + `Math.random()` 是最容易踩的坑。

```js
// ❌ 1080p 每帧 200 万次 Math.random + 200 万次数组写入 ≈ 10~25ms
const img = ctx.createImageData(W, H);
for (let i = 0; i < img.data.length; i += 4) {
  const v = Math.random() * 255 | 0;
  img.data[i] = img.data[i+1] = img.data[i+2] = v;
  img.data[i+3] = 255;
}
ctx.putImageData(img, 0, 0);
```

**正确做法（按性价比排序）**：

```js
// ✅ 方案 A：预生成 4~6 张 128×128 的噪点 tile，每帧随机挑一张 + 随机平移，平铺
const TILES = Array.from({length: 6}, () => makeNoiseTile(128));
function drawStatic(dst, W, H, t) {
  const tile = TILES[(t | 0) % TILES.length];
  const ox = (Math.random() * 128) | 0, oy = (Math.random() * 128) | 0;
  const pat = dst.createPattern(tile, 'repeat');
  dst.save();
  dst.translate(-ox, -oy);
  dst.fillStyle = pat;
  dst.fillRect(0, 0, W + 128, H + 128);
  dst.restore();
}
// 成本 < 0.3ms。缺点：6 张 tile 会有微弱循环感（肉眼几乎看不出）

// ✅ 方案 B：生成 1/4 分辨率的噪点再放大 → "块状雪花"，反而更像低带宽/VHS
// ✅ 方案 C：用 Uint32Array 一次写一个像素，比逐个 data[i] 写快 2~3 倍
const buf = new Uint32Array(imageData.data.buffer);
for (let i = 0; i < buf.length; i++) buf[i] = 0xFF000000 | (rnd() * 0xFFFFFF);
```

WebGL 里就是一行（canvasui 的写法）：

```glsl
float g = hash(uv * uResolution + fract(t) * vec2(127.1, 311.7)) - 0.5;
col += g * uGrain;
```

关键点：

- **噪点强度要分通道不同**：真实磁带是"亮度噪点强、色度噪点弱且更柔"。luma 加 100% 的 grain，chroma 只加 40%，比全通道统一加强更像 VHS。
- **一定要 `IntersectionObserver` 暂停**：满屏 `requestAnimationFrame` 刷噪声在手机上会持续吃掉 15~25% 的一个 CPU 核。元素滚出视口就 `cancelAnimationFrame`。
- **颗粒和雪花是两个参数**：grain 是叠加在原图上的（`col += g`），static 是替换原图的（`col = g`）。同时出现时，先叠 static 再叠 grain。
- **同一张噪声纹理可以复用为 displacement map**：第 2/3/6 节的偏移量都可以从这张图采样，省一次生成。
- **对文字和 UI 的增益**：`mix-blend-mode: screen` 让文字"穿"过噪点（亮噪点提亮文字、暗噪点保持透明），比直接把噪声盖在最上层有层次。注意 `mix-blend-mode` 要求两者在同一层叠上下文里——祖先元素带 `isolation: isolate` 或 `will-change: transform` 会破坏混合。

### 是否适合逐帧实时渲染

**WebGL：完全适合。** 一次 hash 计算，零成本。
**Canvas2D：必须用技巧。** 全分辨率逐像素不可行；tile 平铺（<0.3ms）和降采样放大（<1ms）都非常可行。**降采样那条路不只是优化，它产生的"块状雪花"在观感上反而更对**——这是一个优化和美学同向的罕见情况。

### 真实参考链接

- CodeFronts: Glitch Text with Noise Overlay（**上面那套 Canvas 噪声的完整可运行实现**：`createImageData` + 逐帧 RGB 噪声，R 通道 100%、G 60%、B 30% 做暖色颗粒；`mix-blend-mode: screen` 让文字穿过噪点；`IntersectionObserver` 暂停；还明确给出"手机端持续占用 15~25% 一个 CPU 核"的性能警告）：<https://codefronts.com/motion/css-glitch-text-effect/glitch-text-with-noise-overlay/>
- canvasui VHS（`grain` 与 `scanlines` 的组合，`hash(uv * uResolution + fract(t) * vec2(127.1, 311.7))` 就是这段 GLSL 的来源）：<https://canvasui.dev/docs/components/vhs>
- Ashima webgl-noise（**GLSL 噪声的行业标准实现**，simplex / classic / periodic 三套，bad-tv-shader 用它做失真；比 `fract(sin(dot(...)))` 慢但质量高，适合当 displacement 源）：<https://github.com/ashima/webgl-noise>
- MDN `feTurbulence`（**零 shader 的噪声路线**：`type="turbulence"` vs `"fractalNoise"`、`baseFrequency` 控制粗糙度、`numOctaves` 层数、`seed` 动画化。可以配 `feDisplacementMap` 一层做出噪声驱动的扭曲）：<https://developer.mozilla.org/en-US/docs/Web/SVG/Reference/Element/feTurbulence>
- TimelineMax + feTurbulence 的 `baseFrequency` 动画（把 `baseFrequency` 从 `0.000001 0.000001` 突跳到 `0.5 0.02` 再跳回，是 SVG 版的"信号丢失瞬间"）：<https://codepen.io/ktaftaf/pen/pbLOWg>

---

## 12. Text Corruption / Zalgo 文字乱码

**中文名**：文字乱码 / 组合符污染 / 文字错乱
**英文名**：Zalgo text / Text corruption / Text scramble / Glitch text

### 两种完全不同的乱码

| 类型 | 机制 | 观感 |
|------|------|------|
| **Zalgo（组合符号）** | 每个字符后面插入 N 个 Unicode **组合附加符号**（Combining Diacritical Marks） | 字符被"撑开"，上下溢出，像被污染腐蚀 |
| **Text scramble（字符替换）** | 每帧把部分字符替换成同宽的乱码字符 | 像终端在解码/扫描，字宽不变，行不动 |

**做界面文字用第 2 种，做标题/视觉主体用第 1 种。** 混用会让布局崩掉。

### Zalgo 的 Unicode 机制

组合符号是"附着在前一个字符上"的码点，所以：

```js
// 三个符号池（区分上/中/下，才有可控的形态）
// 主体范围：U+0300–U+036F（Combining Diacritical Marks，79 个）
// 扩展：U+1AB0–U+1AFF、U+1DC0–U+1DFF、U+20D0–U+20FF、U+FE20–U+FE2F、U+0483–U+0489

const UP    = /* 上方池，如 \u0300 \u0301 \u0302 \u0304 \u0307 \u0308 ... \u0362 */;
const MID   = /* 中部池，如 \u0315 \u031A \u031C ... \u0334–\u0338 */;
const DOWN  = /* 下方池，如 \u0316 \u0317 \u0320 \u0323 \u0329 \u0330 ... */;

function zalgoify(text, { up = true, mid = false, down = true, counts = {up:8, mid:3, down:8} } = {}) {
  let out = '';
  for (const ch of text) {
    out += ch;
    if (/\s/.test(ch)) continue;                     // 空白字符不加，否则排版会炸
    for (const type of ['up', 'mid', 'down']) {
      if (type === 'up' && !up) continue;
      if (type === 'mid' && !mid) continue;
      if (type === 'down' && !down) continue;
      const pool = { up: UP, mid: MID, down: DOWN }[type];
      const n = counts[type];
      for (let i = 0; i < n; i++) out += pool[(Math.random() * pool.length) | 0];
    }
  }
  return out;
}

// 反 Zalgo：NFD 拆解后按码点范围剔除，再 NFC 归一
function banish(s) {
  return s.normalize('NFD')
          .replace(/[\u0300-\u036F\u1AB0-\u1AFF\u1DC0-\u1DFF\u20D0-\u20FF\uFE20-\uFE2F\u0483-\u0489]/g, '')
          .normalize('NFC');
}
```

强度档位（来自几个库的实际默认值，可直接采用）：

| 档位 | up | mid | down | 观感 |
|------|----|----|-----|------|
| mini | 0–8 随机 | 0–2 | 0–8 | 轻微抖动 |
| 默认 | 1–9 | 0–3 | 1–9 | 明确的污染感 |
| maxi | 3–19 | 1–5 | 3–67 | 完全不可读，纯纹理 |

### Canvas 实现要点（这里是最容易翻车的地方）

```js
// ❌ 错误做法：每帧改 DOM 文本。触发 layout + 重新整形（shape）整个文本
//    Zalgo 有几百个组合符号时，一次 textContent 赋值可能 5~30ms

// ✅ 正确做法：预渲染位图 + 运行时切换
const variants = [];
for (let i = 0; i < 8; i++) {
  const off = document.createElement('canvas');
  // 用 measureText 拿到 fontBoundingBoxAscent/Descent，预留足够的上下空间
  // 组合符号会向外溢出，不预留会被裁掉
  variants.push(renderToCanvas(zalgoify(sourceText, { counts: randCounts() }), off));
}
// 运行时只 drawImage(variants[frameIdx])，成本 = 一次贴图
```

关键点：

- **必须预留垂直空间**。Zalgo 会改变字形的实际包围盒，`line-height` 和容器高度按普通文本算的话，上下的符号会被裁掉或者撑开布局。用 `measureText().fontBoundingBoxAscent/Descent` 或者干脆固定一个大 padding。
- **基线必须锁死**。如果每次乱码的基线位置变了，整块文字会上下跳动——那不是"乱码"，那是"抖动"。
- **等宽字体是刚需**（尤其 text scramble）。字符替换时必须保证替换字符占据同样的宽度，否则整行在抖。用 `font-variant-numeric: tabular-nums` + 等宽字体，或者固定宽度的容器 + `letter-spacing` 配合。
- **文本长度变的时候要固定容器宽度**。`text-align: left` + 固定容器 + 溢出隐藏，避免后续内容被推走。
- **可访问性**：乱码文本对屏幕阅读器是灾难。真正的文案必须保留在可访问的 DOM 里（`aria-label` 或视觉隐藏的原文本），装饰层用 `aria-hidden="true"` + canvas。
- **别用 `text-shadow` 模拟通道分离时叠乱码**，两者都对渲染对齐敏感，会互相干扰。

### 是否适合逐帧实时渲染

**结论：可行但必须位图化；60Hz 直接改 DOM 文本不可行。**

- 直接改 `textContent`：❌ 会触发 layout / restyle / 文本整形，几十毫秒级，帧率崩掉。
- 预渲染 N 张位图 + 运行时切换：✅ 成本 = 一次 `drawImage`，可以 60Hz。
- DOM 里改少量字符（text scramble，每秒 8~15 帧变化）：✅ 可用，但必须等宽字体 + 固定宽度容器，且降频到 10~15Hz。**降频不只是性能考虑——真实的解码噪声本来就是断续的，不是每帧都变。**

### 真实参考链接

- favware/node-packages 的 zalgo 实现（**工程完整度最高**：up/middle/down 三个字符池、mini/default/maxi 三档强度的具体数值、Unicode 字符串分割、Emoji 跳过、`banish()` 反 Zalgo）：<https://github.com/favware/node-packages/blob/main/packages/zalgo/src/zalgo.ts>
- 一个 Chrome 扩展的 Zalgo 实现与讲解（**最简可读版**：`getDiacritical()` 用 `0x300 → 0x36f` 遍历生成池、生成器函数逐个 yield 随机符号，配滑块控制强度）：<https://darthvi.com/post/zalgare-extension/>
- gregoryneal/zalgofy（参数化配置：`maxAccentsUp/maxAccentsDown/maxAccentsMiddle/maxTotalAccents`，含 100 个符号的极端示例）：<https://github.com/gregoryneal/zalgofy>
- SyntaxAsSpiral 的 zalgo-lexigon（**字符池最全的一份**：UP/MID/DOWN 三池完整码点列表，另有多套"风格"预设（classic / sleek / aquatic / thorn / spike / rootglow），`stripCombining` 覆盖 `\u1AB0-\u1AFF\u1DC0-\u1DFF\u20D0-\u20FF\uFE20-\uFE2F\u0483-\u0489`，还带 zero-width 隐写与全角/小型大写/倒置/同形字映射）：<https://github.com/SyntaxAsSpiral/SyntaxAsSpiral/blob/main/zalgo-lexigon.html>
- CodePen: CSS text glitch effect（**text scramble 的经典实现**：`TextGlitch` 类每帧随机替换部分字符为同宽乱码字符，同时给三份文本副本设不同的 `clip-path: inset()` 和 `translate`，配 `mix-blend-mode: darken` / `color-burn`。它的 `_randText()` / `_addClipCSS()` / `_unglitch()` 三段结构可以直接搬）：<https://codepen.io/mr21/pen/yWzKgG>
- 一行版 Zalgo（代码高尔夫写法，`String.fromCharCode(0x300 + Math.random()*79|0)`，说明了"所有可打印字符都能挂组合符号"）：<https://gist.github.com/noromanba/3062530dc3970d93762a5775080715f8>

---

## 13. 五个真实参考站 / 开源库（可直接借鉴）

按"能直接拿来做什么"排序，每个都给了可借鉴点。

### ① p5.glitch —— p5.js 的字节级 glitch 库

- **URL**：<https://github.com/ffd8/p5.glitch>
- **在线 demo**：<https://p5.glitch.me/> ｜ 图片示例：<https://editor.p5js.org/ffd8/sketches/wwo8xjaIt> ｜ 摄像头示例：<https://editor.p5js.org/ffd8/sketches/5aew0QfB4> ｜ 视频示例：<https://editor.p5js.org/ffd8/sketches/6OfUZnw9d>
- **作者**：teddavis.org（2020）
- **做了什么**：在浏览器里**真的去改 JPEG 的字节流**（`randomBytes()` / `replaceBytes()` / `replaceHex()`），然后重新解码成图像。所以它的 glitch 是"真数据损坏"级别的——会出现 JPEG 的 DCT 块、色度错位、半张图错位，而不是滤镜能模拟出来的。

**可借鉴点**：
1. **字节级 ≠ 像素级**。滤镜是在成品图上做形变，字节级是让解码器自己出错。后者的"错误质量"高一个档次（会出现真实 JPEG 宏块、色度采样错位这些滤镜做不出来的形态）。如果要做真 glitch，这是唯一的前端路线。
2. `loadQuality(.25)` 的思路：**先把图用低质量重新编码一遍**，再破坏它的字节。低质量意味着熵更低、结构更规则，破坏时产生的形态更集中、更好看。
3. `errors(false)` / `debug()` 这两个 API 的位置说明一个事实：**字节破坏会经常产生解码失败**，需要对这些失败做静默处理，并保留一份"安全版"输出。做失败兜底是这个效果的一部分，不是附加项。
4. `instance` 模式（`new Glitch()` 而不是全局函数）——允许多个 glitch 实例并行，这对我们要做的 boot 序列很有用（不同的破坏层各自持有一份噪音状态）。
5. API 结构值得抄：`loadType('jpg')` → `loadImage()` → `randomBytes/replaceBytes/replaceHex` → `buildImage()` → `image()`。**读-改-重建**三段式，和我们的"源 → 效果链 → 输出"架构是同一个模式。

### ② snorpey/glitch-canvas —— 参数最少的经典 Canvas glitch 库

- **URL**：<https://github.com/snorpey/glitch-canvas> ｜ npm：<https://www.npmjs.com/package/glitch-canvas>
- **星标**：约 750 stars，MIT，2015 年发布、2022 年仍在更新
- **做了什么**：给 canvas 加 glitch 效果。参数只有四个：`seed`（0–99）、`quality`（0–99）、`amount`（0–99）、`iterations`（整数）。API 是链式的：`glitch(params).fromImage(img).toDataURL().then(...)`。

**可借鉴点**：
1. **四个参数就能覆盖足够的表现空间**。它的参数命名值得直接抄：`seed`（可复现的随机种子）、`quality`（JPEG 重编码质量）、`amount`（破坏量）、`iterations`（重复次数）。我们的效果链也应该按这个粒度暴露参数，而不是一个 0~1 的"强度"。
2. **`seed` 必须是显式参数**。这是专业和玩具的分界线——同一个 seed 出同一张图，才能做版本控制、才能复现、才能和美术沟通。用 `Math.random()` 直接糊的代码没法迭代。
3. **输入输出的对称设计**：输入有 `fromImage` / `fromImageData` / `fromBuffer` / `fromStream`，输出有 `toDataURL` / `toImageData` / `toBuffer` / `toJPGStream` / `toPNGStream`。**输入输出接口分开定义**这件事本身是设计模式级别的优点——它在浏览器和 Node 里都能跑，因为接的是数据不是 DOM。
4. 它列举的 "glitch-canvas in the wild"（jpg-glitch 编辑器、glitch-img Web Component、fuzzy.cc hover 效果、Viewport Glitcher）说明这个效果在**交互 hover 反馈**上的应用已经很成熟，而我们的场景是 boot，节奏不同但参数范围可以参照。

### ③ three.js GlitchPass / RGBShiftShader / AfterimagePass —— 三维引擎里的标准三件套

- **URL**：
  - GlitchPass 文档：<https://threejs.org/docs/pages/GlitchPass.html>
  - GlitchPass 示例：<https://threejs.org/examples/#webgl_postprocessing_glitch>
  - 示例源码：<https://github.com/mrdoob/three.js/blob/master/examples/webgl_postprocessing_glitch.html>
  - RGBShiftShader 源码：<https://github.com/mrdoob/three.js/blob/master/examples/jsm/shaders/RGBShiftShader.js>
  - AfterimagePass 源码：<https://github.com/mrdoob/three.js/blob/master/examples/jsm/postprocessing/AfterimagePass.js>
- **做了什么**：GlitchPass 用一张 `dt_size` 参数的位移噪点纹理对整屏做**数字方块错位**（`goWild` 开关控制强弱）。RGBShiftShader 是标准的两行通道分离。AfterimagePass 是标准残影（`damp` 参数）。

**可借鉴点**：
1. **GlitchPass 的核心机制不是"随机方块"而是"位移纹理"**。它预加载了一张噪声纹理，用纹理值当每块的偏移量，而不是每帧重新算随机数。好处是**错误形态可复现、可设计**（可以自己画一张"错误形状"的纹理来决定哪些区域出错）。这比 `Math.random()` 高级一个层次，而且更便宜。
2. **`goWild` 开关的存在说明一件事**：glitch 的节奏应该有两档——**常态的轻微扰动 + 偶尔的剧烈爆发**。只有恒定的中等强度观感最差（既不干净也不激烈）。我们的 boot 序列必须有这个"档位差"。
3. **它自带癫痫警告**（示例页开头就是 "This example may potentially trigger seizures for people with photosensitive epilepsy"）。这不是客套——快速高对比闪烁是真实的健康风险。我们做的东西必须有 `prefers-reduced-motion` 分支，而且闪烁频率控制在每秒 3 次以下。
4. **AfterimagePass 的 `damp` 值就是第 9 节的那个数字**。直接读源码能看清反馈循环的最小实现骨架，比自己摸索快得多。
5. 三个 pass 的组合顺序（RenderPass → GlitchPass → OutputPass）说明了**后处理的顺序语义**：越靠后的 pass 越"整体"（影响最终画面），越靠前的越"局部"。我们的效果链也应该按这个逻辑排序，而不是随便叠。

### ④ Codrops CSSGlitchEffect —— 纯 CSS、零 JS 的 glitch（clip-path 路线的标杆）

- **URL**：<https://github.com/codrops/CSSGlitchEffect>
- **星标**：约 700 stars
- **做了什么**：5 份完全相同的图片副本叠在一起，各自用 CSS 动画驱动 `clip-path` 和 `translate` 做**不间断的多层错切**。零 JavaScript。灵感来自 404 conference 讲者页面的效果。

**可借鉴点**：
1. **同内容多层 = glitch 的第一性原理**。它不修改图像，而是**复制 5 份，让每一份以不同的方式取景**。这个"克隆 + 各自裁切 + 独立动画"的模型，就是第 3/4/10 节的统一心智模型。理解这一条之后，canvas 版本和 CSS 版本的实现只是 API 差异。
2. **它证明了 CSS 能做到什么程度**：`clip-path` 是可动画的，配合 `@keyframes` 的**不均匀关键帧分布**（大部分时间静止，只在最后 10% 里疯狂抖几下），观感就是一个信号故障。这个"静默 + 突发"的节奏设计和 three.js 的 `goWild` 是同一个洞察，来自两个完全独立的团队。
3. **零 JS 的代价与价值**：代价是做不了真随机、做不了与音频/时间同步、做不了逐像素操作。价值是**性能极好且不会掉帧**（全部在合成器上跑），而且降级安全。我们的 boot 序列如果有一部分只需要"看起来在抖"，纯 CSS 是最稳的选择。
4. 仓库里有 3 个 demo（`index.html` / `index2.html` / `index3.html`），分别演示不同强度，可以直接对照参数。

**配套阅读**：CSS-Tricks 的《Glitch Effect on Text / Images / SVG》把 Lucas Bebber 原始的 glitch 技法（双伪元素 + `clip` 动画 + `text-shadow` 通道分离 + Sass mixin 自动生成本就随机的 keyframes）拆得极清楚，是把这套 CSS 技法搬进工程的关键一篇：<https://css-tricks.com/glitch-effect-text-images-svg/>

### ⑤ Lucas Bebber 的 CSS Glitched Text（CodePen 经典）—— 文字 glitch 的原型

- **URL**：<https://codepen.io/lbebber/pen/ypgql>（标题 "CSS Glitched Text"）
- **解析文章**：<https://css-tricks.com/glitch-effect-text-images-svg/>（Chris Coyier 拆解 + 改成 Sass mixin）
- **做了什么**：用 `::before` / `::after` 复制文本，各自偏移 2px 左右，用 `text-shadow` 做通道分离（一侧红一侧蓝），再用可动画的 `clip` / `clip-path` 切成条带，配两组不同时长的 `@keyframes`（2s 和 3s，故意错开）。这就是后来所有"赛博文字"效果的祖先。

**可借鉴点**：
1. **两组动画的时钟必须错开**。它用 `2s` 和 `3s` 两个不同周期的 `alternate-reverse`，让两个副本永远不同步。**同步的 glitch 是假的**——真实故障一定有相位差。
2. **通道分离的实现是"错位 + 染色"而不是"分离通道"**。红蓝两份副本各偏移 ±2px。在深色背景上，效果和真的通道分离肉眼无法区分，但成本低到可以忽略。这是个典型的"观感等价、成本差一个数量级"的取舍，值得记下来。
3. **`clip` / `clip-path` 的左右值保持不变，只动上下值**。这让它切的是"水平条带"，与 scanline tearing 完全一致。如果四个值都动，就变成矩形窗口移动，就不是撕裂了。
4. **keyframes 用 Sass 循环生成，值由 `random()` 产生**。这解决了"CSS 没有随机函数"的问题——在构建时生成随机值，运行时就是静态 CSS。**如果只需要固定几套随机序列，构建期生成是比 JS 运行时生成更优的方案**（零运行时成本、可复现、可版本控制）。

**另外三个值得知道的位置**：
- **glitch.wiki**（<https://glitch.wiki/guides/>）：glitch art 社区维护的技法百科，模拟/数字分类，术语最规范。
- **The Glitch Gallery**（<https://glitchgallery.org/>）：纯"野生 glitch 收藏馆"，收集真实故障产生的图像，可以拿来当**参考图库**——判断自己的效果"像不像真的"时，看这里的真货比看别人的滤镜有用。
- **Rosa Menkman《Glitch Studies Manifesto》**（2010，PDF：<https://amodern.net/wp-content/uploads/2016/05/2010_Original_Rosa-Menkman-Glitch-Studies-Manifesto.pdf>；专著 *The Glitch Moment(um)* PDF：<https://networkcultures.org/_uploads/NN%234_RosaMenkman.pdf>；词条：<https://www.isea-symposium-archives.org/presentation/glitch-studies-manifesto/>）：这不是技术文档，但里面最重要的一个概念是 **"glitch 一旦被商品化成滤镜，它就失去了 glitch 性"**（从 "pure glitch" 到 "post-procedural glitch"）。对你的项目有直接指导意义：**可复用的效果越"标准"，越不像故障**。所以每个效果都需要一个非标准的、与具体内容耦合的扰动源。

---

## 14. 组合策略与工程建议

### 14.1 效果链的顺序（不要随便叠）

从"最贴内容"到"最贴屏幕"排：

```
源（视频/离屏 canvas/SVG 渲染）
  ↓ 1. pixel sorting / mirror slice        —— 改变画面的空间结构（最贵，最先做，可降采样）
  ↓ 2. datamosh 块位移 / sine wave         —— 改变画面的局部结构
  ↓ 3. scanline tearing                    —— 条带级硬切
  ↓ 4. RGB channel shift                   —— 通道级错位
  ↓ 5. bitcrush / posterize                —— 色彩量化（必须在 dither 之前）
  ↓ 6. dither / Bayer                      —— 网点（必须在量化之后）
  ↓ 7. vertical roll / VHS tracking        —— 屏幕级（几何）
  ↓ 8. ghost echo（反馈回路）              —— 时间级，必须能看到前面所有结果
  ↓ 9. static noise / scanlines            —— 最上层叠加
  ↓ 输出（DOM canvas / <video> / 背景）
```

**关键顺序约束**（搞反了会毁掉效果）：

| 约束 | 原因 |
|------|------|
| **量化 → 抖动**，不能反 | 反过来抖动会被二次量化毁掉，网纹变成斑块 |
| **几何失真 → 噪点**，不能反 | 噪点先加会被后面的采样/滤镜拉伸成条带，变成"脏条纹" |
| **残影回路必须靠后** | 它读的是"上一帧的最终结果"，位置不对就没有累积效应 |
| **pixel sorting 最靠前** | 它需要"干净的结构"来判断区间。前面已经有噪点的话，阈值检测会被噪点淹没 |
| **VHS 滚动在几何类效果之后** | 滚动是"整个屏幕在滚"，如果在它之后再撕裂，撕裂的位置也跟着滚（有时想要，有时不想要——要明确） |

### 14.2 单帧预算参考（1080p，桌面 Chrome，粗略量级）

| 效果 | 单帧成本 |
|------|----------|
| scanline tearing（24 条 drawImage） | 0.2 ms |
| RGB shift（3 次 drawImage + filter） | 0.5 ms |
| 块位移（~2400 块 drawImage） | 1–2 ms |
| bitcrush（查表 + Uint32 写回） | 1–3 ms |
| 噪点（tile 平铺） | <0.3 ms |
| 噪点（全分辨率逐像素） | **10–25 ms ❌** |
| 逐行 sine（1080 行 drawImage） | 2–5 ms |
| VHS 全套（滚动 + 逐行 jitter + 底部带） | 3–7 ms |
| 残影（fillRect 方案） | <0.1 ms |
| pixel sorting（全分辨率 CPU） | **>2000 ms ❌** |

**16.7ms 的预算下，上面大部分效果是可以同时开的**，但要注意：这些是桌面数字，手机上要乘 3~5 倍。做移动端必须砍掉逐行操作和全分辨率逐像素操作。

### 14.3 三条必须遵守的工程纪律

1. **`prefers-reduced-motion` 不是可选项。** 快速高对比闪烁有真实的癫痫风险（three.js 官方示例在开头就放警告）。至少要做到：闪烁频率 ≤ 每秒 3 次；提供降级分支（静态 glitch 帧而不是动画）；用 `matchMedia('(prefers-reduced-motion: reduce)')` 监听并在运行时响应变化。
2. **离屏可见性检测。** 元素滚出视口就 `cancelAnimationFrame`。满屏 `requestAnimationFrame` 在后台标签页虽会被节流，但在滚动离开视口时不会——这是手机上最常见的耗电来源。
3. **参数要有 `seed` 且可复现。** 用 `mulberry32` 之类的确定性 PRNG 替代 `Math.random()`。好处：效果可复现、可以保存/分享参数、可以做版本对比、可以 A/B 测试。这不是锦上添花——没有它，调参就是纯粹的运气。

### 14.4 这套东西的"真"与"假"

把这一节单独拎出来，因为它比任何参数都重要。

**"假 glitch"的共同特征**：所有效果同时、均匀、持续地作用在整幅画面上；每个像素都被平等地影响；没有时间上的静默期。看两秒就觉得"这是个滤镜"。

**"真 glitch"的特征**：
- **空间不均匀**：只有部分条带在撕裂、只有部分块在卡顿、只有画面的一半被镜像。
- **时间不连续**：大部分时间是干净的，故障在几帧里突然爆发然后消失（Codrops 的 keyframes 用 90% 的时间什么都不做；three.js 有 `goWild`）。
- **有因果的形态**：撕裂是水平的（行同步丢失）、块位移是方块状的（宏块）、色度延迟是向右的（副载波）、head-switching 噪声在底部（换头期）。**方向、形状、位置都有物理原因**——随便乱做就不会像。
- **不完全可读也不完全不可读**：能看到原内容，但局部被破坏。全糊掉就失去信息了。

用 Rosa Menkman 的话说：glitch 一旦被标准化成可复现的效果就变成了商品。**唯一的解药是让扰动源和具体内容耦合**——噪点从画面内容里采样、破坏强度从音频电平里取、撕裂时机从外部事件触发。这样每次跑出来的故障都不一样。

---

## 15. 诚实说明：本文没覆盖的部分

- **音频 glitch（databending on WAV）**：把 WAV/MP3 字节重新解释成图像或其他格式，属于"跨格式误读"，是另一条完全不同的技术路线，本文未展开。
- **真 datamosh 的浏览器内实现**：WebCodecs 能拿到编码后的 chunk（`EncodedVideoChunk`），理论上可以在浏览器里做 I 帧删除。但 WebCodecs 不暴露运动向量，`EncodedVideoChunk` 的改写在浏览器里也没有标准 API——这条路本文只给了原理和 FFGlitch 参考，没有给出可行实现。
- **CSS 侧的完整方案**：本文的 CSS 部分只覆盖了 clip-path 路线（技术 3、10、12 的 CSS 版本）。CSS 的 `filter: url()` + SVG 滤镜（feTurbulence / feDisplacementMap / feComponentTransfer）能做不少替代方案，但没有 shader 那种逐帧精确控制。如果需要 CSS 完整版，这是一块独立的工作。
- **halftone（真网点，非 Bayer）**：本文给了概念区分和实现方向（坐标旋转约 45° 后算网格），但没有给出完整实现和参考链接——这一条的证据链比其他的弱，实现前建议自己验证。
- **pixel sorting 的 GPU 稳定性问题**：Luke Cochrane 的文章里提到用并行基数排序解决"排序不稳定"的问题（bitonic sort 不稳定会打乱相同亮度像素的顺序，导致同一张图跑两次结果不一样）。本文转述了这个结论，但没有实际验证过他的实现。
- **WebGPU vs WebGL 的取舍**：本文以 WebGL2 为主。WebGPU 的 compute shader 对 pixel sorting 和全分辨率逐像素操作是决定性的优势（canvasui 也提供了 WebGPU 版本），但浏览器支持面还窄，需要单独的降级策略。

### 链接可用性

本文文件内的 76 个链接在 2026-10-08 全部经 `curl -L` 实测：

| 状态 | 数量 | 说明 |
|------|------|------|
| HTTP 200 | 71 | 正常可访问 |
| HTTP 403 | 3 | CodePen 反爬（`lbebber/ypgql`、`mr21/yWzKgG`、`ktaftaf/pbLOWg`）。**三个 Pen 均已通过独立内容抓取确认存在**，页面标题分别为 "CSS Glitched Text"、"CSS text glitch effect (clip-path & mix-blend-mode)"、"Glitch Button using an SVG filter" |
| HTTP 454 | 1 | `godotshaders.com/shader/quantized-bayer-dither/`，Cloudflare 反爬，页面真实存在 |
| HTTP 429 | 1 | `SyntaxAsSpiral/zalgo-lexigon.html` —— 这是 GitHub 对我连续请求的**临时限流**，等待 60 秒后重测返回 **200**，链接有效 |

**已移除的一条**：原计划引用 FLOSS Manuals 的 *A Look at Open Video*（用 datamoshing 讲 I/P 帧编码原理，内容质量很好），但该站点的 HTTPS 已经整体不可用（域名根 `https://archive.flossmanuals.net/` 连接失败，HTTP 版 301 跳向 HTTPS 后同样失败）。**已替换为 ffmpeg 官方 wiki 与 Wikipedia 两条仍然可访问的等价来源**，见第 2 节。

> 校验复现方法：`grep -oE 'https?://[^ >)]+' glitch-techniques.md | sort -u` 抽出全部链接后用 `curl -s -o /dev/null -w '%{http_code}' -L` 逐个探测。注意对 GitHub 批量请求会触发 429，需要加 sleep 间隔重测。
