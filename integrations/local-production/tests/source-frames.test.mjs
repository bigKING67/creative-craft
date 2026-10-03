import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CORRECTION_SECONDS, compiledView, correctedSourceIn, correctionOf, parseFrameRate, pictureStream, probedFrameRate, reduceFrameRate,
  truncatedFrame } from '../source-frames.mjs';
import { validateV2 } from '../edit-document.mjs';
import { applyOperations } from '../operations.mjs';
import { compose } from '../composition.mjs';
import { activeCaptions } from '../caption-font.mjs';
import { cutPoints } from '../burned-captions.mjs';
import { SOURCE_END_TOLERANCE, resolveCaptions, sourceSeconds } from '../timeline.mjs';
import { createProject, editBatch, readProject, run } from '../project.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = async name => JSON.parse(await fs.readFile(path.resolve(here, '../../../tests/fixtures/edit-document-v2', name), 'utf8'));
const corrected = (k, num, den) => Math.round((k * den / num + CORRECTION_SECONDS) * 1e9) / 1e9;
const itemOf = (doc, id) => doc.items.find(i => i.id === id);

test('truncatedFrame at 30/1: only in-points strictly less than 0.01 frame below a frame start', () => {
  // 733/30 = 24.4333…: the written 24.4333 is 0.001 frame below frame 733.
  assert.equal(truncatedFrame(24.4333, '30/1'), 733);
  assert.deepEqual(correctedSourceIn(24.4333, '30/1'), { seconds: corrected(733, 30, 1), frame: 733 });
  assert.equal(correctedSourceIn(24.4333, '30/1').seconds, 24.433433333);
  assert.equal(truncatedFrame(24.433333, '30/1'), 733);
  assert.equal(truncatedFrame(733 / 30 - 3.3e-5, '30/1'), 733); // ≈ 0.001 frame below
  assert.equal(truncatedFrame(24.4331, '30/1'), 733); // 732.993 frames
  // Exactly 0.01 frame below is not a truncation (strictly less than 0.01 is).
  assert.equal(truncatedFrame(24.433, '30/1'), null); // 732.99 frames
  // Inside a frame, on a frame start, on a midpoint: kept as written.
  for (const kept of [24.42, 24.46, 24.45, 1, 0, 1e-7, 0.5]) assert.equal(correctedSourceIn(kept, '30/1'), null, String(kept));
  assert.equal(truncatedFrame(2 / 30 - 1e-7, '30/1'), 2);
});

test('truncatedFrame at 30000/1001 uses exact rational frame times', () => {
  const start = k => k * 1001 / 30000;
  for (const k of [1, 100, 733, 1798, 29970]) {
    assert.equal(truncatedFrame(start(k) - 3.3e-5, '30000/1001'), k, `start of ${k} − 3.3e-5 s`);
    assert.equal(truncatedFrame((2 * k + 1) * 1001 / 60000, '30000/1001'), null, `midpoint of ${k}`);
    assert.equal(truncatedFrame(start(k) - 0.002, '30000/1001'), null, `0.06 frame before ${k}`);
  }
  assert.equal(truncatedFrame(24.4333, '30000/1001'), null); // 732.266 frames
  assert.deepEqual(correctedSourceIn(4.5044, '30000/1001'), { seconds: corrected(135, 30000, 1001), frame: 135 });
});

test('frame rate parsing, reduction and import rules', () => {
  assert.deepEqual(parseFrameRate('30000/1001'), { num: 30000n, den: 1001n });
  for (const bad of ['30', '0/1', '30/0', '30.0/1', '1234567/1', '', null]) assert.throws(() => parseFrameRate(bad), /Invalid frame_rate/);
  assert.equal(reduceFrameRate('60/2'), '30/1');
  assert.equal(reduceFrameRate('0/0'), null);
  const video = (r, avg, extra = {}) => ({ codec_type: 'video', r_frame_rate: r, avg_frame_rate: avg, time_base: '1/15360', start_pts: 0, start_time: '0.000000', ...extra });
  const audio = { codec_type: 'audio', r_frame_rate: '0/0', avg_frame_rate: '0/0', time_base: '1/44100', start_pts: 0, start_time: '0.000000' };
  const at0 = streams => ({ streams, format: { start_time: '0.000000' } });
  assert.equal(probedFrameRate(at0([video('30/1', '30/1'), audio])), '30/1');
  assert.equal(probedFrameRate(at0([video('30000/1001', '60000/2002')])), '30000/1001');
  // Variable frame rate (r ≠ avg): none, the renderer behaviour is kept.
  assert.equal(probedFrameRate(at0([video('30/1', '1800000/60061'), audio])), null);
  // The picture stream must start at media time 0, and so must the file.
  assert.equal(probedFrameRate(at0([video('30/1', '30/1', { start_pts: 7680, start_time: '0.500000' }), audio])), null);
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1', { start_pts: 7680, start_time: '0.500000' })], format: { start_time: '0.500000' } }), null);
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1'), { ...audio, start_time: '-0.021333' }], format: { start_time: '-0.021333' } }), null);
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1', { start_time: undefined })], format: { start_time: '0.000000' } }), null);
  assert.equal(probedFrameRate({ streams: [video('30/1', '30/1')], format: {} }), null);
  // Audio only, or only cover art.
  assert.equal(probedFrameRate(at0([audio])), null);
  const cover = video('90000/1', '0/0', { width: 64, height: 64, disposition: { attached_pic: 1 } });
  assert.equal(probedFrameRate(at0([audio, cover])), null);
  assert.equal(pictureStream(at0([audio, cover])), null);
  // Cover art before the picture: width, height and frame rate all come from the picture.
  const picture = video('25/1', '25/1', { width: 160, height: 90, disposition: { attached_pic: 0 } });
  assert.equal(pictureStream(at0([cover, picture, audio])), picture);
  assert.equal(probedFrameRate(at0([cover, picture, audio])), '25/1');
});

test('validateV2: frame_rate only on assets with a picture and in rational form', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  validateV2(doc);
  const audioRate = await fixture('invalid/audio-asset-with-frame-rate.json');
  assert.throws(() => validateV2(audioRate), /Asset music frame_rate requires a video stream/);
  const bad = structuredClone(doc);
  bad.assets[0].frame_rate = '29.97';
  assert.throws(() => validateV2(bad), /Invalid frame_rate on asset talk/);
});

test('compilation corrects truncated in-points of video-track items only; the document is not rewritten', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  itemOf(doc, 'talk1').source_in_seconds = 4.5044; // 0.003 frame below frame 135 at 29.97
  itemOf(doc, 'talk2').source_in_seconds = 10; // 299.7 frames: inside frame 299, kept
  itemOf(doc, 'broll1').source_in_seconds = 1.9999; // 0.003 frame below frame 60 at 30
  // The talk asset (picture and sound) on the audio track, with a truncated in-point.
  doc.items.push({ id: 'talk-sound', track_id: 'a_music', kind: 'media', asset_id: 'talk', start_frame: 270, frames: 30, source_in_seconds: 4.5044, volume: 0.5 });
  validateV2(doc);
  const before = structuredClone(doc);
  const { html, cues } = compose(doc);
  assert.deepEqual(doc, before, 'compile does not mutate');
  const start = id => Number(new RegExp(`id="${id}"[^>]*data-media-start="([^"]+)"`).exec(html)[1]);
  assert.equal(start('v-talk1'), corrected(135, 30000, 1001));
  assert.equal(start('a-talk1'), corrected(135, 30000, 1001), 'the item\'s own sound plays from its picture\'s in-point');
  assert.equal(start('v-talk2'), 10, 'an in-point inside a frame is kept');
  assert.equal(start('v-broll1'), corrected(60, 30, 1));
  assert.equal(start('a-talk-sound'), 4.5044, 'audio-track items are never corrected');
  assert.equal(start('a-bed'), 0);
  // The linked caption (source 2.0–4.5 on talk1) is now outside talk1's window;
  // move it inside and it maps through the compiled in-point.
  const linked = structuredClone(doc);
  Object.assign(itemOf(linked, 'cap1').link, { source_from: 5, source_to: 6 });
  const cue = compose(linked).cues.find(c => c.text === '第一句');
  assert.ok(Math.abs(cue.start - (5 - corrected(135, 30000, 1001))) < 1e-9);
  assert.ok(!cues.some(c => c.text === '第一句'));
  // Without frame_rate the written times are compiled as before.
  const plain = structuredClone(doc);
  for (const asset of plain.assets) delete asset.frame_rate;
  const plainHtml = compose(plain).html;
  assert.match(plainHtml, /id="v-talk1"[^>]*data-media-start="4.5044"/);
  assert.match(plainHtml, /id="v-broll1"[^>]*data-media-start="1.9999"/);
});

test('the compiled view is computed once and shared: views, captions and cut points', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  itemOf(doc, 'talk1').source_in_seconds = 4.5044;
  const view = compiledView(doc);
  assert.equal(compiledView(view), view, 'a view is not corrected again');
  assert.notEqual(view, doc);
  const talk1 = itemOf(view, 'talk1');
  assert.deepEqual(correctionOf(talk1), { written: itemOf(doc, 'talk1'), frame: 135 });
  assert.equal(correctionOf(itemOf(view, 'talk2')), null);
  assert.equal(itemOf(view, 'talk2'), itemOf(doc, 'talk2'), 'unchanged items are shared');
  // Cut points of a view are its own items, matched to the document's items.
  const points = cutPoints(view);
  assert.ok(points.every(p => view.items.includes(p.item)));
  assert.ok(points.every(p => doc.items.includes(p.document) && p.document.id === p.item.id));
  // A caption visible only in the written window [4.5044, 4.50455] is not shown,
  // since the compiled in-point is 4.5046.
  Object.assign(itemOf(doc, 'cap1').link, { source_from: 4.5044, source_to: 4.50455 });
  assert.ok(resolveCaptions(doc).some(c => c.item.id === 'cap1'), 'visible in the written window');
  assert.ok(!activeCaptions(doc).some(c => c.id === 'cap1'), 'font runs follow the compiled view');
});

test('cut points: compiled in/out, the written in- and out-point, the frame', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  itemOf(doc, 'talk1').source_in_seconds = 4.5044;
  const [inPoint, outPoint] = cutPoints(doc).filter(p => p.item.id === 'talk1');
  const compiledIn = corrected(135, 30000, 1001);
  assert.deepEqual([inPoint.edge, inPoint.source_seconds, inPoint.document_source_seconds, inPoint.source_frame], ['in', compiledIn, 4.5044, 135]);
  assert.deepEqual([outPoint.edge, outPoint.source_seconds, outPoint.document_source_seconds], ['out', compiledIn + 150 / 30, 4.5044 + 150 / 30]);
  assert.ok(!('source_frame' in outPoint));
  assert.notEqual(outPoint.document_source_seconds, inPoint.document_source_seconds);
  // Uncorrected items and assets without frame_rate carry no document fields.
  const talk2 = cutPoints(doc).find(p => p.item.id === 'talk2' && p.edge === 'in');
  assert.ok(!('document_source_seconds' in talk2) && !('source_frame' in talk2));
  const plain = structuredClone(doc);
  for (const asset of plain.assets) delete asset.frame_rate;
  const plainIn = cutPoints(plain).find(p => p.item.id === 'talk1' && p.edge === 'in');
  assert.equal(plainIn.source_seconds, 4.5044);
  assert.ok(!('source_frame' in plainIn) && !('document_source_seconds' in plainIn));
});

test('split continuity: 24/1 source on a 60 fps canvas, split after 1 output frame', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  doc.canvas.fps = 60;
  doc.assets.find(a => a.id === 'broll').frame_rate = '24/1';
  doc.items = doc.items.filter(i => i.id === 'broll1');
  const broll = itemOf(doc, 'broll1');
  Object.assign(broll, { start_frame: 0, frames: 60 });
  for (const headIn of [0, 0.5, 1.2345]) {
    broll.source_in_seconds = headIn;
    const split = await applyOperations(doc, [{ type: 'split_item', item_id: 'broll1', at_frame: 1, new_item_id: 'tail' }], { imports: [] });
    validateV2(split);
    const view = compiledView(split), head = itemOf(view, 'broll1'), tail = itemOf(view, 'tail');
    assert.equal(head.source_in_seconds, headIn, `head ${headIn} kept`);
    assert.equal(tail.source_in_seconds, itemOf(split, 'tail').source_in_seconds, 'tail kept as written');
    assert.ok(Math.abs(tail.source_in_seconds - (head.source_in_seconds + sourceSeconds(head, 60))) < 1e-9, `tail starts where the head ends (${headIn})`);
  }
  // A truncated head (11/24 = 0.458333… written 0.4583) is corrected by 0.1 ms +
  // 0.0008 frame; its tail (11.399 frames) is kept, and both sides of the seam
  // still show the same source frame.
  broll.source_in_seconds = 0.4583;
  const split = await applyOperations(doc, [{ type: 'split_item', item_id: 'broll1', at_frame: 1, new_item_id: 'tail' }], { imports: [] });
  const view = compiledView(split), head = itemOf(view, 'broll1'), tail = itemOf(view, 'tail');
  assert.equal(head.source_in_seconds, corrected(11, 24, 1));
  assert.equal(tail.source_in_seconds, itemOf(split, 'tail').source_in_seconds);
  const headEnd = head.source_in_seconds + sourceSeconds(head, 60);
  assert.ok(headEnd - tail.source_in_seconds <= 0.01 / 24 + CORRECTION_SECONDS);
  assert.equal(Math.floor(headEnd * 24), Math.floor(tail.source_in_seconds * 24));
});

test('the corrected range stays inside the asset, up to the last source frame', async () => {
  const doc = await fixture('valid/source-frame-rates.json');
  const broll = itemOf(doc, 'broll1'); // asset broll: 8 s at 30/1 (frames 0–239)
  Object.assign(broll, { source_in_seconds: 7.4666, frames: 16 }); // frame 224 truncated; through frame 239
  validateV2(doc);
  const item = itemOf(compiledView(doc), 'broll1');
  assert.equal(item.source_in_seconds, corrected(224, 30, 1));
  const end = item.source_in_seconds + sourceSeconds(item, 30);
  assert.ok(end <= 8 + SOURCE_END_TOLERANCE, `compiled end ${end}`);
  assert.ok(end - (7.4666 + sourceSeconds(broll, 30)) <= 0.01 / 30 + CORRECTION_SECONDS + 1e-12, 'shift ≤ 0.01 frame + 0.1 ms');
  validateV2(compiledView(doc));
  // An asset ending so that the written range fits the tolerance but the
  // corrected one would not: the in-point is kept.
  doc.assets.find(a => a.id === 'broll').duration = 7.99905;
  validateV2(doc);
  assert.equal(itemOf(compiledView(doc), 'broll1').source_in_seconds, 7.4666);
  assert.ok(!('source_frame' in cutPoints(doc).find(p => p.item.id === 'broll1')));
});

test('import records frame_rate for v2 video (create and add_asset), not for audio, cover art, offset video or v1 projects', async t => {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'frame-rate-import-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const file = name => path.join(dir, name);
  const ff = (...args) => run('ffmpeg', ['-v', 'error', ...args]);
  await ff('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30000/1001:duration=1', '-f', 'lavfi', '-i', 'sine=d=1',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', file('ntsc.mp4'));
  await ff('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=25:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', file('pal.mp4'));
  await ff('-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=30:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-output_ts_offset', '0.5', file('late.mp4'));
  await ff('-f', 'lavfi', '-i', 'sine=d=1', '-c:a', 'aac', file('tone.m4a'));
  await ff('-f', 'lavfi', '-i', 'color=c=red:s=64x64', '-frames:v', '1', file('cover.png'));
  await ff('-f', 'lavfi', '-i', 'sine=d=1', '-i', file('cover.png'), '-map', '1', '-map', '0', '-c:v', 'png', '-c:a', 'aac', '-disposition:v:0', 'attached_pic', file('cover.m4a'));
  const root = path.join(dir, 'v2');
  const created = await createProject(root, { project_id: 'import-rate', title: 'import', canvas: { width: 320, height: 180, fps: 30 },
    assets: [{ id: 'ntsc', path: file('ntsc.mp4') }, { id: 'tone', path: file('tone.m4a') }, { id: 'late', path: file('late.mp4') }, { id: 'cover', path: file('cover.m4a') }],
    tracks: [{ id: 'v', kind: 'video', locked: false }],
    items: [{ id: 'a', track_id: 'v', kind: 'media', asset_id: 'ntsc', start_frame: 0, frames: 15, source_in_seconds: 0, volume: 0 }] });
  const rates = doc => Object.fromEntries(doc.assets.map(a => [a.id, a.frame_rate ?? null]));
  assert.deepEqual(rates(created), { ntsc: '30000/1001', tone: null, late: null, cover: null });
  assert.ok(!('frame_rate' in created.assets.find(a => a.id === 'tone')));
  // Cover art is not a picture: no video, no size, no frame rate (one stream selection).
  const cover = created.assets.find(a => a.id === 'cover');
  assert.deepEqual([cover.video, cover.audio, cover.width, cover.height], [false, true, 0, 0]);
  // The video starting at 0.5 s is still a picture, without a frame grid at k / rate.
  assert.deepEqual(['video', 'width', 'height'].map(k => created.assets.find(a => a.id === 'late')[k]), [true, 160, 90]);
  await editBatch(root, { base_revision: 1, author: 'agent', summary: 'add', operations: [{ type: 'add_asset', id: 'pal', path: file('pal.mp4') }] });
  assert.equal(rates(await readProject(root)).pal, '25/1');
  // local-edit.v1 has no frame_rate field; its imports are not probed for one.
  const v1 = await createProject(path.join(dir, 'v1'), { project_id: 'import-v1', title: 'v1', canvas: { width: 320, height: 180, fps: 30 },
    assets: [{ id: 'ntsc', path: file('ntsc.mp4') }], clips: [{ id: 'c', asset_id: 'ntsc', in_seconds: 0, frames: 15, volume: 0, fit: 'contain', captions: [] }], audio: [] });
  assert.ok(!('frame_rate' in v1.assets[0]));
});
