// Standalone and iframe playback share one cancellable clock and readiness protocol.
export function createPlayback({ duration, render, ready, entry = 0, freeze = null, reset = () => {}, clickTarget = null }) {
  const params = new URLSearchParams(location.search);
  const embedded = parent !== window && params.get('embedded') === '1';
  const parentOrigin = document.referrer ? new URL(document.referrer).origin : location.origin;
  const targetOrigin = parentOrigin === 'null' ? '*' : parentOrigin;
  const bound = value => Math.max(0, Math.min(duration, Number.isFinite(value) ? value : 0));
  let elapsed = bound(entry), origin = null, raf = 0, playing = false, prepared = false;
  let failed = false, disposed = false, run = 0;
  const state = { ready: false, playing: false, time: elapsed, duration, renders: 0, ended: false, error: '' };
  window.__xiPlayback = state;
  function notify(type, extra = {}) {
    if (embedded) parent.postMessage({ channel: 'xi-opening', type, run, ...extra }, targetOrigin);
  }
  function draw(time) { state.time = time; state.renders++; render(time); }
  function fail(error) {
    failed = true; stop(); state.error = String(error?.message || error);
    const notice = document.createElement('p');
    notice.setAttribute('role', 'alert'); notice.textContent = '动画资源未能载入，请刷新重试。';
    notice.style.cssText = 'position:fixed;inset:45% 1rem auto;text-align:center;color:#ddd;font:16px sans-serif;z-index:100';
    document.body.append(notice); notify('error', { message: state.error });
    console.error(error);
  }
  function suspend() {
    cancelAnimationFrame(raf); raf = 0;
    if (origin !== null) elapsed = bound((performance.now() - origin) / 1000);
    origin = null;
  }
  function stop() { suspend(); playing = state.playing = false; }
  function tick(ms) {
    raf = 0;
    if (!playing || disposed) return;
    if (origin === null) { origin = ms - elapsed * 1000; notify('started', { time: elapsed }); }
    elapsed = bound((ms - origin) / 1000);
    try { draw(elapsed); } catch (error) { fail(error); return; }
    if (elapsed >= duration) {
      playing = state.playing = false; origin = null; state.ended = true;
      notify('done'); return;
    }
    raf = requestAnimationFrame(tick);
  }
  function start(from = 0) {
    if (!prepared || failed || disposed || freeze !== null) return;
    stop(); reset(); elapsed = bound(from); state.ended = false;
    playing = state.playing = true;
    if (!document.hidden) raf = requestAnimationFrame(tick);
  }
  function replay() {
    if (freeze !== null) return;
    if (embedded) notify('replay'); else start(0);
  }
  function key(e) {
    if (e.key.toLowerCase() === 'r' && !e.repeat && !e.ctrlKey && !e.metaKey && !e.altKey) replay();
  }
  function message(e) {
    if (!embedded || e.source !== parent || e.origin !== parentOrigin || e.data?.channel !== 'xi-opening') return;
    if (e.data.type === 'start') { run = e.data.run ?? 0; start(e.data.from ?? 0); }
    if (e.data.type === 'stop') stop();
  }
  function visibility() {
    if (!playing) return;
    if (document.hidden) suspend();
    else if (!raf) raf = requestAnimationFrame(tick);
  }
  function destroy() {
    disposed = true; stop();
    removeEventListener('message', message); removeEventListener('keydown', key);
    document.removeEventListener('visibilitychange', visibility);
    clickTarget?.removeEventListener('click', replay);
  }
  addEventListener('message', message); addEventListener('keydown', key);
  document.addEventListener('visibilitychange', visibility);
  clickTarget?.addEventListener('click', replay);
  addEventListener('pagehide', destroy, { once: true });
  Promise.resolve(ready).then(() => {
    if (disposed) return;
    prepared = state.ready = true;
    draw(freeze === null ? elapsed : bound(freeze));
    notify('ready', { duration });
    if (!embedded && freeze === null) start(entry);
  }).catch(fail);
  return { start, stop, destroy, state };
}
