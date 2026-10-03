// Explicit opt-in: real producer + Chrome (PRODUCER_HEADLESS_SHELL_PATH).
// A wide canvas whose 640-px preview would be 640x80 (below the measured
// 88-px capture limit, which stalls) previews at 704x88 and renders.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createProject, probe } from '../project.mjs';
import { renderProject } from '../render.mjs';
import { frameColor, synthVideo } from './media-fixtures.mjs';

test('an extreme-aspect canvas previews clamped to 88 px high and renders', { timeout: 120000 }, async t => {
  assert.ok(process.env.PRODUCER_HEADLESS_SHELL_PATH, 'Set PRODUCER_HEADLESS_SHELL_PATH for this integration check');
  process.env.HF_DE_STALL_MS ??= '15000'; // a regression fails in 15 s instead of 60 s
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'render-size-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const clip = await synthVideo(path.join(dir, 'wide.mp4'), { size: '1280x160', seconds: 1, color: 'blue' }), root = path.join(dir, 'project');
  await createProject(root, { project_id: 'wide', title: 'wide', canvas: { width: 1280, height: 160, fps: 30 }, assets: [{ id: 'clip', path: clip }],
    tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [{ id: 'one', track_id: 'v', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0, fit: 'cover' }] });
  const receipt = await renderProject(root, path.join(dir, 'preview'), { preview: true });
  assert.equal(receipt.status, 'completed');
  const output = path.join(dir, 'preview', 'video.mp4');
  assert.deepEqual([receipt.output.width, receipt.output.height], [704, 88]);
  assert.equal((await probe(output)).height, 88);
  const [r, g, b] = await frameColor(output, 0);
  assert.ok(b > 150 && r < 80 && g < 80, `first frame is the blue source: rgb(${r}, ${g}, ${b})`);
});
