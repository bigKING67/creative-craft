import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { captionBand, decodeWindow, judgeCutPoint, splitFrames, CAPTION_BAND } from '../burned-captions.mjs';
import { detectShots, extractFrame, frameMid, qaOptions } from '../qa.mjs';
import { run } from '../project.mjs';
import { mediaTool } from '../media-analysis.mjs';
import { judgeFragment } from '../cut-fragments.mjs';
import { burnedCaptionCheck, cutFragmentCheck, cutPointChecks, summarizeCutChecks } from '../cut-checks.mjs';
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
  const log = '[Parsed_showinfo_2 @ 0x1] n:0 pts:2 pts_time:1.0 s:4x2\n[Parsed_showinfo_2 @ 0x1] n:1 pts:3 pts_time:1.5\n', frame = 8, timing = { start: 0.5, time_base: { num: 1, den: 2 } };
  assert.deepEqual(splitFrames(Buffer.alloc(2 * frame), log, timing).times, [0.5, 1]);
  assert.throws(() => splitFrames(Buffer.alloc(3 * frame), log, timing), /decoded 3 frame\(s\) but showinfo reported 2/);
  assert.throws(() => splitFrames(Buffer.alloc(frame + 3), log, timing), /not trustworthy/);
});

test('frame times are integer pts × the ffprobe time base, never the printed pts_time', async t => {
  // pts_time text is deliberately wrong: only pts and the time base count.
  const tagged = lines => lines.map(line => `[Parsed_showinfo_1 @ 0x1] ${line}`).join('\n');
  const log = tagged(['config in time_base: 1/30000, frame_rate: 30000/1001', 'n:   0 pts:  733733 pts_time:24.4578 s:4x2', 'n:   1 pts:  734734 pts_time:24.49']);
  const timing = { start: 0, time_base: { num: 1, den: 30000 } };
  assert.deepEqual(splitFrames(Buffer.alloc(16), log, timing).times, [733733 / 30000, 734734 / 30000]);
  assert.throws(() => splitFrames(Buffer.alloc(16), log, { start: 0, time_base: { num: 1, den: 15360 } }), /showinfo time base 1\/30000 differs from the stream time base 1\/15360/);
  assert.throws(() => splitFrames(Buffer.alloc(16), log.replace('pts:  734734', 'pts:NOPTS'), timing), /frame line has no integer pts/);
  assert.throws(() => splitFrames(Buffer.alloc(16), log.replace(' s:4x2', ''), timing), /no frame size/);
  assert.throws(() => splitFrames(Buffer.alloc(16), log), /needs the stream time_base/);
  // Real decode of a 30000/1001 fps file: every time is exactly k × 1001/30000.
  const dir = await scratch(t), file = path.join(dir, 'ntsc.mp4');
  await run(mediaTool('ffmpeg'), ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=64x64:rate=30000/1001:duration=2', '-c:v', 'libx264', '-video_track_timescale', '30000', file]);
  const window = await decodeWindow(file, 0.5, 1);
  assert.ok(window.times.length >= 10, `frames ${window.times.length}`);
  assert.ok(window.times.every(time => Number.isInteger(Math.round(time * 30000)) && Math.abs(time * 30000 / 1001 - Math.round(time * 30000 / 1001)) < 1e-9), JSON.stringify(window.times));
});

test('an in-point even 1e-7 s before a frame start shows the previous frame (no tolerance toward later frames)', () => {
  const frame = 1 / 30, change = [{ source_seconds: 1.5, kind: 'caption' }];
  assert.equal(judgeCutPoint('in', 1.5 - 1e-7, change, { frame }).result, 'warn', 'frame 44 is shown first; the caption changes one frame later');
  assert.equal(judgeCutPoint('in', 1.5, change, { frame }).result, 'aligned');
  assert.equal(judgeCutPoint('out', 1.5 + frame + 1e-7, change, { frame }).result, 'warn', 'out-point 1e-7 s after frame 45 + 1 frame still shows frame 45');
  assert.equal(judgeCutPoint('out', 1.5 + frame, change, { frame }).result, 'warn', 'last shown frame is 45, the changed one');
  assert.equal(judgeCutPoint('out', 1.5, change, { frame }).result, 'aligned');
  const times = Array.from({ length: 120 }, (_, k) => k / 30);
  const fragment = judgeFragment('in', { times, changes: [30], at: 1 - 1e-7, step: frame, frame, first: 1 - 1e-7, last: 2.9, itemFrames: 58 });
  assert.equal(fragment.result, 'warn', JSON.stringify(fragment));
  assert.equal(judgeFragment('in', { times, changes: [30], at: 1, step: frame, frame, first: 1, last: 2.9, itemFrames: 58 }).result, 'aligned');
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

// Synthetic source (30 fps, 5 s): moving test pattern, colour bars from 1.5 s
// (frame 45) to 3.0 s, a 2-frame white flash on frames 90–91, then the test
// pattern again from frame 92.
const shotsSource = file => run(mediaTool('ffmpeg'), ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=30:duration=5',
  '-f', 'lavfi', '-i', 'smptehdbars=size=360x640:rate=30:duration=5', '-filter_complex',
  "[0:v][1:v]overlay=enable='between(n,45,89)',drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='between(n,90,91)'[v]",
  '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', file]);

test('cut-boundary fragments: judgement rules', () => {
  const frame = 1 / 30, times = Array.from({ length: 120 }, (_, k) => k / 30), base = { times, step: frame, frame, itemFrames: 60 };
  // Shot changes at frames 30, 50 (a 0.67 s shot), 75 and 100 (a 0.83 s shot).
  const changes = [30, 50, 75, 100];
  const at = (edge, source, first, last) => judgeFragment(edge, { ...base, changes, at: source, first, last });
  assert.deepEqual(at('in', 0.8, 0.8, 2.766667), { result: 'warn', kind: 'fragment', fragment_frames: 6, change_seconds: 1,
    suggested_source_in_seconds: 1.016667, suggested_shift_seconds: 0.216667 }, 'opens with 6 frames of the previous shot');
  assert.equal(at('in', 0.99999, 0.99999, 2.98).fragment_frames, 1, 'a hair before frame 30 (1.0 s) still shows frame 29');
  assert.equal(at('in', 1.016667, 1.016667, 2.98).result, 'aligned', 'midpoint of the first frame of the shot');
  assert.equal(at('in', 1.1, 1.1, 3).result, 'clear', 'the 0.67 s shot is shown from frame 33 on: mostly inside the item');
  // Out-point 1.7 s (last shown frame 50, the first of the new shot): ends with 1 frame of the next shot.
  assert.deepEqual(at('out', 1.7, 0, 1.666667), { result: 'warn', kind: 'fragment', fragment_frames: 1, change_seconds: 1.666667,
    suggested_source_out_seconds: 1.683333, suggested_frames: 50, drop_output_frames: 10 });
  assert.equal(at('out', 1.6666667, 0, 1.633333).result, 'aligned', 'the change is the first frame after the cut');
  assert.equal(at('out', 3.3, 1.6, 3.266667).result, 'clear', 'the 0.83 s shot 75–99 cut 1 frame early is mostly shown, not a fragment');
});

test('cut-boundary fragments on a synthetic source: shot tail, flash and next-shot head warn; aligned cuts pass', { timeout: 60000 }, async t => {
  const dir = await scratch(t);
  await shotsSource(path.join(dir, 'shots.mp4'));
  const items = [
    { start_frame: 0, frames: 30, source_in_seconds: 1.3 }, // m0: opens with 6 frames of the test pattern
    { start_frame: 30, frames: 30, source_in_seconds: 1.5 }, // m1: in-point on the bars' first frame
    { start_frame: 60, frames: 30, source_in_seconds: 2.95 }, // m2: 2 bars frames + the 2-frame white flash
    { start_frame: 90, frames: 40, source_in_seconds: 0.2 }, // m3: ends with 1 frame of the bars
    { start_frame: 130, frames: 30, source_in_seconds: 0.5 }, // m4: ends exactly before the bars
  ];
  const result = await cutFragmentCheck(docWith('shots.mp4', items), dir);
  const point = (id, edge) => result.measured.points.find(p => p.item_id === id && p.edge === edge);
  assert.equal(result.status, 'warn', result.observation);
  assert.deepEqual(result.measured.points.filter(p => p.result === 'warn').map(p => `${p.item_id}:${p.edge}`), ['m0:in', 'm2:in', 'm2:out', 'm3:out'], result.observation);
  assert.equal(point('m0', 'in').fragment_frames, 6);
  assert.ok(Math.abs(point('m0', 'in').suggested_source_in_seconds - 45.5 / 30) < 1e-3, JSON.stringify(point('m0', 'in')));
  assert.equal(point('m1', 'in').result, 'aligned');
  assert.equal(point('m2', 'in').kind, 'flash');
  assert.equal(point('m2', 'in').fragment_frames, 4, 'two bars frames and the two-frame flash');
  assert.ok(Math.abs(point('m2', 'in').suggested_source_in_seconds - 92.5 / 30) < 1e-3, JSON.stringify(point('m2', 'in')));
  assert.equal(point('m3', 'out').fragment_frames, 1);
  assert.equal(point('m3', 'out').suggested_frames, 39);
  assert.equal(point('m4', 'out').result, 'aligned');
  // m2 also ends with the flash and 0.88 s of the following shot: keep only its 2 bars frames.
  assert.deepEqual([point('m2', 'out').kind, point('m2', 'out').suggested_frames], ['flash', 2]);
  assert.deepEqual(result.refs.map(r => r.item_id), ['m0', 'm2', 'm2', 'm3']);
  assert.deepEqual([result.measured.thresholds.shot_mad, result.measured.thresholds.scene_jump], [30, 30]);
  assert.match(result.observation, /m0 in-point opens with 6 frame\(s\) of the previous source shot/);
});

test('both cut-point checks share one decode per cut point and match the checks run alone', { timeout: 60000 }, async t => {
  const dir = await scratch(t);
  await captionSource(path.join(dir, 'caption.mp4'), { changeAt: 1.5, duration: 4 });
  const doc = docWith('caption.mp4', [{ start_frame: 0, frames: 30, source_in_seconds: 1.3 }, { start_frame: 30, frames: 30, source_in_seconds: 2.2 }]);
  const calls = [];
  const decode = (...args) => { calls.push(args.slice(0, 3)); return decodeWindow(...args); };
  const shared = await cutPointChecks(doc, dir, { decode });
  assert.equal(calls.length, 4, 'one decode for each of the 4 cut points');
  // The shared range is the union of both checks' ranges (fragments need about ±1 s, captions 0.5 s).
  assert.ok(calls.every(([, from, to]) => to - from > 2), JSON.stringify(calls));
  const alone = [await burnedCaptionCheck(doc, dir), await cutFragmentCheck(doc, dir)];
  assert.deepEqual([shared.burned, shared.fragments], alone);
  assert.equal(shared.burned.status, 'warn', shared.burned.observation);
});

test('cut-check summary: warn wins, then unknown with the unchecked points, else pass', () => {
  const texts = { scope: '3 source cut point(s)', finding: 'thing', describe: e => `${e.item_id} ${e.edge}`, pass: 'all clear',
    warned: (count, details, unchecked) => `${count} warned: ${details}.${unchecked}` };
  const point = (item_id, edge, result, extra = {}) => ({ item_id, edge, result, output_seconds: 1, ...extra });
  const warn = summarizeCutChecks([point('a', 'in', 'warn'), point('b', 'out', 'unknown', { error: 'boom' }), point('c', 'in', 'clear')], { ...texts, sampleAt: () => 's-1' });
  assert.deepEqual(warn, { status: 'warn', observation: '1 warned: a in. 1 of 3 cut point(s) were not checked (b out): boom.', refs: [{ time_seconds: 1, item_id: 'a', sample_id: 's-1' }] });
  const unknown = summarizeCutChecks([point('b', 'out', 'unknown', { error: 'boom' }), point('c', 'in', 'aligned')], texts);
  assert.equal(unknown.status, 'unknown');
  assert.match(unknown.observation, /^No thing found at the 1 analysed point\(s\) of 3 source cut point\(s\), but the check is incomplete\. 1 of 2/);
  assert.deepEqual(summarizeCutChecks([point('c', 'in', 'clear')], texts), { status: 'pass', observation: 'all clear' });
});
