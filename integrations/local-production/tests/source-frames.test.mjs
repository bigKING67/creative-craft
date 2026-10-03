import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFrameRate, probedFrameRate, reduceFrameRate, snapSourceFrames, sourceFrameAt } from '../source-frames.mjs';
import { validateV2 } from '../edit-document.mjs';
import { compose } from '../composition.mjs';
import { activeCaptions } from '../caption-font.mjs';
import { cutPoints } from '../burned-captions.mjs';
import { createProject, editBatch, readProject, run } from '../project.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = async name => JSON.parse(await fs.readFile(path.resolve(here, '../../../tests/fixtures/edit-document-v2', name), 'utf8'));

test('sourceFrameAt at 30/1: truncated decimals snap up, otherwise the containing frame', () => {
  // 733/30 = 24.4333…: the written 24.4333 is 0.001 frame below frame 733.
  assert.deepEqual(sourceFrameAt(24.4333, '30/1'), { frame: 733, start_seconds: 733 / 30, mid_seconds: 1467 / 60 });
  assert.equal(sourceFrameAt(24.433333, '30/1').frame, 733);
  // Frame start − 3.3e-5 s (≈ 0.001 frame) is that frame.
  assert.equal(sourceFrameAt(733 / 30 - 3.3e-5, '30/1').frame, 733);
  // Exactly 0.01 frame below is not absorbed (strictly less than 0.01 is).
  assert.equal(sourceFrameAt(24.433, '30/1').frame, 732); // 732.99 frames
  assert.equal(sourceFrameAt(24.4331, '30/1').frame, 733); // 732.993 frames
  assert.equal(sourceFrameAt(24.42, '30/1').frame, 732); // 732.6 frames: floor
  // Exactly on a frame boundary and exactly on a frame midpoint.
  assert.equal(sourceFrameAt(1, '30/1').frame, 30);
  assert.equal(sourceFrameAt(0, '30/1').frame, 0);
  assert.equal(sourceFrameAt(0, '30/1').mid_seconds, 1 / 60);
  assert.deepEqual(sourceFrameAt(24.45, '30/1'), { frame: 733, start_seconds: 733 / 30, mid_seconds: 24.45 });
  // Just before the next boundary but more than 0.01 frame away: still this frame.
  assert.equal(sourceFrameAt(24.46, '30/1').frame, 733); // 733.8 frames
  // Tiny and exponent-form numbers are exact too.
  assert.equal(sourceFrameAt(1e-7, '30/1').frame, 0);
  assert.equal(sourceFrameAt(2 / 30 - 1e-7, '30/1').frame, 2);
});

test('sourceFrameAt at 30000/1001 uses exact rational frame times', () => {
  const start = k => k * 1001 / 30000;
  for (const k of [1, 100, 733, 1798, 29970]) {
    assert.equal(sourceFrameAt(start(k), '30000/1001').frame, k, `start of ${k}`);
    assert.equal(sourceFrameAt(start(k) - 3.3e-5, '30000/1001').frame, k, `start of ${k} − 3.3e-5 s`);
    assert.equal(sourceFrameAt((2 * k + 1) * 1001 / 60000, '30000/1001').frame, k, `midpoint of ${k}`);
    assert.equal(sourceFrameAt(start(k) - 0.002, '30000/1001').frame, k - 1, `0.06 frame before ${k}`);
  }
  // 24.4333 s at 29.97 fps is 732.266 frames: frame 732.
  const at = sourceFrameAt(24.4333, '30000/1001');
  assert.equal(at.frame, 732);
  assert.equal(at.mid_seconds, 1465 * 1001 / 60000);
  assert.ok(at.start_seconds <= 24.4333 && 24.4333 < at.start_seconds + 1001 / 30000);
});

test('frame rate parsing, reduction and import rules', () => {
  assert.deepEqual(parseFrameRate('30000/1001'), { num: 30000n, den: 1001n });
  for (const bad of ['30', '0/1', '30/0', '30.0/1', '1234567/1', '', null]) assert.throws(() => parseFrameRate(bad), /Invalid frame_rate/);
  assert.equal(reduceFrameRate('60/2'), '30/1');
  assert.equal(reduceFrameRate('0/0'), null);
  const video = (r, avg, extra = {}) => ({ codec_type: 'video', r_frame_rate: r, avg_frame_rate: avg, time_base: '1/15360', start_pts: 0, ...extra });
  const audio = { codec_type: 'audio', r_frame_rate: '0/0', avg_frame_rate: '0/0', time_base: '1/44100', start_pts: 0 };
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1'), audio] }), '30/1');
  assert.equal(probedFrameRate({ streams: [video('30000/1001', '60000/2002')] }), '30000/1001');
  // Variable frame rate (r ≠ avg): none, the renderer behaviour is kept.
  assert.equal(probedFrameRate({ streams: [video('30/1', '1800000/60061'), audio] }), null);
  // Video starting after the media-time origin: frame k is not at k / rate.
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1', { start_pts: 512 }), audio] }), null);
  // Audio only, or only cover art.
  assert.equal(probedFrameRate({ streams: [audio] }), null);
  assert.equal(probedFrameRate({ streams: [audio, video('90000/1', '0/0', { disposition: { attached_pic: 1 } })] }), null);
});

test('validateV2: frame_rate only on assets with a picture and in rational form', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  validateV2(doc);
  const audioRate = await fixture('invalid/audio-asset-with-frame-rate.json');
  assert.throws(() => validateV2(audioRate),/Asset music frame_rate requires a video stream/);
  const bad = structuredClone(doc);
  bad.assets[0].frame_rate = '29.97';
  assert.throws(() => validateV2(bad), /Invalid frame_rate on asset talk/);
});

test('compilation snaps in-points of frame_rate assets; the document is not rewritten', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  doc.items.find(i => i.id === 'talk1').source_in_seconds = 2.0021; // 60.0029 frames at 29.97 → frame 60
  doc.items.find(i => i.id === 'broll1').source_in_seconds = 1.9999; // 59.997 frames → frame 60
  const before = structuredClone(doc);
  const { html, cues } = compose(doc);
  assert.deepEqual(doc, before, 'compile does not mutate');
  const mid = (k, num, den) => (2 * k + 1) * den / (2 * num);
  const start = id => Number(new RegExp(`id="${id}"[^>]*data-media-start="([^"]+)"`).exec(html)[1]);
  assert.equal(start('v-talk1'), mid(60, 30000, 1001));
  assert.equal(start('a-talk1'), mid(60, 30000, 1001), 'sound plays from the same source time as its picture');
  assert.equal(start('v-broll1'), mid(60, 30, 1));
  assert.equal(start('a-bed'), 0, 'audio-only asset unchanged');
  // talk2's 10.0 s is 299.7 frames → frame 299 (containing frame).
  assert.equal(start('v-talk2'), mid(299, 30000, 1001));
  // The linked caption (source 2.0–4.5 on talk1) maps through the compiled in-point.
  const compiledIn = mid(60, 30000, 1001);
  assert.ok(Math.abs(cues.find(c => c.text === '第一句').end - (4.5 - compiledIn)) < 1e-9);
  // Without frame_rate the written times are compiled as before.
  const plain = structuredClone(doc);
  for (const asset of plain.assets) delete asset.frame_rate;
  const plainHtml = compose(plain).html;
  assert.match(plainHtml, /id="v-talk1"[^>]*data-media-start="2.0021"/);
  assert.match(plainHtml, /id="v-broll1"[^>]*data-media-start="1.9999"/);
  assert.equal(snapSourceFrames(plain), plain);
});

test('caption visibility and QA cut points use the compiled in-point', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  const talk1 = doc.items.find(i => i.id === 'talk1');
  talk1.source_in_seconds = 4.4999; // 134.86 frames at 29.97 → frame 134, midpoint 4.4878 s
  doc.items.find(i => i.id === 'cap1').link.source_from = 4.49; // ends at 4.5: visible only through the compiled window
  doc.items.find(i => i.id === 'cap1').link.source_to = 4.495;
  assert.ok(activeCaptions(doc).some(c => c.id === 'cap1'));
  const points = cutPoints(doc).filter(p => p.item.id === 'talk1');
  const compiledIn = (2 * 134 + 1) * 1001 / 60000;
  assert.deepEqual(points.map(p => [p.edge, p.source_seconds, p.document_source_seconds, p.source_frame]),
    [['in', compiledIn, 4.4999, 134], ['out', compiledIn + 150 / 30, 4.4999, 134]]);
  const plain = structuredClone(doc);
  for (const asset of plain.assets) delete asset.frame_rate;
  const plainIn = cutPoints(plain).find(p => p.item.id === 'talk1' && p.edge === 'in');
  assert.equal(plainIn.source_seconds, 4.4999);
  assert.ok(!('source_frame' in plainIn));
});

test('import records frame_rate for video (create and add_asset), not for audio or v1 projects', async t => {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'frame-rate-import-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const ntsc = path.join(dir, 'ntsc.mp4'), pal = path.join(dir, 'pal.mp4'), tone = path.join(dir, 'tone.m4a');
  await run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30000/1001:duration=1', '-f', 'lavfi', '-i', 'sine=d=1',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', ntsc]);
  await run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=25:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', pal]);
  await run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'sine=d=1', '-c:a', 'aac', tone]);
  const root = path.join(dir, 'v2');
  const created = await createProject(root, { project_id: 'import-rate', title: 'import', canvas: { width: 320, height: 180, fps: 30 },
    assets: [{ id: 'ntsc', path: ntsc }, { id: 'tone', path: tone }],
    tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [{ id: 'a', track_id: 'v', kind: 'media', asset_id: 'ntsc', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0 }] });
  const rates = doc => Object.fromEntries(doc.assets.map(a => [a.id, a.frame_rate ?? null]));
  assert.deepEqual(rates(created), { ntsc: '30000/1001', tone: null });
  assert.ok(!('frame_rate' in created.assets.find(a => a.id === 'tone')));
  await editBatch(root, { base_revision: 1, author: 'agent', summary: 'add', operations: [{ type: 'add_asset', id: 'pal', path: pal }] });
  assert.deepEqual(rates(await readProject(root)), { ntsc: '30000/1001', tone: null, pal: '25/1' });
  // local-edit.v1 has no frame_rate field; its assets never get one.
  const v1 = await createProject(path.join(dir, 'v1'), { project_id: 'import-v1', title: 'v1', canvas: { width: 320, height: 180, fps: 30 },
    assets: [{ id: 'ntsc', path: ntsc }], clips: [{ id: 'c', asset_id: 'ntsc', in_seconds: 0, frames: 15, volume: 0, fit: 'contain', captions: [] }], audio: [] });
  assert.ok(!('frame_rate' in v1.assets[0]));
});
