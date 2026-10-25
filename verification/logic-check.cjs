// Deterministic checks: no browser, network, builds or writes.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const ts = require(path.join(root, 'XI-开场动画/node_modules/typescript'));
function modules() {
  const cache = new Map();
  return function load(file) {
    if (cache.has(file)) return cache.get(file);
    const exports = {}; cache.set(file, exports);
    const js = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    vm.runInNewContext(js, { exports, require(p) { return load(path.resolve(path.dirname(file), p + '.ts')); } });
    return exports;
  };
}
function environment() {
  const queue = new Map(), events = new Map(); let next = 0, now = 0;
  const on = (name, fn) => { if (!events.has(name)) events.set(name, new Set()); events.get(name).add(fn); };
  const off = (name, fn) => events.get(name)?.delete(fn);
  const style = { setProperty(key, value) { this[key] = value; } };
  const sandbox = {
    console, URL, URLSearchParams, location: { search: '', origin: 'http://localhost' },
    performance: { now: () => now }, innerWidth: 1000, innerHeight: 1000,
    requestAnimationFrame(fn) { const id = ++next; queue.set(id, fn); return id; },
    cancelAnimationFrame(id) { queue.delete(id); }, addEventListener: on, removeEventListener: off,
    matchMedia(query) { return { matches: !query.includes('reduced'), addEventListener() {}, removeEventListener() {} }; },
    document: { hidden: false, referrer: '', addEventListener: on, removeEventListener: off,
      documentElement: { addEventListener: on, removeEventListener: off },
      createElement() { return { style: {}, setAttribute() {} }; }, body: { append() {} } },
  };
  sandbox.window = sandbox; sandbox.parent = sandbox;
  vm.createContext(sandbox);
  for (const file of ['playback.js', 'tilt.js']) vm.runInContext(fs.readFileSync(path.join(root, 'shared', file), 'utf8').replace(/export function /g, 'function '), sandbox);
  return { sandbox, queue, events, style,
    advance(ms) { now = ms; const batch = [...queue]; queue.clear(); for (const [, fn] of batch) fn(ms); },
    event(name, data = {}) { for (const fn of [...(events.get(name) || [])]) fn(data); },
  };
}
(async () => {
  const env = environment();
  const draws = [];
  const player = env.sandbox.createPlayback({ duration: 1, render: t => draws.push(t), ready: Promise.resolve() });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(player.state.ready, true);
  for (let i = 0; i < 40; i++) player.start();
  assert.equal(env.queue.size, 1, 'replay must cancel the old loop');
  env.advance(0); env.advance(500);
  assert.equal(player.state.time, .5);
  env.sandbox.document.hidden = true; env.event('visibilitychange');
  assert.equal(env.queue.size, 0);
  env.advance(5500); env.sandbox.document.hidden = false; env.event('visibilitychange'); env.advance(5500);
  assert.equal(player.state.time, .5, 'hidden time must not advance the film');
  env.advance(6000); assert.equal(player.state.ended, true); assert.equal(env.queue.size, 0);
  player.start(); player.destroy(); assert.equal(env.queue.size, 0);

  const frozenEnv = environment();
  const frozen = frozenEnv.sandbox.createPlayback({ duration: 2, render() {}, ready: Promise.resolve(), freeze: .7 });
  await new Promise(resolve => setImmediate(resolve));
  frozen.start(); assert.equal(frozen.state.time, .7); assert.equal(frozenEnv.queue.size, 0);

  const tiltEnv = environment();
  const plane = { style: tiltEnv.style, parentElement: { getBoundingClientRect() { return { left: 0, top: 0, width: 1000, height: 1000 }; } } };
  const tilt = tiltEnv.sandbox.attachTilt(plane);
  tiltEnv.event('pointermove', { pointerType: 'mouse', clientX: 1000, clientY: 0 });
  for (let ms = 0; ms < 2000; ms += 16) tiltEnv.advance(ms);
  assert.match(plane.style.transform, /rotateX\(-9\.0000deg\) rotateY\(-12\.0000deg\)/);
  assert.equal(tiltEnv.queue.size, 0, 'a settled tilt must stop scheduling');
  tiltEnv.event('pointerleave');
  for (let ms = 2000; ms < 4000; ms += 16) tiltEnv.advance(ms);
  assert.equal(plane.style.transform, 'none'); assert.equal(tiltEnv.queue.size, 0);
  tiltEnv.event('pointermove', { pointerType: 'touch', clientX: 1000, clientY: 0 });
  assert.equal(tiltEnv.queue.size, 0); tilt.destroy();

  const load = modules();
  const current = load(path.join(root, 'XI-开场动画/src/boot-tracks.ts'));
  const motion = load(path.join(root, 'XI-开场动画/src/boot-motion.ts'));
  assert.equal(motion.bootMotion(18).scan, null, 'welcome must not compute scan geometry');
  assert.equal(motion.bootMotion(15).scanVisible, true);
  const baseline = process.argv[2];
  if (baseline) {
    const old = load(path.resolve(baseline, 'WENSI-开场动画/src/boot-tracks.ts'));
    const oldOrbit = load(path.resolve(baseline, 'WENSI-开场动画/src/boot-orbit-tracks.ts'));
    const orbit = load(path.join(root, 'XI-开场动画/src/boot-orbit-tracks.ts'));
    for (let frame = 480; frame <= 660; frame += .125) {
      const a = old.scanTrack(frame), b = current.scanTrack(frame);
      for (const key of Object.keys(a)) assert.ok(Math.abs(a[key] - b[key]) < 1e-9, `${key}@${frame}`);
      assert.ok(Math.abs(old.companyTrack(frame) - current.companyTrack(frame)) < 1e-12);
      assert.equal(JSON.stringify(oldOrbit.scanOrbitTrack(frame)), JSON.stringify(orbit.scanOrbitTrack(frame)));
    }
    console.log('Reference scan/orbit/highlight curves unchanged at 1,441 fractional frames.');
  }
  for (const file of ['index-bw.html', '拼接.html']) {
    const html = fs.readFileSync(path.join(root, file), 'utf8');
    for (const [, js] of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(js, { filename: file });
    assert.doesNotMatch(html, /wenxi|wensi|aurora/i);
  }
  console.log('PASS: replay cancellation, pause/resume, freeze, tilt direction/idle/touch, motion gating, syntax and naming.');
})().catch(error => { console.error(error); process.exitCode = 1; });
