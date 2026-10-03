import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createProject, editBatch, readProject } from '../project.mjs';
import { MIN_RENDER_HEIGHT, checkRenderSize, outputSize, renderProject } from '../render.mjs';
import { synthVideo } from './media-fixtures.mjs';

test('preview keeps the longest edge at 640 but never drops below the renderer height limit', () => {
  assert.equal(MIN_RENDER_HEIGHT, 88);
  assert.deepEqual(outputSize({ width: 1280, height: 720 }, true), { width: 640, height: 360 });
  assert.deepEqual(outputSize({ width: 720, height: 1280 }, true), { width: 360, height: 640 });
  assert.deepEqual(outputSize({ width: 320, height: 180 }, true), { width: 320, height: 180 });
  // Extreme aspect ratios: 640 x 80 would stall, so the preview is raised to 88 px high.
  assert.deepEqual(outputSize({ width: 1280, height: 160 }, true), { width: 704, height: 88 });
  assert.deepEqual(outputSize({ width: 3840, height: 480 }, true), { width: 704, height: 88 });
  // Never above the canvas itself.
  assert.deepEqual(outputSize({ width: 640, height: 88 }, true), { width: 640, height: 88 });
  assert.deepEqual(outputSize({ width: 3840, height: 90 }, true), { width: 3754, height: 88 });
  // Export is always the canvas.
  assert.deepEqual(outputSize({ width: 3840, height: 480 }, false), { width: 3840, height: 480 });
  assert.doesNotThrow(() => checkRenderSize({ width: 64, height: 88 }));
  assert.throws(() => checkRenderSize({ width: 1280, height: 86 }), /Canvas 1280x86 is too small to render.*88 px/);
});

test('a canvas below the height limit is created and edited, but render and preview fail at once', async t => {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'render-size-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const clip = await synthVideo(path.join(dir, 'clip.mp4'), { size: '128x72', seconds: 1 }), root = path.join(dir, 'project');
  // Create and edit are not refused: this is a renderer limit, not a document rule.
  await createProject(root, { project_id: 'tiny', title: 'tiny', canvas: { width: 128, height: 72, fps: 30 }, assets: [{ id: 'clip', path: clip }],
    tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [{ id: 'one', track_id: 'v', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0 }] });
  await editBatch(root, { base_revision: 1, author: 'agent', summary: 'trim', operations: [{ type: 'trim_item', item_id: 'one', tail_frames: 3 }] });
  assert.equal((await readProject(root)).revision, 2);
  for (const preview of [false, true]) {
    const output = path.join(dir, `out-${preview}`), started = Date.now();
    await assert.rejects(renderProject(root, output, { preview }),
      /Canvas 128x72 is too small to render: the renderer's screenshot capture stalls below 88 px of output height \(measured: ≤86 px fails, ≥88 px renders, whatever the media\)\. Use a canvas at least 88 px high/);
    assert.ok(Date.now() - started < 5000, 'refused before any browser starts');
    await assert.rejects(fs.access(output), { code: 'ENOENT' }, 'nothing written');
  }
});
