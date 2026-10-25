#!/usr/bin/env python3
"""Browser regression checks using local Chromium and Chrome DevTools Protocol.
Requires websocket-client. No browser/npm download and no public listener.
"""
import argparse
import base64
import http.server
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

import websocket

ROOT = Path(__file__).resolve().parents[1]
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PROBE = r"""
(() => {
 const native=requestAnimationFrame.bind(window),cancel=cancelAnimationFrame.bind(window);
 const pending=new Map(), intervals=[], calls=[], longtasks=[];
 let last=0;
 window.requestAnimationFrame=fn=>{
  const id=native(t=>{pending.delete(id);const a=performance.now();try{fn(t)}finally{calls.push({name:fn.name,ms:performance.now()-a,t})}});
  pending.set(id,fn.name);return id;
 };
 window.cancelAnimationFrame=id=>{pending.delete(id);cancel(id)};
 new PerformanceObserver(list=>{for(const e of list.getEntries())longtasks.push({start:e.startTime,ms:e.duration})}).observe({type:'longtask',buffered:true});
 const motion=[];
 function sample(t){
  if(last)intervals.push(t-last);last=t;
  const p=document.getElementById('pwrap');
  if(p)motion.push({t,transform:p.style.transform});
  native(sample);
 }
 native(sample);
 window.__probe={intervals,calls,longtasks,motion,get pending(){return [...pending.values()]}};
})();
"""

class Browser:
    def __init__(self, baseline=None):
        self.temp = tempfile.TemporaryDirectory(prefix="xi-chrome-")
        class Handler(http.server.SimpleHTTPRequestHandler):
            def translate_path(self, path):
                path = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
                root = ROOT
                if baseline and path.startswith('/before/'):
                    root = Path(baseline); path = path[len('/before'):]
                candidate = (root / path.lstrip('/')).resolve()
                return str(candidate if candidate.is_relative_to(root) else root / '__missing__')
            def do_GET(self):
                delay = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get('delay', ['0'])[0]
                time.sleep(min(2, max(0, float(delay))))
                super().do_GET()
            def log_message(self, *args):
                pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        chrome = sorted(Path.home().glob('.cache/ms-playwright/chromium-*/chrome-linux64/chrome'))[-1]
        self.log = open(Path(self.temp.name) / 'chrome.log', 'w')
        self.process = subprocess.Popen([
            str(chrome), '--headless=new', '--no-sandbox', '--disable-dev-shm-usage',
            '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
            '--blink-settings=primaryPointerType=4,availablePointerTypes=4,primaryHoverType=2,availableHoverTypes=2',
            '--remote-allow-origins=*', f'--user-data-dir={self.temp.name}', 'about:blank',
        ], stdout=self.log, stderr=self.log, start_new_session=True)
        port_file = Path(self.temp.name) / 'DevToolsActivePort'
        for _ in range(150):
            if port_file.exists(): break
            time.sleep(.1)
        port = int(port_file.read_text().splitlines()[0])
        targets = json.load(OPENER.open(f'http://127.0.0.1:{port}/json'))
        target = next(t for t in targets if t['type'] == 'page')
        self.ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=20, suppress_origin=True)
        self.number = 0; self.events = []; self.errors = []
        for method in ['Page.enable', 'Runtime.enable', 'Network.enable', 'Performance.enable']:
            self.call(method)
        self.call('Page.addScriptToEvaluateOnNewDocument', {'source': PROBE})
    def call(self, method, params=None):
        self.number += 1; wanted = self.number
        self.ws.send(json.dumps({'id': wanted, 'method': method, 'params': params or {}}))
        while True:
            item = json.loads(self.ws.recv())
            if item.get('method') == 'Runtime.exceptionThrown': self.errors.append(item['params'])
            if item.get('id') == wanted:
                if 'error' in item: raise RuntimeError(item['error'])
                return item.get('result', {})
            self.events.append(item)
    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
        return result.get('result', {}).get('value')
    def wait(self, expression, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.evaluate(expression): return
            time.sleep(.05)
        raise AssertionError(f'Timed out: {expression}')
    def navigate(self, path, width=1920, height=1080, mobile=False):
        self.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': mobile})
        self.call('Emulation.setTouchEmulationEnabled', {'enabled': mobile})
        self.call('Page.navigate', {'url': path if path.startswith('file:') else self.base + '/' + urllib.parse.quote(path, safe='/?=&:%')})
        self.wait("document.readyState === 'complete'")
    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        data = self.call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
        Path(path).write_bytes(base64.b64decode(data['data']))
    def close(self):
        self.ws.close(); self.server.shutdown()
        os.killpg(self.process.pid, signal.SIGTERM)
        self.process.wait(timeout=10); self.log.close(); self.temp.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline')
    parser.add_argument('--quick', action='store_true')
    args = parser.parse_args()
    browser = Browser(args.baseline)
    report = {'screenshots': [], 'checks': {}, 'environment': {'browser': browser.call('Browser.getVersion'), 'load_average': os.getloadavg()}}
    report['environment']['renderer'] = browser.evaluate("(()=>{const gl=document.createElement('canvas').getContext('webgl');const ext=gl?.getExtension('WEBGL_debug_renderer_info');return ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):'unavailable'})()")
    out = ROOT / 'verification/screenshots'
    preview = ROOT / 'XI-开场动画/预览'
    try:
        for name, path, width, height in [
            ('头像-桌面', 'index-bw.html?f=78', 1920, 1080),
            ('头像-手机', 'index-bw.html?f=78', 390, 844),
            ('光标-删除', 'index-bw.html?f=101', 1920, 1080),
        ]:
            browser.navigate(path, width, height, width < height)
            browser.wait('window.__xiPlayback?.ready')
            assert browser.evaluate('window.__xiPlayback.error') == ''
            browser.screenshot(out / (name + '.png'))
            report['screenshots'].append(name)
            report['checks'][name] = browser.evaluate("({pending:__probe.pending,canvas:[glitch.width,glitch.height],text:document.querySelector('.text-zone').textContent.trim(),overflow:document.documentElement.scrollWidth>innerWidth})")
        for filename, t, width, height in [
            ('01-欢迎页-入场.png', .12, 640, 794),
            ('02-欢迎页-擦亮中.png', 1.04, 640, 794),
            ('03-欢迎页-落定.png', 2.0, 640, 794),
            ('04-扫描环-飞入.png', 4.0, 640, 794),
            ('05-扫描环-收拢.png', 5.7, 640, 794),
            ('06-扫描环-结束帧.png', 6.675, 640, 794),
            ('07-桌面1920x1080.png', 2.0, 1920, 1080),
        ]:
            browser.navigate(f'XI-开场动画/dist/index.html?t={t}&freeze=1', width, height, width < height)
            browser.wait('window.__xiPlayback?.ready')
            assert browser.evaluate('__probe.pending.length') == 0
            browser.screenshot(preview / filename)
        # Character edge alignment survives desktop→portrait resize without reflowing the line.
        browser.navigate('index-bw.html?f=106')
        browser.wait('window.__xiPlayback?.ready')
        for width, height in [(1920,1080),(390,844),(1280,720)]:
            browser.call('Emulation.setDeviceMetricsOverride', {'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
            time.sleep(.15)
            alignment = browser.evaluate("(()=>{const c=document.querySelector('.ch').getBoundingClientRect(),r=document.getElementById('w-caret').getBoundingClientRect();return {delta:r.left-c.right,left:r.left,right:r.right,width:innerWidth}})()")
            assert abs(alignment['delta']) <= .51, alignment
            assert 0 <= alignment['left'] < alignment['right'] <= width, alignment
        report['checks']['caret_resize_alignment'] = True
        # Deletion choreography: the caret sweeps across a still-visible glyph and
        # lands on the new boundary on the same frame that glyph reaches zero.
        browser.navigate('index-bw.html?f=116')
        browser.wait('window.__xiPlayback?.ready')
        trace = browser.evaluate("""(() => {
          const caret=document.getElementById('w-caret');
          const chars=[...document.querySelectorAll('#w-xi .ch')];
          const boxes=chars.map(c=>{const r=c.getBoundingClientRect();return {l:r.left,r:r.right}});
          const out=[];
          for(let f=84;f<=122;f++){ render(f/25); const r=caret.getBoundingClientRect();
            out.push({f, caret:r.left, op:chars.map(c=>parseFloat(c.style.opacity||'1'))}); }
          return {boxes, out, step:Math.max(4,Math.min(10,Math.floor(50/chars.length)))};
        })()""")
        boxes, step = trace['boxes'], trace['step']
        report['checks']['deletion_trace'] = {'step_frames': step, 'boxes': boxes}
        for index in range(len(boxes) - 1, -1, -1):
            order = len(boxes) - 1 - index
            samples = [s for s in trace['out'] if 96 + order * step <= s['f'] < 96 + (order + 1) * step]
            assert samples, f'no samples for character {index}'
            gone = next(s for s in samples if s['op'][index] == 0)
            assert abs(gone['caret'] - boxes[index]['l']) <= .51, (index, gone)
            mid = min(samples, key=lambda s: abs(s['op'][index] - .5))
            assert boxes[index]['l'] < mid['caret'] < boxes[index]['r'], (index, mid)
            assert .05 < mid['op'][index] < .95, (index, mid)
            assert all(s['op'][index] > 0 for s in samples if s['f'] < gone['f']), index
            report['checks'][f'deletion_char{index}'] = {
                'mid_frame': mid['f'], 'mid_opacity': mid['op'][index],
                'caret_at_zero': gone['caret'], 'target': boxes[index]['l'],
            }
        report['checks']['deletion_caret_monotonic'] = all(
            a['caret'] >= b['caret'] - .01 for a, b in zip(trace['out'], trace['out'][1:]))
        assert report['checks']['deletion_caret_monotonic']
        # Perspective direction, actual matrices, inactivity and return to neutral.
        # The welcome act keeps the parallax; the scan ring must not follow the mouse.
        browser.navigate('XI-开场动画/dist/index.html?stage=welcome&t=2.4')
        browser.wait('window.__xiPlayback?.ended')
        browser.call('Input.dispatchMouseEvent', {'type':'mouseMoved','x':1660,'y':180})
        time.sleep(1.3)
        tilt = browser.evaluate("({plane:getComputedStyle(document.querySelector('.tilt-plane')).transform,depth:document.querySelector('.tilt-plane').style.getPropertyValue('--tilt-depth'),pending:__probe.pending})")
        assert tilt['plane'].startswith('matrix3d(') and float(tilt['depth']) > .5, tilt
        assert tilt['pending'] == []
        report['checks']['tilt'] = tilt
        browser.evaluate("document.documentElement.dispatchEvent(new Event('pointerleave'))")
        time.sleep(1.3)
        assert browser.evaluate("document.querySelector('.tilt-plane').style.transform") == 'none'
        assert browser.evaluate('__probe.pending.length') == 0
        browser.call('Emulation.setEmulatedMedia', {'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
        browser.call('Input.dispatchMouseEvent', {'type':'mouseMoved','x':200,'y':900})
        time.sleep(.1)
        assert browser.evaluate("document.querySelector('.tilt-plane').style.transform") == 'none'
        browser.call('Emulation.setEmulatedMedia', {'features':[]})
        report['checks']['tilt_return_reduced_motion'] = True
        browser.navigate('XI-开场动画/dist/index.html?stage=scan')
        browser.wait('window.__xiPlayback?.ended')
        browser.call('Input.dispatchMouseEvent', {'type':'mouseMoved','x':1660,'y':180})
        time.sleep(1.3)
        assert browser.evaluate("document.querySelector('.tilt-plane').style.transform") == 'none'
        assert browser.evaluate("document.querySelector('.tilt-plane').style.getPropertyValue('--tilt-depth')") in ('', '0')
        assert browser.evaluate('__probe.pending.length') == 0
        browser.screenshot(out / '扫描环-不跟随鼠标.png')
        report['checks']['scan_tilt_disabled'] = True
        browser.navigate('XI-开场动画/dist/index.html?t=2.0&embedded=1')
        # Top-level ignores embedded=1, so it still plays normally.
        browser.wait('window.__xiPlayback?.ready')
        browser.call('Input.dispatchMouseEvent', {'type':'mouseMoved','x':1650,'y':220})
        time.sleep(.45)
        browser.screenshot(out / '欢迎页-鼠标倾斜.png')
        browser.navigate('index-bw.html')
        browser.wait('window.__xiPlayback?.ready')
        time.sleep(2.7)
        browser.call('Input.dispatchMouseEvent', {'type':'mouseMoved','x':1640,'y':200})
        time.sleep(.35)
        browser.screenshot(out / '头像-鼠标倾斜.png')
        # Many restarts leave exactly one playback callback, not one per click.
        browser.evaluate("for(let i=0;i<20;i++)stage.click()")
        time.sleep(.1)
        pending = browser.evaluate("__probe.pending.filter(n=>n==='tick').length")
        assert pending == 1, pending
        report['checks']['20_portrait_replays'] = pending
        browser.navigate('拼接.html?cut=.4')
        browser.wait('window.__xiSequence?.ready')
        browser.wait("__xiSequence.active==='b'")
        browser.evaluate("for(let i=0;i<20;i++)dispatchEvent(new KeyboardEvent('keydown',{key:'r'}))")
        time.sleep(.7)
        parent = browser.evaluate("({state:__xiSequence,iframes:document.querySelectorAll('iframe').length,visible:[...document.querySelectorAll('iframe')].filter(f=>f.style.visibility==='visible').length,childPending:[...document.querySelectorAll('iframe')].map(f=>f.contentWindow.__probe.pending)})")
        assert parent['iframes'] == 2 and parent['visible'] == 1, parent
        assert all(len(arr) <= 1 for arr in parent['childPending']), parent
        report['checks']['20_parent_replays'] = parent
        browser.navigate('拼接.html?order=ba&cut=.2')
        browser.wait('window.__xiSequence?.ready')
        assert browser.evaluate('__xiSequence.active') == 'b'
        browser.evaluate("document.querySelectorAll('iframe')[0].contentWindow.dispatchEvent(new KeyboardEvent('keydown',{key:'r'}))")
        browser.wait('__xiSequence.replays===1')
        report['checks']['iframe_keyboard_replay'] = True
        # Delayed documents must not consume the first segment's playback budget.
        delayed = urllib.parse.urlencode({'a':'index-bw.html?delay=.4','b':'XI-开场动画/dist/index.html?delay=1.1'})
        browser.navigate('拼接.html?' + delayed)
        browser.wait('window.__xiSequence?.ready')
        times = browser.evaluate("[...document.querySelectorAll('iframe')].map(f=>f.contentWindow.__xiPlayback.time)")
        assert times[0] < .35 and times[1] == 0, times
        report['checks']['delayed_readiness_times'] = times
        # Self-contained portrait also works when opened directly from disk.
        browser.navigate((ROOT / 'index-bw.html').as_uri() + '?f=78')
        browser.wait('window.__xiPlayback?.ready')
        assert browser.evaluate('window.__xiPlayback.error') == ''
        report['checks']['file_portrait'] = True
        if not args.quick:
            metrics = []
            paths = ['index-bw.html', 'index-bw.html', 'XI-开场动画/dist/index.html']
            if args.baseline: paths = ['before/index-bw.html', 'before/index-bw.html'] + paths
            for path in paths:
                browser.navigate(path)
                time.sleep(7.2)
                sample = browser.evaluate("({intervals:__probe.intervals,calls:__probe.calls,longtasks:__probe.longtasks,motion:__probe.motion,state:window.__xiPlayback,pending:__probe.pending})")
                intervals = sorted(sample.pop('intervals'))
                calls = sample.pop('calls')
                motion = sample.pop('motion')
                metrics.append({
                    'path':path,'samples':len(intervals),
                    'raf_interval_p50_ms':intervals[len(intervals)//2],
                    'raf_interval_p95_ms':intervals[int(len(intervals)*.95)],
                    'raf_interval_max_ms':max(intervals),
                    'callback_total_ms':sum(c['ms'] for c in calls),
                    'callback_max_ms':max((c['ms'] for c in calls),default=0),
                    'portrait_distinct_positions':len(set(m['transform'] for m in motion)),
                    **sample,
                })
            report['performance'] = metrics
            browser.navigate('拼接.html')
            browser.wait('window.__xiSequence?.ready')
            browser.wait("__xiSequence.active==='b'", timeout=8)
            browser.wait('!__xiSequence.playing', timeout=9)
            assert browser.evaluate("[...document.querySelectorAll('iframe')].every(f=>f.contentWindow.__probe.pending.length===0)")
            report['checks']['full_sequence_settles'] = True
        report['runtime_errors'] = browser.errors
        assert not browser.errors, browser.errors
        (ROOT / 'verification/browser-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        browser.close()

if __name__ == '__main__':
    main()
