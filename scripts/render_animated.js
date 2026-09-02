#!/usr/bin/env node
/*
 * render_animated.js — 动画帧导出：让 HTML 内 CSS 动画（数字滚入/要点渐入/线条绘制/进度填充）
 * 真正进入成片，替代「每页一张静态帧」的导出方式。
 *
 * 背景：默认管线「HTML → 每页 1 张静态 PNG → compose_motion.py(Ken Burns)」会把页面内 CSS 动画
 * 全部丢失（静态帧只有动画终点态）。本脚本用 Chrome DevTools Protocol(CDP) 对每一页做
 * 「真实时间推进 + 逐帧截屏」，把 CSS 动画的整个过程捕获成帧序列，再拼成 body 视频。
 *
 * 用法：
 *   node render_animated.js <ppt.html> <durations.json> <out_body.mp4> \
 *       [--fps 30] [--size 1920x1080] [--chrome "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] \
 *       [--port 9333] [--frames-dir <dir>] [--only-page 3]
 *
 * 参数：
 *   ppt.html        幻灯片（支持 ?page=N 直达，见 templates/slide-template.html）
 *   durations.json  每页停留时长 {"durations":[d0,d1,...],"total":...}（与配音分段对齐，来自 gen_sync_subs.py）
 *   out_body.mp4    输出的 body 视频（无配音/字幕/水印，后续叠加）
 *   --fps           逐帧采样率，默认 30（CSS 揭示动画 15~30 足够）
 *   --size          视口尺寸，默认 1920x1080（与 16:9 母版一致）
 *   --chrome        Chrome 可执行文件路径
 *   --port          CDP 调试端口，默认 9333（冲突时换一个）
 *   --frames-dir    保留中间帧序列的目录（默认临时目录，结束后删除）
 *   --only-page     只导第 N 页（1 起，调试用）
 *
 * 依赖：node ≥22（内置 fetch/WebSocket）、Chrome/Chromium、ffmpeg（拼接帧序列用）。
 * 说明：本脚本是 Step 6 的「动画增强」路径——关键页需要 CSS 动画进视频时用它替代
 *       「静态帧 + compose_motion.py」；无动画需求时仍走默认 Ken Burns 路径即可。
 */
'use strict';
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function parseArgs() {
  const a = process.argv.slice(2);
  const pos = [];
  const opt = {};
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    if (x.startsWith('--')) {
      const k = x.slice(2);
      const v = a[i + 1] && !a[i + 1].startsWith('--') ? a[++i] : 'true';
      opt[k] = v;
    } else pos.push(x);
  }
  return { pos, opt };
}

const { pos, opt } = parseArgs();
const [htmlPath, durationsPath, outMp4] = pos;
const fps = parseInt(opt.fps || '30', 10);
const size = opt.size || '1920x1080';
const [W, H] = size.split('x').map(Number);
const chromePath = opt.chrome || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const port = parseInt(opt.port || '9333', 10);
const framesDir = opt['frames-dir'] || fs.mkdtempSync(path.join(os.tmpdir(), 'animframes_'));
const onlyPage = opt['only-page'] ? parseInt(opt['only-page'], 10) : null;

if (!htmlPath || !durationsPath || !outMp4) {
  console.error('用法: node render_animated.js <ppt.html> <durations.json> <out_body.mp4> [--fps 30]');
  process.exit(2);
}

function log(...m) { console.log('[render_animated]', ...m); }

// 读每页时长
const durations = JSON.parse(fs.readFileSync(durationsPath, 'utf8'));
const durs = Array.isArray(durations) ? durations : durations.durations;
const nPages = durs.length;

// ---- CDP 客户端（node 内置 WebSocket）----
class CDP {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.pending = new Map();
    this.ready = new Promise((res, rej) => {
      this.ws.onopen = () => res();
      this.ws.onerror = (e) => rej(e);
    });
    this.ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) {
        const { resolve, reject } = this.pending.get(m.id);
        this.pending.delete(m.id);
        m.error ? reject(new Error(m.error.message)) : resolve(m.result);
      }
    };
  }
  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }
}

async function httpJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status} on ${url}`);
  return r.json();
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function waitForChrome(base) {
  for (let i = 0; i < 100; i++) {
    try { await httpJson(`${base}/json/version`); return; } catch (e) { await sleep(100); }
  }
  throw new Error('Chrome 调试端口超时未就绪');
}

async function main() {
  // 1. 启动 Chrome
  const chromeArgs = [
    '--headless=new', `--remote-debugging-port=${port}`,
    '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
    '--hide-scrollbars', '--force-device-scale-factor=1', '--disable-extensions',
    '--disable-dev-shm-usage', '--disable-software-rasterizer',
    '--user-data-dir=' + fs.mkdtempSync(path.join(os.tmpdir(), 'chrome_profile_')),
    'about:blank',
  ];
  log('启动 Chrome ...');
  const chrome = spawn(chromePath, chromeArgs, { stdio: 'ignore' });
  const base = `http://127.0.0.1:${port}`;
  try {
    await waitForChrome(base);
  } catch (e) {
    chrome.kill('SIGKILL');
    throw e;
  }

  try {
    // 2. 新建标签页并连上 CDP（新版 Chrome 的 /json/new 需 PUT 方法；先用 about:blank 建页再 navigate）
    const target = await (await fetch(`${base}/json/new?about:blank`, { method: 'PUT' })).json();
    const cdp = new CDP(target.webSocketDebuggerUrl);
    await cdp.ready;
    await cdp.send('Page.enable');
    await cdp.send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false });

    fs.mkdirSync(framesDir, { recursive: true });
    const frameInterval = 1000 / fps;
    let globalIdx = 0;

    for (let p = 0; p < nPages; p++) {
      if (onlyPage && p + 1 !== onlyPage) continue;
      const dur = Math.max(durs[p] || 0, 0.5);
      const nFrames = Math.max(1, Math.round(dur * fps));
      const url = 'file://' + path.resolve(htmlPath) + '?page=' + (p + 1);

      // 3. 导航到该页，等加载完成（CSS 动画自 load 起推进）
      await cdp.send('Page.navigate', { url });
      await sleep(350); // 等首帧渲染与动画启动

      // 4. 逐帧截屏（真实时间推进，捕获 CSS 动画全程）
      for (let f = 0; f < nFrames; f++) {
        const shot = await cdp.send('Page.captureScreenshot', { format: 'png' });
        const file = path.join(framesDir, `frame_${String(globalIdx).padStart(6, '0')}.png`);
        fs.writeFileSync(file, Buffer.from(shot.data, 'base64'));
        globalIdx++;
        if (f < nFrames - 1) await sleep(frameInterval);
      }
      log(`页 ${p + 1}/${nPages} 完成（${nFrames} 帧，${dur.toFixed(1)}s）`);
    }

    // 5. 帧序列 → body 视频
    const pattern = path.join(framesDir, 'frame_%06d.png');
    const r = spawnSync('ffmpeg', [
      '-y', '-framerate', String(fps), '-i', pattern,
      '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
      path.resolve(outMp4),
    ], { stdio: 'inherit' });
    if (r.status !== 0) throw new Error('ffmpeg 拼接失败');
    log(`OK -> ${outMp4}（${globalIdx} 帧，${fps}fps）`);
  } finally {
    chrome.kill('SIGKILL');
    if (!opt['frames-dir']) {
      try { fs.rmSync(framesDir, { recursive: true, force: true }); } catch (e) {}
    }
  }
}

main().catch((e) => { console.error('[render_animated] 失败:', e.message); process.exit(1); });
