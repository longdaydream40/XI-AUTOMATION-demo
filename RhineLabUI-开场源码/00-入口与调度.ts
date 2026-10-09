// 从 src/main.ts 抽出的开场入口。行号是原文件行号。
// 点击「开始」只做一件事：记下 bootStart，然后每帧用 (现在 - bootStart) 重算画面。

// ---------- 开场 DOM，原 src/main.ts:63-107 ----------
// $("#stage").innerHTML = `
//   <div id="boot-background" class="boot-background"><svg .../></div>
//   <header class="brand">${brandHeading}</header>
//   <section id="boot" class="boot">
//     <div class="access-text">ACCESS</div>
//     <div class="boot-logo">${logo}</div>
//     <div class="auth-status"><span>▪</span> <span id="auth-message"></span></div>
//     <div class="scan"><svg viewBox="0 0 1920 1080">六条 path + 两个圆点 + 中心点</svg></div>
//     <div class="welcome">...</div>
//   </section>
//   <div class="powered">POWERED BY <b>RHINE LAB</b></div>
// `;
// const bootSequence = new BootSequence($("#stage"));

// ---------- 点击开始，原 src/main.ts:1182-1212 ----------
function completeStartup(silent: boolean) {
  if (started || !ready) return;
  started = true;
  audio.releaseEntry();
  audio.restartBoot();
  const fade = motionActive("boot") ? 600 : 0;
  // 应用时间 0 = 原片 5 秒，所以减 1.76 就是从原片 6.76 秒的白场开始。
  bootStart = performance.now() / 1000 - 1.76;
  bootStart += fade / 1000;
  setMode("boot");
  requestAnimationFrame(frame);
}

// ---------- 每帧调度，原 src/main.ts:1000-1046 ----------
function frame(ms: number) {
  if (document.hidden) { requestAnimationFrame(frame); return; }
  const time = ms / 1000;
  const cinema = mode === "boot" && ready
    ? bootFrame(frozenTime ?? time - bootStart)
    : undefined;
  // 22 秒之前开场层盖住三维场景；之后把同一条时间交给 Three.js。
  if (!viewer?.isOpen && (!cinema || cinema.time >= 21.9)) scene?.update(time, cinema);
  requestAnimationFrame(frame);
}

// ---------- 时间轴分段，原 src/main.ts:941-988 ----------
function bootFrame(t: number) {
  audio.updateBoot(t, frozenTime !== null);
  const motion = bootSequence.update(t);   // DOM / SVG，见 boot.ts
  let step: string = motion.step;          // access | logo | auth | scan | welcome
  if (t >= 22) step = "array";
  if (t >= 25.68) step = "select";
  if (t >= 28.3) step = "inspect";
  if (t >= 35) { setMode("detail"); return undefined; }
  const reveal = ease((t - 22) / 0.4);
  const lift = ease((t - 26) / 1.8);
  const zoom = 0.55 * ease((t - 27.3) / 1.65) + 0.45 * ease((t - 29.0) / 5.0);
  return { reveal, lift, zoom, time: t };
}
