// One outer transform per scene. Timeline transforms stay on their own children.
export function attachTilt(plane, { disabled = false } = {}) {
  const fine = matchMedia('(hover: hover) and (pointer: fine)');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const MAX_X = 9, MAX_Y = 12;
  let targetX = 0, targetY = 0, x = 0, y = 0, last = 0, raf = 0, resizeRAF = 0;
  let rect = { left: 0, top: 0, width: innerWidth, height: innerHeight };
  const enabled = () => !disabled && fine.matches && !reduced.matches;
  function paint() {
    plane.style.transform = x || y ? `rotateX(${x.toFixed(4)}deg) rotateY(${y.toFixed(4)}deg)` : 'none';
    plane.style.setProperty('--tilt-depth', String(Math.min(1, Math.hypot(x / MAX_X, y / MAX_Y))));
  }
  function tick(now) {
    raf = 0;
    const dt = last ? Math.min(64, now - last) : 16.67;
    last = now;
    const a = 1 - Math.exp(-dt / 95);
    x += (targetX - x) * a;
    y += (targetY - y) * a;
    if (Math.abs(targetX - x) + Math.abs(targetY - y) < 0.002) {
      x = targetX; y = targetY; last = 0;
      plane.style.willChange = 'auto';
    } else raf = requestAnimationFrame(tick);
    paint();
  }
  function wake() {
    if (raf) return;
    plane.style.willChange = 'transform';
    raf = requestAnimationFrame(tick);
  }
  function move(e) {
    if (!enabled() || e.pointerType === 'touch') return;
    const nx = Math.max(-1, Math.min(1, (e.clientX - rect.left) / rect.width * 2 - 1));
    const ny = Math.max(-1, Math.min(1, (e.clientY - rect.top) / rect.height * 2 - 1));
    // Positive screen Y / negative screen X rotation lifts the pointed-at edge.
    targetX = ny * MAX_X; targetY = -nx * MAX_Y;
    wake();
  }
  function leave() { targetX = targetY = 0; if (x || y) wake(); }
  function reset() {
    cancelAnimationFrame(raf); raf = 0; last = 0;
    targetX = targetY = x = y = 0;
    plane.style.willChange = 'auto'; paint();
  }
  function measure() {
    // The scene, unlike the plane, is not rotated. Read only on resize.
    rect = plane.parentElement.getBoundingClientRect();
    reset();
  }
  function resize() {
    reset();
    if (!resizeRAF) resizeRAF = requestAnimationFrame(() => { resizeRAF = 0; measure(); });
  }
  function visibility() { if (document.hidden) reset(); }
  function preference() { if (!enabled()) reset(); }
  measure();
  addEventListener('pointermove', move, { passive: true });
  document.documentElement.addEventListener('pointerleave', leave);
  addEventListener('blur', leave);
  addEventListener('resize', resize);
  document.addEventListener('visibilitychange', visibility);
  fine.addEventListener('change', preference);
  reduced.addEventListener('change', preference);
  return { reset, setDisabled(value) {
    if (disabled === value) return;
    disabled = value;
    if (disabled) reset();
  }, destroy() {
    reset(); cancelAnimationFrame(resizeRAF);
    removeEventListener('pointermove', move);
    document.documentElement.removeEventListener('pointerleave', leave);
    removeEventListener('blur', leave); removeEventListener('resize', resize);
    document.removeEventListener('visibilitychange', visibility);
    fine.removeEventListener('change', preference);
    reduced.removeEventListener('change', preference);
  } };
}
