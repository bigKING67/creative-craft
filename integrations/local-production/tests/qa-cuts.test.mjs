import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { burnedCaptionCheck, captionBand, judgeCutPoint, CAPTION_BAND } from '../burned-captions.mjs';
import { detectShots, qaOptions } from '../qa.mjs';
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
  assert.deepEqual(judgeCutPoint('in', 1.3, change, { frame }), { result: 'warn', suggested_source_seconds: 1.5, suggested_shift_seconds: 0.2 });
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
  assert.ok(Math.abs(point.suggested_source_seconds - 1.5) < 0.02, JSON.stringify(point));
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
