// WENSI 开场动画 —— 只有开场这一段。
//
// 上游 main.ts 有 1785 行，里面混着档案阵列、详情页、三维场景、工作台、壁纸、PWA。
// 这里只留开场真正要跑的那条链：建 DOM → 算版式 → 每帧把 bootMotion(t) 写进 DOM。
//
// 动画本身（boot.ts / boot-motion.ts / boot-tracks.ts / boot-orbit-tracks.ts /
// boot-logo-tracks.ts / boot-lettering.* / brand.ts）逐字节是上游的，一行没改。
// 颜色和文案的改动全在 CSS 和下面这段 DOM 里。
//
// 上游：github.com/LBEILC/RhineLabUI @ 12cc5e4（MIT）

import "./fonts.css";
import "./style.css";
import "./黑场开场.css";
import { BootSequence } from "./boot";
import { logo, brandHeading } from "./brand";

const $ = <T extends HTMLElement = HTMLElement>(selector: string) =>
  document.querySelector<T>(selector)!;

// ── 开场 DOM ───────────────────────────────────────────────────────────────
// 和上游 main.ts:78-100 同一套结构。文案节点全部留着（BootLettering 会逐帧
// 往里写字），只是被 黑场开场.css 关掉了显示。
$("#stage").innerHTML = `
  <div id="boot-background" class="boot-background"><svg viewBox="0 0 1920 1080" preserveAspectRatio="none"><g fill="none" stroke="#fff" stroke-width="3"><path d="M-210 705C-45 705 182 704 247 567C337 377 99 306 4 435S27 680 169 631C309 584 227 314 279 111S568-113 568-113"/><path d="M1560-80C1374 114 1671 168 1601 323S1371 367 1431 480S1692 666 1559 787S1329 886 1498 1130"/><circle cx="1450" cy="648" r="346"/><circle cx="1450" cy="648" r="348"/></g></svg></div>
  <header class="brand">${brandHeading}</header>
  <section id="boot" class="boot" aria-label="系统启动">
    <div class="access-text">ACCESS</div>
    <div class="boot-logo">${logo}</div>
    <div class="auth-status"><span>▪</span> <span id="auth-message"></span><i></i></div>
    <div class="scan"><svg viewBox="0 0 1920 1080" aria-hidden="true"><g fill="none" stroke="#080a08" stroke-width="2" stroke-linecap="round"><path/><path stroke="#fff"/><path/><path/><path/><path/><circle class="orbit-dot" r="8" fill="#ed821b" stroke="none"/><circle class="orbit-dot" r="8" fill="#ed821b" stroke="none"/><circle class="scan-core" cx="960" cy="540" r="5" fill="#080a08" stroke="none"/></g></svg><span>PERMISSION AUTHORIZED</span></div>
    <div class="welcome"><div class="welcome-panel"></div><div class="welcome-heading">WELCOME TO</div><div class="welcome-company"><strong>WENSI AUTOMATION</strong><strong class="welcome-highlight" aria-hidden="true">WENSI AUTOMATION</strong></div><div class="welcome-database">INTERNAL DATABASE</div><div class="welcome-logo">${logo}</div></div>
  </section>
  <div class="powered">POWERED BY <b>RHINE LAB</b><i></i></div>
`;

$("#boot-background").insertAdjacentHTML(
  "beforeend",
  '<div class="boot-white"></div>',
);
$("#stage").dataset.mode = "boot";

const bootSequence = new BootSequence($("#stage"));

// ── 时间轴口径（和上游一致）────────────────────────────────────────────────
// 原片 25 fps，appTime 0 = 原片第 5 秒；播放起点是 appTime 1.76，也就是白场那一帧。
//
// 终点：二维开场层最后一帧是原片 26.92 s（appTime 21.92），之后白场涨满、交给三维档案阵列。
// 这里没有三维，所以停在 appTime 21.16（原片 26.16 s）—— 白场起涨之前，画面落在欢迎页上。
// 注意单位：本文件里的时间全部是 appTime（= 原片秒数 - 5），END 也是。
// 想连白场一起放，把 END 改成 21.92，画面会停在满屏白。
const END = 21.16;

const params = new URLSearchParams(location.search);
// ?t=13.28 从指定 appTime 起播；?t=13.28&freeze=1 只画那一帧（对帧用）。
const entry = params.has("t") ? Number(params.get("t")) : 1.76;
const freeze = params.get("freeze") === "1";

// ── 版式 ───────────────────────────────────────────────────────────────────
// 上游 viewport-layout.ts 的 openingLayout：舞台按 1920×1080 等比铺满视口，
// 开场所有坐标都写在 1920×1080 的局部坐标系里，缩放交给 transform。
function layout() {
  const width = Math.max(1, innerWidth);
  const height = Math.max(1, innerHeight);
  const scale = Math.min(height / 1080, width / 1280);
  const stage = $("#stage");
  stage.style.width = `${width / scale}px`;
  stage.style.height = `${height / scale}px`;
  stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
  stage.dataset.layout = "opening";
  // .boot-white 与 .scan 要用（扫描环在窄舞台上按比例收小）
  stage.style.setProperty("--opening-width", `${width / scale}px`);
  stage.style.setProperty("--opening-height", `${height / scale}px`);
  stage.style.setProperty("--opening-scan-scale", String(Math.min(1, width / scale / 1920)));
  stage.dataset.openingPortrait = String(width < height);
}
layout();
addEventListener("resize", layout);

// ── 每帧 ───────────────────────────────────────────────────────────────────
let step = "";

function render(t: number) {
  // 时间轴是纯函数：同一帧永远同一画面，跳帧、倒放、重算都不会错位。
  const motion = bootSequence.update(Math.min(t, END));
  if (motion.step !== step) {
    $("#stage").dataset.boot = motion.step;
    step = motion.step;
  }
}

if (freeze) {
  render(entry);
} else {
  const started = performance.now() / 1000 - entry;
  const tick = (ms: number) => {
    const t = ms / 1000 - started;
    render(t);
    // 到 END 就不再排下一帧：画面停在欢迎页上，不烧 CPU。
    if (t < END) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
