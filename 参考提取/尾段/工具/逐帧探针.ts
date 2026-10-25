// 尾段逐帧探针
//
// 直接 import 上游真实的 boot-motion.ts 跑一遍，把尾段每一帧的数值快照抄出来。
// 不读代码猜，不手抄数值 —— 下面所有结论都由这个脚本产出的数据支撑。
//
// 跑法（需要 bun）：
//   cd /home/xuan/设计/RhineLabUI-开场尾段-剥离
//   bun run 工具/逐帧探针.ts > /tmp/tail-probe.json
//
// 上游：/home/xuan/设计/RhineLabUI（HEAD 12cc5e4）

import { bootMotion } from "../../RhineLabUI/src/boot-motion";
import { TYPING_FRAMES } from "../../RhineLabUI/src/typing-rhythm";
import { BOOT_CUES } from "../../RhineLabUI/src/audio";

type Snap = ReturnType<typeof bootMotion>;

// ── 尾段窗口 ─────────────────────────────────────────────────────────────
// 起点：截图那一帧 —— `▪ START PROCESSING...` 第三个点出现的第一帧。
// 终点：二维开场层最后一次数值变化。
export const START_FRAME = 457;
export const END_FRAME = 673;
// 终点之后再看一段，用来证明「后面真的不变了」。
const LOOKAHEAD = 30;

// 帧号 → appTime。源码里 f = Math.floor((appTime + 5) * 25 + 1e-5)，
// 所以取该帧的起始时刻反推 appTime。
const frameToAppTime = (f: number) => f / 25 - 5;
const at = (f: number) => bootMotion(frameToAppTime(f));

// 把嵌套快照压成一维，便于逐帧比较。
const flatten = (o: object, prefix = ""): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(o)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === "object") {
      if (Array.isArray(v)) out[key] = JSON.stringify(v);
      else Object.assign(out, flatten(v as object, key));
    } else out[key] = String(v);
  }
  return out;
};

// 浮点数留 6 位，快照体积降一个量级，肉眼比对也够。
const round = (value: unknown): unknown => {
  if (typeof value === "number") return Number(value.toFixed(6));
  if (Array.isArray(value)) return value.map(round);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value as object).map(([k, v]) => [k, round(v)]),
    );
  return value;
};

// ── 1. 逐帧快照 ──────────────────────────────────────────────────────────
const frames: Record<string, unknown>[] = [];
for (let f = START_FRAME; f <= END_FRAME; f++)
  frames.push({
    frame: f,
    videoTime: Number((f / 25).toFixed(6)),
    appTime: Number(frameToAppTime(f).toFixed(6)),
    state: round(at(f)) as object,
  });

// ── 2. 逐帧变更：哪些字段在哪几帧真的在动 ────────────────────────────────
const seen = new Map<string, string>();
const changes: { from: number; to: number; fields: string[] }[] = [];
let previous: Record<string, string> | null = null;
for (let f = START_FRAME; f <= END_FRAME + LOOKAHEAD; f++) {
  const flat = flatten(at(f) as object);
  if (previous) {
    const moved: string[] = [];
    for (const [k, v] of Object.entries(flat)) {
      // t / f 是时钟本身，每帧必变，不算内容变化。
      if (k === "t" || k === "f") continue;
      if (seen.get(k) !== v) moved.push(k);
    }
    for (const [k, v] of Object.entries(flat)) seen.set(k, v);
    if (moved.length) {
      const last = changes[changes.length - 1];
      if (last && last.to === f - 1 && last.fields.join() === moved.join())
        last.to = f;
      else changes.push({ from: f, to: f, fields: moved });
    }
  } else for (const [k, v] of Object.entries(flat)) seen.set(k, v);
  previous = flat;
}

const inWindow = changes.filter((c) => c.from <= END_FRAME);
const afterWindow = changes.filter((c) => c.from > END_FRAME);

// ── 3. 边界证据 ──────────────────────────────────────────────────────────
const boundary = {
  startFrame: START_FRAME,
  startVideoTime: START_FRAME / 25,
  startAppTime: frameToAppTime(START_FRAME),
  endFrame: END_FRAME,
  endVideoTime: END_FRAME / 25,
  endAppTime: frameToAppTime(END_FRAME),
  frameCount: END_FRAME - START_FRAME + 1,
  seconds: (END_FRAME - START_FRAME + 1) / 25,
  // 起点那一刻的 auth 文案，用来和截图对齐
  startAuthText: at(START_FRAME).auth,
  // 终点那一刻二维层是否已经全退
  endState: {
    step: at(END_FRAME).step,
    white: at(END_FRAME).white,
    backgroundOpacity: at(END_FRAME).backgroundOpacity,
    welcomeVisible: at(END_FRAME).welcomeVisible,
    welcomeOpacity: at(END_FRAME).welcomeOpacity,
    exit: at(END_FRAME).exit,
  },
  // 终点之后 LOOKAHEAD 帧里还动不动的字段
  lastChangeFrameInWindow: inWindow.length
    ? inWindow[inWindow.length - 1].to
    : null,
  changesAfterWindow: afterWindow,
};

// 截图只能确定到「三个点」这一段；这一段里画面还有什么在动，一并给出来。
const dotRange = { first: 457, last: 478 };
const movingWhileDots = [
  ...new Set(
    changes
      .filter((c) => c.from >= dotRange.first && c.to <= dotRange.last)
      .flatMap((c) => c.fields),
  ),
];

// ── 4. 声音侧：窗口内还有没有键音、有哪些 cue ────────────────────────────
const audio = {
  typingFramesInWindow: TYPING_FRAMES.filter(
    (f) => f >= START_FRAME && f <= END_FRAME,
  ),
  typingFrameTableTail: TYPING_FRAMES.slice(-6),
  cuesInWindow: BOOT_CUES.filter(
    (c) => c.time * 25 >= START_FRAME && c.time * 25 <= END_FRAME + 1,
  ).map((c) => ({ sound: c.sound, time: c.time, frame: Math.round(c.time * 25) })),
};

process.stdout.write(
  JSON.stringify(
    {
      upstream: {
        repo: "/home/xuan/设计/RhineLabUI",
        bootMotion: "src/boot-motion.ts",
      },
      boundary,
      movingWhileDots,
      changes: changes,
      frames,
      audio,
    },
    null,
    1,
  ),
);
