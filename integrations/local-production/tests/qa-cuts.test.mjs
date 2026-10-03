import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { burnedCaptionCheck, captionBand, decodeWindow, judgeCutPoint, splitFrames, CAPTION_BAND } from '../burned-captions.mjs';
import { detectShots, extractFrame, frameMid, qaOptions } from '../qa.mjs';
import { run } from '../project.mjs';
import { mediaTool } from '../media-analysis.mjs';
import { captionSource } from '../verify-smoke.mjs';

// Self-authored synthetic sources only (ffmpeg lavfi), no customer media.
const scratch = async t => {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'creative-qa-cuts-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  return dir;
};
const docWith = (asset, items) => ({ canvas: { width: 360, height: 640, fps: 30 }, assets: [{ id: 'src', file: asset, video: true }],
  tracks: [{ id: 'v_main', kind: 'video' }], items: items.map((item, i) => ({ id: `m${i}`, track_id: 'v_main', kind: 'media', asset_id: 'src', volume: 0, ...item })) });

test('cut-point judgement: in-point before a caption change warns, at it is aligned; out-point after one warns', () => {
  const change = [{ source_seconds: 1.5, kind: 'caption' }], frame = 1 / 30;
  // Suggestions are the changed frame's midpoint (not its start; µs precision, not 4 decimals).
  assert.deepEqual(judgeCutPoint('in', 1.3, change, { frame }), { result: 'warn', suggested_source_seconds: 1.516667, suggested_shift_seconds: 0.216667 });
  assert.equal(judgeCutPoint('in', 1.3, [{ source_seconds: 1.5, frame_mid_seconds: 1.51, kind: 'caption' }], { frame }).suggested_source_seconds, 1.51);
  assert.equal(judgeCutPoint('out', 1.7, change, { frame }).suggested_source_seconds, 1.516667);
  // An in-point a hair before the changed frame (24.4333 < 733/30) still shows frame 732: warn, suggest frame 733's midpoint.
  const real = [{ source_seconds: 24.433333, frame_mid_seconds: 24.45, kind: 'caption' }];
  assert.deepEqual(judgeCutPoint('in', 24.4333, real, { frame }), { result: 'warn', suggested_source_seconds: 24.45, suggested_shift_seconds: 0.0167 });
  assert.equal(judgeCutPoint('in', 24.45, real, { frame }).result, 'aligned', 'the midpoint shows the changed frame first');
  assert.equal(judgeCutPoint('out', 24.45, real, { frame }).result, 'aligned', 'out at the midpoint: last shown frame is 732');
  assert.equal(judgeCutPoint('out', 24.4667, real, { frame }).result, 'warn', 'out a hair after frame 733 ends shows it');
  assert.deepEqual(judgeCutPoint('in', 1.5, change, { frame }), { result: 'aligned' });
  assert.deepEqual(judgeCutPoint('in', 0.9, change, { frame }), { result: 'clear' }, 'more than 0.5 s inside the item');
  assert.equal(judgeCutPoint('out', 1.7, change, { frame }).result, 'warn');
  assert.equal(judgeCutPoint('out', 1.5, change, { frame }).result, 'aligned');
  assert.equal(judgeCutPoint('in', 1.3, [{ source_seconds: 1.5, kind: 'shot' }], { frame }).result, 'clear', 'full-frame shot changes are not caption changes');
  assert.deepEqual(captionBand(), CAPTION_BAND);
  assert.throws(() => captionBand({ top: 0.8, bottom: 0.82 }), /Caption band/);
  assert.throws(() => qaOptions({ sceneThreshold: 1.5 }), /Scene threshold/);
});

test('burned-in caption check: caption switching after the in-point warns with the change time; aligned cut and caption-free source pass', { timeout: 60000 }, async t => {
  const dir = await scratch(t);
  await captionSource(path.join(dir, 'caption.mp4'), { changeAt: 1.5 });
  await captionSource(path.join(dir, 'plain.mp4'), {});
  const late = await burnedCaptionCheck(docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 1.3 }]), dir);
  assert.equal(late.status, 'warn', late.observation);
  const point = late.measured.points.find(p => p.edge === 'in');
  assert.equal(point.result, 'warn');
  assert.ok(Math.abs(point.suggested_source_seconds - 45.5 / 30) < 1e-3, `midpoint of the first changed frame (45): ${JSON.stringify(point)}`);
  assert.deepEqual(late.refs, [{ time_seconds: 0, item_id: 'm0' }]);
  assert.match(late.measured.method, /not OCR/);
  // Out-point 1.3 + 1 s = 2.3 s: the change at 1.5 s is 0.8 s before it (outside the window).
  assert.equal(late.measured.points.find(p => p.edge === 'out').result, 'clear');
  const aligned = await burnedCaptionCheck(docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 1.5 }]), dir);
  assert.equal(aligned.status, 'pass', aligned.observation);
  assert.equal(aligned.measured.points.find(p => p.edge === 'in').result, 'aligned');
  const flash = await burnedCaptionCheck(docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 0.7 }]), dir);
  assert.equal(flash.measured.points.find(p => p.edge === 'out').result, 'warn', 'next line flashes before the out-point 1.7 s');
  const plain = await burnedCaptionCheck(docWith('plain.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 1.3 }]), dir);
  assert.equal(plain.status, 'pass', plain.observation);
  // A band that misses the caption row sees nothing.
  const elsewhere = await burnedCaptionCheck(docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 1.3 }]), dir, { band: { top: 0.1, bottom: 0.3 } });
  assert.equal(elsewhere.status, 'pass');
});

test('shot detection finds a 0.6 s shot inside one file', { timeout: 60000 }, async t => {
  const dir = await scratch(t), file = path.join(dir, 'short.mp4');
  await captionSource(file, { duration: 4, shortShot: [2, 2.6] });
  const shots = await detectShots(file, 4);
  assert.equal(shots.length, 3, JSON.stringify(shots));
  assert.ok(Math.abs(shots[1].start - 2) < 0.04 && Math.abs(shots[1].end - 2.6) < 0.04, JSON.stringify(shots));
  assert.equal((await detectShots(file, 4, 0.99)).length, 1, 'threshold is configurable');
});

test('variable frame rate source: every decoded frame keeps its own source time', { timeout: 60000 }, async t => {
  const dir = await scratch(t), file = path.join(dir, 'vfr.mp4');
  // 30 fps until 1 s, then 15 fps; the caption switches at 3.0 s inside the 15 fps part.
  await captionSource(file, { duration: 3, changeAt: 3, slowFrom: 1 });
  const window = await decodeWindow(file, 2.5, 3.6);
  assert.equal(window.frames.length, window.times.length);
  assert.ok(window.frames.length >= 8, `frames ${window.frames.length}`);
  const gaps = window.times.slice(1).map((time, i) => Math.round((time - window.times[i]) * 1000));
  assert.ok(gaps.every(g => g === 67), `15 fps part decodes one frame per 1/15 s: ${gaps}`);
  const late = await burnedCaptionCheck(docWith('vfr.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 2.8 }]), dir);
  const point = late.measured.points.find(p => p.edge === 'in');
  assert.equal(point.result, 'warn', JSON.stringify(point));
  assert.ok(Math.abs(point.suggested_source_seconds - (3 + 1 / 30)) < 1e-3, `midpoint of the 1/15 s frame at 3.0 s: ${JSON.stringify(point)}`);
  const aligned = await burnedCaptionCheck(docWith('vfr.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 3 }]), dir);
  assert.equal(aligned.measured.points.find(p => p.edge === 'in').result, 'aligned', aligned.observation);
});

test('frame/time count mismatch is refused instead of truncated', () => {
  const log = 'Parsed_showinfo_2 @ 0x1] n:0 pts:0 pts_time:1.0 s:4x2\nn:1 pts:1 pts_time:1.5\n', frame = 8;
  assert.deepEqual(splitFrames(Buffer.alloc(2 * frame), log, 0.5).times, [0.5, 1]);
  assert.throws(() => splitFrames(Buffer.alloc(3 * frame), log), /decoded 3 frame\(s\) but showinfo reported 2/);
  assert.throws(() => splitFrames(Buffer.alloc(frame + 3), log), /not trustworthy/);
});

test('summary: any warn wins, otherwise any unchecked point makes the check unknown', { timeout: 60000 }, async t => {
  const dir = await scratch(t);
  await captionSource(path.join(dir, 'caption.mp4'), { changeAt: 1.5 });
  // m0 reads caption.mp4; m1's asset file does not exist, so both its points are unchecked.
  const doc = sourceIn => {
    const d = docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: sourceIn }, { start_frame: 30, frames: 30, source_in_seconds: 0 }]);
    d.assets.push({ id: 'gone', file: 'missing.mp4', video: true });
    d.items[1].asset_id = 'gone';
    return d;
  };
  const mixed = await burnedCaptionCheck(doc(1.3), dir);
  assert.equal(mixed.status, 'warn', mixed.observation);
  assert.match(mixed.observation, /2 of 4 cut point\(s\) were not checked \(m1 in, m1 out\)/);
  const partial = await burnedCaptionCheck(doc(1.5), dir);
  assert.equal(partial.status, 'unknown', partial.observation);
  assert.match(partial.observation, /2 analysed point\(s\).*incomplete\. 2 of 4 cut point\(s\) were not checked/);
  assert.deepEqual(partial.measured.points.map(p => p.result), ['aligned', 'clear', 'unknown', 'unknown']);
});

// Synthetic CFR file: red frames 0–44, blue from frame 45 on (a cut at frame 45).
const colourCut = async (file, { cutFrame = 45, seconds = 3, fps = 30 } = {}) => run(mediaTool('ffmpeg'), ['-v', 'error', '-n', '-f', 'lavfi', '-i',
  `color=c=red:s=64x64:r=${fps}:d=${seconds},drawbox=x=0:y=0:w=64:h=64:color=blue:t=fill:enable='gte(n,${cutFrame})'`, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', file]);
const pixel = async png => {
  const { stdout } = await run(mediaTool('ffmpeg'), ['-v', 'error', '-i', png, '-vf', 'scale=1:1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], { encoding: 'buffer' });
  return stdout[0] > stdout[2] ? 'red' : 'blue';
};

test('QA samples are frame-exact: last frame before a cut and first frame after it', { timeout: 60000 }, async t => {
  const dir = await scratch(t), file = path.join(dir, 'cut.mp4');
  await colourCut(file);
  const colours = {};
  for (const frame of [0, 43, 44, 45, 46, 89]) {
    const png = path.join(dir, `f${frame}.png`);
    await extractFrame(file, frame, 30, png);
    colours[frame] = await pixel(png);
  }
  assert.deepEqual(colours, { 0: 'red', 43: 'red', 44: 'red', 45: 'blue', 46: 'blue', 89: 'blue' });
  assert.equal(frameMid(45, 30), 45.5 / 30);
});
