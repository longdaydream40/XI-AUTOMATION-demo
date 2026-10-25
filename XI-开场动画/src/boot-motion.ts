// Original editorial timing is 25 fps; all geometry is evaluated at fractional frames.
import { companyTrack, scanTrack, track } from "./boot-tracks";
import { scanOrbitTrack } from "./boot-orbit-tracks";
const progress = (t: number, a: number, b: number) => Math.max(0, Math.min(1, (t - a) / (b - a)));
const smooth = (p: number) => p * p * (3 - 2 * p);
const ringOpacityKeys = [[487, 0], [488, .18], [490, .6], [493, 1]] as const;
const welcomeInk = [0, 0, .2, 1, 0, 0, .25];

export function bootMotion(appTime: number) {
  const t = appTime + 5, frame = t * 25, f = Math.floor(frame + .00001);
  const scanVisible = t >= 19.48 && t < 22.76;
  const welcomeVisible = t >= 22.76 && t < 26.16;
  const scanGlitch = f === 525 || f === 526 || f === 528 || f === 529;
  const flashIndex = f - 569;
  return {
    f, step: scanVisible ? "scan" : "welcome", scanVisible, welcomeVisible,
    // No invisible logo, authorization lettering or scan geometry is evaluated.
    scan: scanVisible ? {
      geometry: scanTrack(frame), orbit: scanOrbitTrack(frame),
      scale: scanGlitch ? 1.94 : 1,
      opacity: scanGlitch ? .32 : track(ringOpacityKeys, frame),
      blur: scanGlitch ? 2.2 : 0,
      ornament: t >= 21.84,
    } : null,
    welcomeOpacity: welcomeVisible ? 1 - smooth(progress(t, 26.04, 26.16)) : 0,
    welcomeInk: flashIndex >= 0 && flashIndex < 7 ? welcomeInk[flashIndex] : 1,
    companyVisible: f >= 588 && f !== 590 && f !== 591,
    companyMask: f === 594 || f === 595,
    highlight: welcomeVisible ? companyTrack(frame) : 0,
  };
}
