// XI welcome → scan. Reference trajectories remain in 1920×1080 film coordinates.
import "./style.css";
import "./黑场开场.css";
import { BootSequence } from "./boot";
import { attachTilt } from "../../shared/tilt.js";
import { createPlayback } from "../../shared/playback.js";

const stage = document.querySelector<HTMLElement>("#stage")!;
stage.innerHTML = `
  <section class="boot" aria-label="XI AUTOMATION 系统启动">
    <div class="tilt-scene"><div class="tilt-plane">
      <div class="scan"><div class="scan-depth"><svg viewBox="0 0 1920 1080" aria-hidden="true">
        <g fill="none" stroke="#f2f0ec" stroke-width="2" stroke-linecap="round">
          <path stroke-width="2.4"/><path stroke="#6f6f6b" stroke-width="4"/><path/><path/><path/><path/>
          <circle class="orbit-dot" r="0" fill="#b22430" stroke="none"/>
          <circle class="orbit-dot" r="0" fill="#b22430" stroke="none"/>
          <circle class="scan-core" cx="959.5" cy="539.5" r="0" fill="#f2f0ec" stroke="none"/>
        </g>
      </svg></div></div>
      <div class="welcome">
        <div class="welcome-heading">WELCOME TO</div>
        <div class="welcome-company"><strong><span>XI AUTOMATION</span></strong><strong class="welcome-highlight" aria-hidden="true"><span>XI AUTOMATION</span></strong></div>
      </div>
    </div></div>
  </section>`;
stage.dataset.mode = "boot";

const SEGMENTS = [
  { from: 17.76, to: 21.16 },
  { from: 14.48, to: 17.755 },
];
const TOTAL = SEGMENTS.reduce((sum, s) => sum + s.to - s.from, 0);
function filmTime(u: number) {
  let at = Math.max(0, u);
  for (const segment of SEGMENTS) {
    const length = segment.to - segment.from;
    if (at < length) return segment.from + at;
    at -= length;
  }
  return SEGMENTS[SEGMENTS.length - 1].to;
}
const params = new URLSearchParams(location.search);
function numeric(name: string, fallback: number, min: number, max: number) {
  const value = params.has(name) ? Number(params.get(name)) : fallback;
  return Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : fallback;
}
// A packaged act plays one segment of the film on its own. `?stage=` picks it,
// or a packaged page bakes it into window.__XI_STAGE__ so the file needs no query.
const ACTS = {
  welcome: { offset: 0, length: SEGMENTS[0].to - SEGMENTS[0].from },
  scan: { offset: SEGMENTS[0].to - SEGMENTS[0].from, length: SEGMENTS[1].to - SEGMENTS[1].from },
} as const;
const requested = params.get("stage") || (window as { __XI_STAGE__?: string }).__XI_STAGE__ || "";
const act = requested in ACTS ? ACTS[requested as keyof typeof ACTS] : null;
const duration = act ? act.length : TOTAL;
const entry = numeric("t", 0, 0, duration);
const freeze = params.get("freeze") === "1";
let resizeFrame = 0;
function layout() {
  const width = Math.max(1, innerWidth), height = Math.max(1, innerHeight);
  const scale = Math.min(height / 1080, width / 1280);
  stage.style.width = `${width / scale}px`;
  stage.style.height = `${height / scale}px`;
  stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
  stage.dataset.layout = "opening";
  stage.style.setProperty("--opening-scan-scale", String(Math.min(1, width / scale / 1920)));
  stage.dataset.openingPortrait = String(width < height);
}
layout();
addEventListener("resize", () => {
  if (!resizeFrame) resizeFrame = requestAnimationFrame(() => { resizeFrame = 0; layout(); });
});
if (params.has("zoom")) stage.style.setProperty("--portrait-zoom", String(numeric("zoom", 2.4, 1, 3)));
if (params.has("wscale")) stage.style.setProperty("--welcome-scale", String(numeric("wscale", 1, 0.4, 1.5)));
const dot = params.get("dot");
if (dot && /^#?[\da-f]{6}$/i.test(dot)) stage.style.setProperty("--orbit-dot", "#" + dot.replace(/^#/, ""));
// The scan ring is a readout, not a scene: no mouse parallax while it is up.
const startsInScan = filmTime(entry + (act ? act.offset : 0)) >= SEGMENTS[1].from;
const tilt = attachTilt(stage.querySelector<HTMLElement>(".tilt-plane")!, { disabled: freeze || startsInScan });
const sequence = new BootSequence(stage);
// A bounded font wait avoids switching glyph widths halfway through the sweep.
let fontTimeout: ReturnType<typeof setTimeout>;
const fonts = Promise.race([
  document.fonts.load('700 42px "MiSans"').catch(() => []),
  new Promise(resolve => { fontTimeout = setTimeout(resolve, 3000); }),
]).finally(() => clearTimeout(fontTimeout));
createPlayback({
  duration, entry, freeze: freeze ? entry : null, ready: fonts,
  // The act stops one thousandth of a second short of the next act's first
  // frame; otherwise the last drawn frame would already be the other act.
  render(u) {
    const motion = sequence.update(act ? filmTime(Math.min(u, duration - .001) + act.offset) : filmTime(u));
    tilt.setDisabled(motion.step === "scan");
  },
  reset() { tilt.reset(); },
});
