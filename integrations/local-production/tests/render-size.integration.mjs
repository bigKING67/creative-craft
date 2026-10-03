// Explicit opt-in: real producer + Chrome (PRODUCER_HEADLESS_SHELL_PATH).
// Outputs below the measured 88 px capture height are captured at an integer
// multiple and scaled back: a 128x72 canvas exports and previews at 128x72,
// a 1280x160 canvas previews at 640x80, with the picture and captions in place.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createProject, probe } from '../project.mjs';
import { renderProject } from '../render.mjs';
import { qaRender } from '../qa.mjs';
import { REGION, frameColor, frameColour, synthVideo, tempDir } from './media-fixtures.mjs';

const CAPTION_BAND = 'iw/2:ih/10:iw/4:ih*3/4'; // centre half of the band around centerY 0.8

async function project(dir, name, [width, height], { caption = false } = {}) {
  const clip = await synthVideo(path.join(dir, `${name}.mp4`), { size: `${width}x${height}`, seconds: 1, color: 'red', right: 'blue' });
  const root = path.join(dir, name);
  await createProject(root, { project_id: name, title: name, canvas: { width, height, fps: 30 }, assets: [{ id: 'clip', path: clip }],
    tracks: [{ id: 'v', kind: 'video', locked: false }, ...(caption ? [{ id: 'c', kind: 'caption', locked: false }] : [])],
    items: [{ id: 'one', track_id: 'v', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0, fit: 'cover' },
      ...(caption ? [{ id: 'cap', track_id: 'c', kind: 'caption', start_frame: 0, frames: 15, text: 'HHHH',
        style: { fontHeight: 0.08, centerY: 0.8, color: '#ffffff', strokeWidth: 0, weight: 900 } }] : [])] });
  return root;
}

async function assertRender(root, output, { preview, size, capture }) {
  const receipt = await renderProject(root, output, { preview });
  assert.equal(receipt.status, 'completed');
  assert.deepEqual(receipt.capture, { ...capture, factor: capture.width / size[0], downscale: 'ffmpeg scale flags=area' });
  const video = path.join(output, 'video.mp4'), media = await probe(video);
  assert.deepEqual([receipt.output.width, receipt.output.height, media.width, media.height], [...size, ...size]);
  await assert.rejects(fs.access(path.join(output, 'capture.mp4')), { code: 'ENOENT' }, 'the upscaled capture is removed');
  assert.match(await fs.readFile(path.join(output, 'index.html'), 'utf8'), new RegExp(`data-width="${capture.width}" data-height="${capture.height}"`));
  assert.equal(await frameColour(video, 0, REGION.left), 'red', 'left half of the first frame is the red source half');
  assert.equal(await frameColour(video, 0, REGION.right), 'blue', 'right half of the first frame is the blue source half');
  return { receipt, video };
}

test('a 128x72 canvas exports and previews at 128x72 via a 2x capture; a 1280x160 canvas previews at 640x80', { timeout: 180000 }, async t => {
  assert.ok(process.env.PRODUCER_HEADLESS_SHELL_PATH, 'Set PRODUCER_HEADLESS_SHELL_PATH for this integration check');
  process.env.HF_DE_STALL_MS ??= '15000'; // a regression fails in 15 s instead of 60 s
  const dir = await tempDir('render-size-');
  t.after(() => fs.rm(dir, { recursive: true, force: true }));

  const tiny = await project(dir, 'tiny', [128, 72], { caption: true });
  const exported = await assertRender(tiny, path.join(dir, 'tiny-export'), { preview: false, size: [128, 72], capture: { width: 256, height: 144 } });
  await assertRender(tiny, path.join(dir, 'tiny-preview'), { preview: true, size: [128, 72], capture: { width: 256, height: 144 } });
  // The white caption is drawn over the red/blue picture at centerY 0.8 (green appears only from white: about 27 with the caption, 0 without).
  const [, green] = await frameColor(exported.video, 0, CAPTION_BAND);
  assert.ok(green > 10, `caption visible in its band after the downscale (mean green ${green})`);
  const qa = await qaRender(tiny, path.join(dir, 'tiny-export'), path.join(dir, 'tiny-qa'));
  assert.equal(qa.checks.find(c => c.id === 'resolution').status, 'pass');

  const wide = await project(dir, 'wide', [1280, 160]);
  await assertRender(wide, path.join(dir, 'wide-preview'), { preview: true, size: [640, 80], capture: { width: 1280, height: 160 } });
});
