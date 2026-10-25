// 尾段片段：src/audio.ts
// 起止 = 上游原文件行号；上游 /home/xuan/设计/RhineLabUI（HEAD 12cc5e4）
// 尾段窗口 f457–f673（原片 18.28–26.92 s）

──── src/audio.ts:74-85  ★ 尾段生效 ★BOOT_CUES：按原片时间码的提示点表。窗口内命中 6 条
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

──── src/audio.ts:614-643  ★ 尾段生效 ★updateBoot：相位配平（22.76 / 26.92 两条边界）+ cue 派发 + 键音
  updateBoot(appTime: number, frozen = false) {
    const time = appTime + 5;
    const previous = this.bootTime;
    this.bootTime = time;
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
    if (
      frozen ||
      previous === null ||
      time < previous ||
      time - previous > 0.3
    ) {
      this.stopEffects();
      return;
    }
    for (const cue of BOOT_CUES)
      if (cue.time > previous && cue.time <= time) this.play(cue.sound);
    if (hasTypingBetween(previous, time)) this.play("key");
  }
