// 尾段片段：src/boot-motion.ts
// 起止 = 上游原文件行号；上游 /home/xuan/设计/RhineLabUI（HEAD 12cc5e4）
// 尾段窗口 f457–f673（原片 18.28–26.92 s）

──── src/boot-motion.ts:1-5  · 依赖（尾段之前就跑完 / 尾段每帧都在用） import：曲线表两条 + 标志轨迹一条
// Original footage is 25 fps. App time zero corresponds to video time 5 s.
// Discrete editorial cuts use frame numbers; spatial motion uses continuous time.
import { brandTrack, companyTrack, scanTrack, track } from "./boot-tracks";
import { scanOrbitTrack } from "./boot-orbit-tracks";
import { bootLogoTrack } from "./boot-logo-tracks";

──── src/boot-motion.ts:6-22  · 依赖（尾段之前就跑完 / 尾段每帧都在用） progress / smooth / typed / at / accessCounts，逐字文案就靠这几个
export const progress = (t: number, a: number, b: number) =>
  Math.max(0, Math.min(1, (t - a) / (b - a)));
export const smooth = (p: number) => p * p * (3 - 2 * p);
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
const at = (f: number, frames: number[]) => frames.includes(f);
const accessCounts = [
  1, 1, 3, 4, 5, 6, 9, 11, 12, 14, 17, 18, 19, 20, 22, 23, 25, 26,
];

──── src/boot-motion.ts:24-26  · 依赖（尾段之前就跑完 / 尾段每帧都在用） bootMotion 入口 + 帧号换算：f = floor((appTime + 5) * 25 + 1e-5)
export function bootMotion(appTime: number) {
  const t = appTime + 5;
  const f = Math.floor(t * 25 + 0.00001);

──── src/boot-motion.ts:27-36  ★ 尾段生效 ★step 五段分派。第 32 行 t < 19.48 和第 34 行 t < 22.76 是尾段的两条边界
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

──── src/boot-motion.ts:37-41  · 前置（尾段窗口内已定型，不再变化） auth 前两段（ID CONFIRMED / REQUEST RECEIVED），尾段不走这里
  let auth = "";
  if (f < 363) {
    auth = typed("ID CONFIRMED", f, 282, 295);
    if (f >= 320) auth += " : " + typed("JOYCE MOORE", f, 321, 339);
  } else if (f < 421) auth = typed("REQUEST RECEIVED", f, 367, 389);

──── src/boot-motion.ts:42-47  ★ 尾段生效 ★尾段起点。第 44-45 行补三个点，第 46 行是 f479/485/486 的缺字故障
  else {
    auth = typed("START PROCESSING", f, 423, 440);
    if (f >= 449)
      auth += ".".repeat(Math.min(3, 1 + Math.floor((f - 449) / 4)));
    if (at(f, [479, 485, 486])) auth = "              SING...";
  }

──── src/boot-motion.ts:48-54  ★ 尾段生效 每帧输入量：frame / scan / scanOrbit / scanGlitch / 闪切表 / exit
  const frame = t * 25;
  const scan = scanTrack(frame);
  const scanOrbit = scanOrbitTrack(frame);
  const scanGlitch = at(f, [525, 526, 528, 529]);
  const welcomeIntro = [1, 0, 0.28, 0, 1, 0, 0];
  const flashIndex = f - 569;
  const exit = smooth(progress(t, 26.56, 26.92));

──── src/boot-motion.ts:55-70  ★ 尾段生效 快照头部：step / auth / logoOpacity / authOpacity / 标志 / 品牌三行 / powered
  return {
    t,
    f,
    step,
    auth,
    access: "ACCESS PERMISSION REQUIRED".slice(
      0,
      f < 170 ? 0 : accessCounts[Math.min(17, f - 170)],
    ),
    accessOpacity: f >= 170 && f < 227 ? (f === 226 ? 0.25 : 1) : 0,
    logoOpacity: t >= 9.16 && t < 19.48 ? 1 : 0,
    logo: bootLogoTrack(frame),
    logoLetters: typed("RHINE·LAB", f, 232, 255),
    authOpacity: f >= 281 && f < 487 ? 1 : 0,
    brand: [0, 1, 2].map((line) => brandTrack(frame, line)),
    poweredLetters: typed("POWERED BY RHINE LAB", f, 279, 295).length,

──── src/boot-motion.ts:71-120  ★ 尾段生效 ★scan 组：双环半径与起止角、环闪、字距收拢、核心装饰、小点绕行
    scanVisible: t >= 19.48 && t < 22.76,
    scan,
    scanOrbit,
    scanRadius: scan.radius,
    ringScale: scanGlitch ? 1.94 : 1,
    ringOpacity: scanGlitch
      ? 0.32
      : track(
          [
            [487, 0],
            [488, 0.18],
            [490, 0.6],
            [493, 1],
          ],
          frame,
        ),
    ringBlur: scanGlitch ? 2.2 : 0,
    scanTracking: track(
      [
        [487, 40],
        [492, 28],
        [497, 18],
        [500, 14],
        [505, 8],
        [510, 4],
        [515, 1.7],
        [520, 0.5],
        [527, 0],
        [568, 0],
      ],
      frame,
    ),
    scanFont: 26.5,
    permissionOpacity:
      t < 21.8
        ? progress(t, 19.48, 19.88)
        : track(
            [
              [545, 1],
              [546, 0.4],
              [547, 0.3],
              [548, 0.25],
              [549, 0.1],
              [550, 0.04],
              [551, 0],
            ],
            frame,
          ),
    ornament: t >= 21.84,
    coreRadius: scanOrbit.coreRadius,

──── src/boot-motion.ts:121-136  ★ 尾段生效 ★welcome 组：闪切表、公司名扫过、高亮、数据库闪动、退场缩放模糊
    welcomeVisible: t >= 22.76 && t < 26.92,
    welcomePanel:
      flashIndex >= 0 && flashIndex < 7 ? welcomeIntro[flashIndex] : 0,
    welcomeInk:
      flashIndex >= 0 && flashIndex < 7
        ? [0, 0, 0.2, 1, 0, 0, 0.25][flashIndex]
        : 1,
    companyVisible: f >= 588 && !at(f, [590, 591]),
    companyMask: at(f, [594, 595]),
    highlight: companyTrack(frame),
    databaseOpacity: f < 626 || at(f, [628, 629, 631, 634]) ? 0 : 1,
    welcomeLogo: f >= 588,
    welcomeScale: 1 - 0.46 * exit,
    welcomeOpacity: 1 - Math.pow(exit, 3),
    exitBlur: 8 * exit,
    exit,

──── src/boot-motion.ts:137-138  ★ 尾段生效 ★白场与底纹：底纹在 26.92 s 关掉，白场在 26.16–26.88 s 涨满
    backgroundOpacity: t < 26.92 ? 1 : 0,
    white: smooth(progress(t, 26.16, 26.88)),

──── src/boot-motion.ts:139-140  ★ 尾段生效 return 收尾
  };
}
