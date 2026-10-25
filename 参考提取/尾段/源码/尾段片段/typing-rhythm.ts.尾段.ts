// 尾段片段：src/typing-rhythm.ts
// 起止 = 上游原文件行号；上游 /home/xuan/设计/RhineLabUI（HEAD 12cc5e4）
// 尾段窗口 f457–f673（原片 18.28–26.92 s）

──── src/typing-rhythm.ts:1-30  ★ 尾段生效 ★TYPING_FRAMES：拿 bootMotion 反推出来的逐字帧表。窗口内只剩 f457 一帧
import { bootMotion } from "./boot-motion";

// Use the actual 25 fps text reveal, including the first character of each field.
// Glitch restoration at frames 479/485/486 is not new typing.
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
