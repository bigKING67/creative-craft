import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createProject, digest, loadProject } from '../project.mjs';
import { frameAlignment } from '../frame-alignment.mjs';
import { compiledView, correctionOf } from '../source-frames.mjs';
import { agedProject, synthRedThenBlue, tempDir } from './media-fixtures.mjs';

test('frame_rate is re-checked before compiling: a stale one is not applied and is reported, a valid one is', { timeout: 60000 }, async t => {
  const dir = await tempDir('frame-alignment-');
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const primed = await synthRedThenBlue(path.join(dir, 'primed.mkv'), { switchFrame: 30, seconds: 2, acodec: 'aac',
    audioArgs: ['-itsoffset', '-0.067'], args: ['-avoid_negative_ts', 'disabled'] });
  const clean = await synthRedThenBlue(path.join(dir, 'clean.mp4'), { switchFrame: 31, seconds: 2 });
  const root = path.join(dir, 'project');
  const item = (id, asset, start) => ({ id, track_id: 'v', kind: 'media', asset_id: asset, start_frame: start, frames: 10, source_in_seconds: 1.0333, volume: 0 });
  const created = await createProject(root, { project_id: 'aged', title: 'aged', canvas: { width: 320, height: 180, fps: 30 },
    assets: [{ id: 'src', path: primed }, { id: 'clean', path: clean }], tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [item('old', 'src', 0), item('new', 'clean', 10)] });
  assert.ok(!('frame_rate' in created.assets[0]), 'the 0.7.0 import does not record it');
  assert.equal(created.assets[1].frame_rate, '30/1');
  const revision = await agedProject(root), before = await digest(revision);

  const { doc } = await loadProject(root);
  assert.equal(doc.assets[0].frame_rate, '30/1');
  // Without the re-check the stale rate would correct 1.0333 to frame 31.
  assert.equal(compiledView(doc).items[0].source_in_seconds, 1.033433333);
  const { view, frame_alignment } = await frameAlignment(root, doc);
  assert.equal(frame_alignment.length, 2);
  assert.deepEqual(frame_alignment[1], { asset_id: 'clean', frame_rate: '30/1', applied: true });
  const [stale] = frame_alignment;
  assert.deepEqual({ ...stale, reason: undefined }, { asset_id: 'src', frame_rate: '30/1', applied: false, reason: undefined });
  assert.match(stale.reason, /video stream starts at 0 s, after the earliest stream start -0\.\d+ s \(media time 0\)/);
  assert.equal(view.items[0].source_in_seconds, 1.0333, 'stale asset: written in-point kept');
  assert.equal(correctionOf(view.items[0]), null);
  assert.equal(view.items[1].source_in_seconds, 1.033433333, 'valid asset: corrected to frame 31 + 0.1 ms');
  assert.equal(compiledView(view), view, 'the view is final');
  assert.equal(await digest(revision), before, 'the project revision is not rewritten');

  // Same answer from the per-content cache; a changed asset file is refused.
  assert.deepEqual((await frameAlignment(root, doc)).frame_alignment, frame_alignment);
  const other = { ...doc, assets: doc.assets.map(a => a.id === 'clean' ? { ...a, sha256: 'f'.repeat(64) } : a) };
  await assert.rejects(frameAlignment(root, other), /Asset changed: clean/);
});
