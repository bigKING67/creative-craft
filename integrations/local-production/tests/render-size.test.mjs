import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createProject, loadProject } from '../project.mjs';
import { MIN_RENDER_HEIGHT, MIN_RENDER_WIDTH, captureSize, outputSize } from '../render.mjs';
import { compose } from '../composition.mjs';
import { synthVideo, tempDir } from './media-fixtures.mjs';

test('preview keeps the longest edge at 640 (never above the canvas); export is the canvas', () => {
  assert.deepEqual(outputSize({ width: 1280, height: 720 }, true), { width: 640, height: 360 });
  assert.deepEqual(outputSize({ width: 720, height: 1280 }, true), { width: 360, height: 640 });
  assert.deepEqual(outputSize({ width: 320, height: 180 }, true), { width: 320, height: 180 });
  assert.deepEqual(outputSize({ width: 128, height: 72 }, true), { width: 128, height: 72 });
  // Extreme aspect ratios are no longer raised to the capture limit: the capture is.
  assert.deepEqual(outputSize({ width: 1280, height: 160 }, true), { width: 640, height: 80 });
  assert.deepEqual(outputSize({ width: 3840, height: 64 }, true), { width: 640, height: 10 });
  assert.deepEqual(outputSize({ width: 64, height: 3840 }, true), { width: 10, height: 640 });
  assert.deepEqual(outputSize({ width: 3840, height: 480 }, false), { width: 3840, height: 480 });
});

test('outputs below the measured capture limits are captured at the smallest integer multiple that reaches them', () => {
  assert.equal(MIN_RENDER_HEIGHT, 88);
  assert.equal(MIN_RENDER_WIDTH, 8);
  assert.deepEqual(captureSize({ width: 320, height: 180 }), { width: 320, height: 180, factor: 1 });
  assert.deepEqual(captureSize({ width: 160, height: 88 }), { width: 160, height: 88, factor: 1 });
  assert.deepEqual(captureSize({ width: 160, height: 86 }), { width: 320, height: 172, factor: 2 });
  assert.deepEqual(captureSize({ width: 128, height: 72 }), { width: 256, height: 144, factor: 2 });
  assert.deepEqual(captureSize({ width: 64, height: 64 }), { width: 128, height: 128, factor: 2 });
  assert.deepEqual(captureSize({ width: 640, height: 80 }), { width: 1280, height: 160, factor: 2 });
  assert.deepEqual(captureSize({ width: 640, height: 10 }), { width: 5760, height: 90, factor: 9 });
  assert.deepEqual(captureSize({ width: 3840, height: 64 }), { width: 7680, height: 128, factor: 2 });
  // Width limit (vertical extremes): a 10 px wide preview is wide enough, a 4 px one is not.
  assert.deepEqual(captureSize({ width: 10, height: 640 }), { width: 10, height: 640, factor: 1 });
  assert.deepEqual(captureSize({ width: 4, height: 640 }), { width: 8, height: 1280, factor: 2 });
  // Every canvas validateCanvas accepts (even, 64–3840) and its preview reaches both limits with an exact aspect ratio.
  for (const [w, h] of [[64, 64], [64, 3840], [3840, 64], [128, 72], [1280, 160], [90, 64]]) {
    for (const preview of [false, true]) {
      const out = outputSize({ width: w, height: h }, preview), cap = captureSize(out);
      assert.ok(cap.height >= MIN_RENDER_HEIGHT && cap.width >= MIN_RENDER_WIDTH, `${w}x${h} ${preview}`);
      assert.equal(cap.width * out.height, cap.height * out.width);
      assert.ok(cap.width % 2 === 0 && cap.height % 2 === 0);
    }
  }
});

test('the composition is laid out at the capture size: caption sizes scale with it', async t => {
  const dir = await tempDir('render-size-');
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const clip = await synthVideo(path.join(dir, 'clip.mp4'), { size: '128x72', seconds: 1 }), root = path.join(dir, 'project');
  await createProject(root, { project_id: 'tiny', title: 'tiny', canvas: { width: 128, height: 72, fps: 30 }, assets: [{ id: 'clip', path: clip }],
    tracks: [{ id: 'v', kind: 'video', locked: false }, { id: 'c', kind: 'caption', locked: false }],
    items: [{ id: 'one', track_id: 'v', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0 },
      { id: 'cap', track_id: 'c', kind: 'caption', start_frame: 0, frames: 15, text: 'Hi',
        style: { fontHeight: 0.08, centerY: 0.8, color: '#ffffff', strokeWidth: 0.004, weight: 700 } }] });
  const { doc, templates } = await loadProject(root);
  const fontSize = html => Number(/id="c-cap"[^>]*font-size:([\d.]+)px/.exec(html)[1]);
  const direct = compose(doc, { width: 128, height: 72 }, { templates }).html, captured = compose(doc, captureSize({ width: 128, height: 72 }), { templates }).html;
  assert.match(captured, /data-width="256" data-height="144"/);
  assert.equal(fontSize(captured), 2 * fontSize(direct));
});
