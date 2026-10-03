// Explicit opt-in: real producer + Chrome (PRODUCER_HEADLESS_SHELL_PATH).
// Media time 0 is the earliest stream start, for the renderer as for QA; the
// import records frame_rate only when that is the video start.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createProject, ffprobeJson, run } from '../project.mjs';
import { renderProject } from '../render.mjs';
import { streamStart } from '../source-frames.mjs';
import { mediaTool } from '../media-analysis.mjs';
import { frameColor } from './media-fixtures.mjs';

const ff = (...args) => run(mediaTool('ffmpeg'), ['-v', 'error', ...args]);
// 30 fps, red frames 0..switchFrame-1, blue from switchFrame on, 320x180, plus a tone.
const redThenBlue = (switchFrame, seconds) => ['-f', 'lavfi', '-i', `color=red:s=320x180:r=30:d=${switchFrame / 30}`,
  '-f', 'lavfi', '-i', `color=blue:s=320x180:r=30:d=${seconds - switchFrame / 30}`];
const starts = async file => Object.fromEntries((await ffprobeJson(file)).streams.map(s => [s.codec_type, streamStart(s)]));
const colour = ([r, g, b]) => r > 150 && g < 80 && b < 80 ? 'red' : b > 150 && r < 80 && g < 80 ? 'blue' : `rgb(${r}, ${g}, ${b})`;

async function firstFrame(dir, name, file, sourceIn) {
  const root = path.join(dir, `${name}-project`), output = path.join(dir, `${name}-render`);
  const doc = await createProject(root, { project_id: name, title: name, canvas: { width: 320, height: 180, fps: 30 }, assets: [{ id: 'src', path: file }],
    tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [{ id: 'one', track_id: 'v', kind: 'media', asset_id: 'src', start_frame: 0, frames: 10, source_in_seconds: sourceIn, volume: 0.5, fit: 'cover' }] });
  const receipt = await renderProject(root, output, { preview: true });
  assert.equal(receipt.status, 'completed');
  const html = await fs.readFile(path.join(output, 'index.html'), 'utf8');
  return { asset: doc.assets[0], mediaStart: Number(/<video[^>]*data-media-start="([^"]+)"/.exec(html)[1]),
    colour: colour(await frameColor(path.join(output, 'video.mp4'), 0)) };
}

test('media time 0 is the earliest stream start; frame_rate only when that is the video start', { timeout: 180000 }, async t => {
  assert.ok(process.env.PRODUCER_HEADLESS_SHELL_PATH, 'Set PRODUCER_HEADLESS_SHELL_PATH for this integration check');
  process.env.HF_DE_STALL_MS ??= '15000';
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'source-start-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));

  // 1. Video and audio both start at 0.5 s (MKV keeps the offset): frame_rate is
  // recorded and the truncated in-point 0.7333 (frame 22 starts at 0.7333…) is
  // corrected to frame 22, the first blue frame, 0.5 s into the file.
  const shifted = path.join(dir, 'shifted.mkv');
  await ff(...redThenBlue(22, 2), '-f', 'lavfi', '-i', 'sine=d=2', '-filter_complex', '[0:v][1:v]concat=n=2:v=1,format=yuv420p[v]', '-map', '[v]', '-map', '2:a',
    '-c:v', 'libx264', '-g', '1', '-c:a', 'aac', '-output_ts_offset', '0.5', shifted);
  const shiftedStarts = await starts(shifted);
  if (!(shiftedStarts.video > 0 && shiftedStarts.video === shiftedStarts.audio)) {
    t.skip(`ffmpeg ${JSON.stringify(shiftedStarts)}: could not build a file whose streams all start at the same non-zero time`);
  } else {
    const truncated = await firstFrame(dir, 'shifted', shifted, 0.7333);
    assert.equal(truncated.asset.frame_rate, '30/1');
    assert.equal(truncated.mediaStart, 0.733433333, 'corrected to frame 22 + 0.1 ms');
    assert.equal(truncated.colour, 'blue', 'frame 22 (first blue) is on screen: media time 0 = the 0.5 s video start');
    assert.equal((await firstFrame(dir, 'shifted-21', shifted, 0.72)).colour, 'red', 'frame 21 is still red');
  }

  // 2. Audio starting 67 ms before the video (MKV keeps a negative start; the
  // reproduction from the stall investigation): no frame_rate, the written
  // in-point is compiled as is and the renderer shows video time in-point − 0.067.
  // Red frames 0..29 (0–1 s), blue from 1 s.
  const primed = path.join(dir, 'primed.mkv');
  await ff(...redThenBlue(30, 3), '-itsoffset', '-0.067', '-f', 'lavfi', '-i', 'sine=d=3',
    '-filter_complex', '[0:v][1:v]concat=n=2:v=1,format=yuv420p[v]', '-map', '[v]', '-map', '2:a',
    '-c:v', 'libx264', '-g', '1', '-c:a', 'aac', '-avoid_negative_ts', 'disabled', primed);
  const primedStarts = await starts(primed);
  assert.ok(primedStarts.video === 0 && primedStarts.audio < -0.06, `fixture: ${JSON.stringify(primedStarts)}`);
  // 1.0333 is 0.03 ms below frame 31 (1.03333…): the 0.6.0 rule recorded 30/1 and
  // corrected it; video time 1.0333 − 0.067 = 0.966 is red either way.
  const early = await firstFrame(dir, 'primed', primed, 1.0333);
  assert.ok(!('frame_rate' in early.asset));
  assert.equal(early.mediaStart, 1.0333, 'written in-point kept');
  assert.equal(early.colour, 'red', 'video time 0.966: still the red second');
  // 1.06 − 0.067 = 0.993 is red as well; 1.1 − 0.067 = 1.033 is blue.
  assert.equal((await firstFrame(dir, 'primed-106', primed, 1.06)).colour, 'red');
  assert.equal((await firstFrame(dir, 'primed-110', primed, 1.1)).colour, 'blue');
});
