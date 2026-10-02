import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { SCHEMA, SCHEMA_V2, validateV2, migrateV1, readProject, editProject, editBatch, digest, run, createProject } from '../project.mjs';
import { compose } from '../composition.mjs';
import { canonicalJson, operationsSha256 } from '../operations.mjs';
import { lintComposition } from '../render.mjs';
import { resolveCaptions } from '../timeline.mjs';

const fixtures = fileURLToPath(new URL('../../../tests/fixtures/edit-document-v2/', import.meta.url));
const load = async (dir, name) => JSON.parse(await fs.readFile(path.join(fixtures, dir, name), 'utf8'));

test('shared fixtures: every valid document passes semantic validation', async () => {
  const names = (await fs.readdir(path.join(fixtures, 'valid'))).filter(n => n.endsWith('.json'));
  assert.ok(names.length > 0);
  for (const name of names) {
    const doc = await load('valid', name);
    assert.doesNotThrow(() => validateV2(doc), name);
  }
});
// File name = violated rule. Known names also assert the rejection reason.
const reasons = { 'audio-only-asset-on-video-track': /has no video/, 'caption-link-reversed-range': /link range/,
  'caption-link-unknown-item': /unknown media item/, 'caption-on-video-track': /must be on a caption track/,
  'duplicate-item-id': /Duplicate item id/, 'first-revision-with-parent': /parent digest/,
  'free-caption-missing-timing': /requires start_frame\/frames/, 'media-missing-source-in': /requires asset_id/,
  'same-track-overlap': /Overlapping/, 'source-range-exceeds-asset': /exceeds asset/, 'unknown-asset': /Unknown asset/,
  'unknown-track': /Unknown track/,
  // P2 packaging and audio.
  'caption-with-speed': /cannot carry speed, fades or transitions/, 'crossfade-overlap-mismatch': /overlap its predecessor .* by exactly 12/,
  'crossfade-without-overlap': /Crossfade talk1 must overlap/, 'duck-on-video-track': /only allowed on audio tracks/,
  'duck-under-self': /cannot duck under itself/, 'duck-under-unknown-track': /Duck under unknown track/,
  'fades-exceed-item': /Fades exceed item length/, 'graphic-on-caption-track': /must be on a video track/,
  'graphic-var-not-primitive': /Graphic var title must be a string/, 'graphic-with-media-field': /cannot carry media\/caption fields: volume/,
  'overlap-without-crossfade': /without crossfade: talk1, talk2/, 'speed-source-exceeds-asset': /exceeds asset \(speed-scaled\): talk2/ };
test('shared fixtures: every invalid document is rejected', async () => {
  const names = (await fs.readdir(path.join(fixtures, 'invalid'))).filter(n => n.endsWith('.json'));
  assert.ok(names.length >= 12);
  for (const name of names) {
    const doc = await load('invalid', name);
    assert.throws(() => validateV2(doc), reasons[name.slice(0, -5)] ?? Error, `${name} must be rejected`);
  }
});

const sha = c => c.repeat(64);
function v1Fixture() {
  return { schema_version: SCHEMA, project_id: 'legacy', title: '旧工程', revision: 1, parent_sha256: null,
    canvas: { width: 640, height: 360, fps: 24 },
    assets: [{ id: 'source', sha256: sha('a'), file: `assets/${sha('a')}.media`, duration: 6, video: true, audio: true, width: 640, height: 360 }],
    clips: [{ id: 'first', asset_id: 'source', in_seconds: 1, frames: 48, volume: 1, fit: 'contain', captions: [{ from: 0.5, to: 2, text: '第一句' }] },
      { id: 'second', asset_id: 'source', in_seconds: 4, frames: 24, volume: 0.5, fit: 'cover', captions: [{ from: 4, to: 5, text: '第二句' }] }],
    audio: [{ id: 'bed', asset_id: 'source', in_seconds: 0, start_frame: 48, frames: 96, volume: 0.2 },
      { id: 'late', asset_id: 'source', in_seconds: 0, start_frame: 60, frames: 10, volume: 0.2 },
      { id: 'gone', asset_id: 'source', in_seconds: 0, start_frame: 80, frames: 10, volume: 0.2 }] };
}
function v2Fixture() {
  return { schema_version: SCHEMA_V2, project_id: 'multi', title: '多轨', revision: 1, parent_sha256: null,
    canvas: { width: 640, height: 360, fps: 24 },
    assets: [{ id: 'talk', sha256: sha('a'), file: `assets/${sha('a')}.media`, duration: 10, video: true, audio: true, width: 640, height: 360, origin: { kind: 'import' } },
      { id: 'broll', sha256: sha('b'), file: `assets/${sha('b')}.media`, duration: 4, video: true, audio: false, width: 640, height: 360, origin: { kind: 'generated', provenance_ref: 'jobs/b.json' } },
      { id: 'music', sha256: sha('c'), file: `assets/${sha('c')}.media`, duration: 20, video: false, audio: true, width: 0, height: 0, origin: { kind: 'import' } }],
    tracks: [{ id: 'v_main', kind: 'video', locked: false }, { id: 'v_broll', kind: 'video', locked: false },
      { id: 'a_music', kind: 'audio', locked: false }, { id: 'c_sub', kind: 'caption', locked: false }],
    items: [
      { id: 'talk1', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 0, frames: 48, source_in_seconds: 1, volume: 1, fit: 'cover' },
      { id: 'talk2', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 48, frames: 48, source_in_seconds: 5, volume: 1, fit: 'cover' },
      { id: 'over', track_id: 'v_broll', kind: 'media', asset_id: 'broll', start_frame: 24, frames: 24, source_in_seconds: 0, volume: 0,
        transform: { x: 0.75, y: 0.25, scale: 0.4 }, opacity: 0.8 },
      { id: 'bed', track_id: 'a_music', kind: 'media', asset_id: 'music', start_frame: 0, frames: 96, source_in_seconds: 0, volume: 0.2 },
      { id: 'cap1', track_id: 'c_sub', kind: 'caption', text: '跨切点', link: { item_id: 'talk1', source_from: 1.5, source_to: 2.5 } },
      { id: 'cap2', track_id: 'c_sub', kind: 'caption', text: '后半句', link: { item_id: 'talk1', source_from: 2.6, source_to: 2.9 } },
      { id: 'title', track_id: 'c_sub', kind: 'caption', text: '标题 <b>', start_frame: 60, frames: 24 }],
    change: { author: 'system', summary: 'fixture', operations_sha256: null } };
}
async function onDisk(t, doc) {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'creative-v2-test-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  await fs.mkdir(path.join(dir, 'revisions'));
  await fs.writeFile(path.join(dir, 'revisions/000001.json'), `${JSON.stringify(doc, null, 2)}\n`);
  return dir;
}
const revisions = async dir => (await fs.readdir(path.join(dir, 'revisions'))).filter(n => n.endsWith('.json')).length;
const r9 = v => Math.round(v * 1e9) / 1e9;
const batch = (base_revision, operations) => ({ base_revision, author: 'agent', summary: 'test', operations });

test('v2 composition: track order is z order, transform/opacity, separate audio, linked and free captions', () => {
  const { html, cues, frames } = compose(v2Fixture());
  assert.equal(frames, 96);
  assert.match(html, /id="v-talk1"[^>]*data-track-index="0"[^>]*style="z-index:1;object-fit:cover"/);
  assert.match(html, /id="v-over"[^>]*data-track-index="1"[^>]*style="z-index:2;object-fit:contain;left:55%;top:5%;right:auto;bottom:auto;width:40%;height:40%;opacity:0.8"/);
  assert.match(html, /id="a-talk1"[^>]*data-volume="1"/);
  assert.ok(!html.includes('id="a-over"'), 'silent B-roll asset emits no audio');
  assert.match(html, /id="a-bed"[^>]*data-track-index="102"[^>]*data-volume="0.2"/);
  assert.match(html, /标题 &lt;b&gt;/);
  // cap1 source 1.5–2.5 inside talk1 (source 1–3, output 0–2): output 0.5–1.5.
  assert.deepEqual(cues.map(c => [c.text, r9(c.start), r9(c.end)]), [['跨切点', 0.5, 1.5], ['后半句', 1.6, 1.9], ['标题 <b>', 2.5, 3.5]]);
});
test('linked captions follow trims and vanish when their source leaves the item', () => {
  const doc = v2Fixture();
  const talk1 = doc.items[0];
  talk1.source_in_seconds = 2; talk1.frames = 12; // source 2.0–2.5
  assert.deepEqual(resolveCaptions(doc).filter(c => c.item.link).map(c => [c.item.id, c.start, c.end]), [['cap1', 0, 0.5]]);
});
// Rules shared with the Python core (P1) beyond the contract text; one inline case each.
test('cross-language rules: kind-exclusive fields, linked caption timing, parent digest by revision', () => {
  const cases = {
    'media item must not carry text/style/link': [
      d => { d.items[0].text = 'x'; }, d => { d.items[0].style = { fontHeight: .04, centerY: .8, color: '#ffffff', strokeWidth: 0, weight: 600 }; },
      d => { d.items[0].link = { item_id: 'talk2', source_from: 5, source_to: 6 }; }],
    'caption item must not carry asset_id/source_in_seconds/volume': [
      d => { d.items[6].asset_id = 'talk'; }, d => { d.items[6].source_in_seconds = 0; }, d => { d.items[6].volume = 1; }],
    'linked caption must not carry start_frame/frames': [d => { d.items[4].start_frame = 0; }, d => { d.items[4].frames = 12; }],
    'parent_sha256 is null exactly at revision 1': [d => { d.parent_sha256 = sha('d'); }, d => { d.revision = 2; },
      d => { d.revision = 2; d.parent_sha256 = 42; }],
  };
  for (const [rule, mutations] of Object.entries(cases)) {
    for (const mutate of mutations) {
      const doc = v2Fixture(); mutate(doc);
      assert.throws(() => validateV2(doc), Error, rule);
    }
  }
  assert.doesNotThrow(() => validateV2({ ...v2Fixture(), revision: 2, parent_sha256: sha('d') }));
});
// P2 rules agreed with the Python core beyond the contract text (root fixtures are
// added on the Python side); one inline negative case each on the P2 fixture.
test('P2 cross-language rules: graphic field whitelist, duck target kind, crossfade ordering and full overlap scan', async () => {
  const base = await load('valid', 'p2-packaging.json');
  const graphic = d => d.items.find(i => i.id === 'lower');
  const cases = {
    'graphic accepts only template/vars/timing/fades/opacity': [
      d => { graphic(d).transform = { x: .5, y: .5, scale: .5 }; }, d => { graphic(d).transition_in = { kind: 'crossfade', frames: 2 }; },
      d => { graphic(d).speed = 1; }, d => { graphic(d).fit = 'cover'; }],
    'duck target must be a video or audio track': [d => { d.tracks.find(t => t.id === 'a_music').duck.under_track_id = 'c_sub'; }],
    'crossfade must start strictly after its predecessor': [d => {
      Object.assign(d.items.find(i => i.id === 'talk1'), { frames: 10, fade_in_frames: 0 });
      Object.assign(d.items.find(i => i.id === 'talk2'), { start_frame: 0, transition_in: { kind: 'crossfade', frames: 10 } });
      d.items = d.items.filter(i => i.id !== 'cap1');
    }],
    'overlap is checked against every earlier item, not only the adjacent one': [d => {
      Object.assign(d.items.find(i => i.id === 'talk1'), { frames: 100 });
      Object.assign(d.items.find(i => i.id === 'talk2'), { start_frame: 90, frames: 110, speed: 1, fade_out_frames: 0 });
      d.items.push({ id: 'talk3', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 95, frames: 110, source_in_seconds: 0, volume: 1,
        transition_in: { kind: 'crossfade', frames: 105 } });
    }],
  };
  assert.doesNotThrow(() => validateV2(base));
  for (const [rule, mutations] of Object.entries(cases)) {
    for (const mutate of mutations) {
      const doc = structuredClone(base); mutate(doc);
      assert.throws(() => validateV2(doc), Error, rule);
    }
  }
  const ordered = structuredClone(base);
  cases['crossfade must start strictly after its predecessor'][0](ordered);
  assert.throws(() => validateV2(ordered), /must start after its predecessor/);
  const scanned = structuredClone(base);
  cases['overlap is checked against every earlier item, not only the adjacent one'][0](scanned);
  assert.throws(() => validateV2(scanned), /overlaps more than its predecessor/);
});
test('compiled v2 HTML passes the HyperFrames lint gate', async () => {
  const lint = await lintComposition(compose(v2Fixture()).html);
  assert.equal(lint.error_count, 0, JSON.stringify(lint.findings));
  assert.equal(lint.warning_count, 0, JSON.stringify(lint.findings));
  assert.equal(lint.blocked, false);
});
test('lint gate blocks compositions with error findings', async () => {
  const lint = await lintComposition('<html><body><div data-composition-id="main"><video src="x.mp4" data-start="0"></video></div></body></html>');
  assert.ok(lint.error_count > 0 && lint.blocked, JSON.stringify(lint));
});
test('migration preserves v1 timing: clips, linked captions, beds split into lanes and truncated', () => {
  const v1 = v1Fixture();
  const v2 = { ...migrateV1(v1), revision: 1, parent_sha256: null };
  validateV2(v2);
  assert.deepEqual(compose(v2).cues, compose(v1).cues);
  assert.equal(compose(v2).frames, compose(v1).frames);
  const bed = v2.items.find(i => i.id === 'bed'), late = v2.items.find(i => i.id === 'late');
  assert.equal(bed.frames, 24); // truncated at the v1 output end (72)
  assert.equal(late.track_id, 'a_bed_2');
  assert.ok(!v2.items.some(i => i.id === 'gone'), 'bed entirely after the v1 end is dropped');
  assert.ok(v2.assets.every(a => a.origin.kind === 'import'));
});
test('v1 batch triggers a pure migration revision then the edit revision; v1 file untouched', async t => {
  const dir = await onDisk(t, v1Fixture());
  const original = await digest(path.join(dir, 'revisions/000001.json'));
  const result = await editBatch(dir, batch(1, [{ type: 'set_item_props', item_id: 'second', props: { volume: 0.25 } }]));
  assert.equal(result.migration_revision, 2);
  assert.equal(result.revision, 3);
  const migration = await readProject(dir, 2), edited = await readProject(dir, 3);
  assert.equal(migration.change.author, 'migration');
  assert.equal(migration.schema_version, SCHEMA_V2);
  assert.equal(edited.parent_sha256, await digest(path.join(dir, 'revisions/000002.json')));
  assert.equal(edited.items.find(i => i.id === 'second').volume, 0.25);
  assert.equal(edited.change.operations_sha256, operationsSha256([{ type: 'set_item_props', item_id: 'second', props: { volume: 0.25 } }]));
  assert.equal(await digest(path.join(dir, 'revisions/000001.json')), original);
  await assert.rejects(editProject(dir, 3, [{ type: 'reorder', clip_ids: ['second', 'first'] }]), /v1 operations are not supported/);
});
test('operations digest uses canonical JSON (key order independent)', () => {
  assert.equal(canonicalJson({ b: 1, a: [{ d: 2, c: 'x' }] }), '{"a":[{"c":"x","d":2}],"b":1}');
  assert.equal(operationsSha256([{ type: 'x', a: 1 }]), operationsSha256([{ a: 1, type: 'x' }]));
});
test('stale base revision, invalid op and bad result are all rejected atomically', async t => {
  const dir = await onDisk(t, v2Fixture());
  await assert.rejects(editBatch(dir, batch(2, [{ type: 'remove_item', item_id: 'title' }])), /conflict/);
  await assert.rejects(editBatch(dir, batch(1, [{ type: 'remove_item', item_id: 'title' }, { type: 'explode' }])), /Unknown edit operation/);
  await assert.rejects(editBatch(dir, batch(1, [{ type: 'move_item', item_id: 'talk2', start_frame: 24 }])), /Overlapping/);
  await assert.rejects(editBatch(dir, { ...batch(1, [{ type: 'remove_item', item_id: 'title' }]), author: 'migration' }), /Invalid edit batch/);
  assert.equal(await revisions(dir), 1);
});
test('dry-run returns a diff and writes nothing', async t => {
  const dir = await onDisk(t, v2Fixture());
  const result = await editBatch(dir, batch(1, [{ type: 'remove_item', item_id: 'talk2', ripple: true },
    { type: 'add_item', item: { id: 'note', track_id: 'c_sub', kind: 'caption', text: '新', start_frame: 0, frames: 12 } }]), { dryRun: true });
  assert.equal(result.status, 'dry_run');
  assert.deepEqual(result.diff.items, { added: ['note'], removed: ['talk2'], changed: [] });
  assert.deepEqual(result.diff.duration_frames, { before: 96, after: 96 });
  assert.equal(await revisions(dir), 1);
  assert.deepEqual((await fs.readdir(dir)).sort(), ['revisions']);
});
test('locked tracks refuse modification, removal and moves into them', async t => {
  const dir = await onDisk(t, v2Fixture());
  await editBatch(dir, batch(1, [{ type: 'trim_item', item_id: 'talk2', tail_frames: 4 }]));
  await assert.rejects(editBatch(dir, batch(2, [{ type: 'trim_item', item_id: 'talk2', tail_frames: 4 }, { type: 'edit_track', track_id: 'v_main', locked: true }])),
    /only operation/, 'a lock change cannot share a batch');
  await editBatch(dir, batch(2, [{ type: 'edit_track', track_id: 'v_main', locked: true }]));
  for (const op of [{ type: 'trim_item', item_id: 'talk2', tail_frames: 4 }, { type: 'remove_item', item_id: 'talk1' },
    { type: 'set_item_props', item_id: 'talk1', props: { volume: 0 } }, { type: 'move_item', item_id: 'over', track_id: 'v_main' },
    { type: 'add_item', item: { id: 'extra', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 96, frames: 4, source_in_seconds: 0, volume: 1 } },
    { type: 'split_item', item_id: 'talk1', at_frame: 10, new_item_id: 'x' }]) {
    await assert.rejects(editBatch(dir, batch(3, [op])), /locked/, op.type);
  }
  await assert.rejects(editBatch(dir, batch(3, [{ type: 'revert_to', revision: 1 }])), /locked/, 'revert must not unlock-and-change');
  // Unlock-then-edit in one batch is the bypass the batch rule closes.
  await assert.rejects(editBatch(dir, batch(3, [{ type: 'edit_track', track_id: 'v_main', locked: false }, { type: 'trim_item', item_id: 'talk2', tail_frames: 4 }])), /only operation/);
  assert.equal(await revisions(dir), 3);
  // Reverting to an unlocked revision with identical locked-track items keeps the lock.
  await editBatch(dir, batch(3, [{ type: 'revert_to', revision: 2 }]));
  assert.equal((await readProject(dir)).tracks.find(tr => tr.id === 'v_main').locked, true);
  await editBatch(dir, batch(4, [{ type: 'edit_track', track_id: 'v_main', locked: false }]));
  await editBatch(dir, batch(5, [{ type: 'trim_item', item_id: 'talk2', tail_frames: 4 }]));
  assert.equal((await readProject(dir)).items.find(i => i.id === 'talk2').frames, 40);
});
test('split assigns linked captions by source_from; trim/slip/move/ripple behave', async t => {
  const dir = await onDisk(t, v2Fixture());
  // talk1 source 1–3 s; cut at frame 36 → source 2.5. cap1 (1.5) stays left, cap2 (2.6) goes right.
  await editBatch(dir, batch(1, [{ type: 'split_item', item_id: 'talk1', at_frame: 36, new_item_id: 'talk1b' }]));
  let doc = await readProject(dir);
  const right = doc.items.find(i => i.id === 'talk1b');
  assert.deepEqual([right.start_frame, right.frames, right.source_in_seconds], [36, 12, 2.5]);
  assert.equal(doc.items.find(i => i.id === 'cap1').link.item_id, 'talk1');
  assert.equal(doc.items.find(i => i.id === 'cap2').link.item_id, 'talk1b');
  assert.deepEqual(compose(doc).cues.slice(0, 2).map(c => [r9(c.start), r9(c.end)]), [[0.5, 1.5], [1.6, 1.9]]);
  await editBatch(dir, batch(2, [{ type: 'trim_item', item_id: 'talk1', head_frames: 12 }, { type: 'trim_item', item_id: 'talk2', slip_seconds: -1 },
    { type: 'move_item', item_id: 'title', start_frame: 0 }]));
  doc = await readProject(dir);
  const talk1 = doc.items.find(i => i.id === 'talk1');
  assert.deepEqual([talk1.start_frame, talk1.frames, talk1.source_in_seconds], [12, 24, 1.5]);
  assert.equal(doc.items.find(i => i.id === 'talk2').source_in_seconds, 4);
  await editBatch(dir, batch(3, [{ type: 'remove_item', item_id: 'talk1', ripple: true }]));
  doc = await readProject(dir);
  assert.equal(doc.items.find(i => i.id === 'talk1b').start_frame, 12);
  assert.ok(!doc.items.some(i => i.id === 'cap1'), 'linked caption removed with its media');
});
test('replace_media drops old linked captions unless new ones are given; revert_to must be alone', async t => {
  const dir = await onDisk(t, v2Fixture());
  await editBatch(dir, batch(1, [{ type: 'replace_media', item_id: 'talk2', asset_id: 'broll', source_in_seconds: 0 },
    { type: 'replace_media', item_id: 'talk1', asset_id: 'talk', source_in_seconds: 3,
      captions: [{ id: 'fresh', track_id: 'c_sub', text: '新台词', source_from: 3, source_to: 4 }] }]));
  let doc = await readProject(dir);
  assert.ok(!doc.items.some(i => ['cap1', 'cap2'].includes(i.id)));
  assert.equal(doc.items.find(i => i.id === 'fresh').link.item_id, 'talk1');
  await assert.rejects(editBatch(dir, batch(2, [{ type: 'revert_to', revision: 1 }, { type: 'remove_item', item_id: 'title' }])), /only operation/);
  await editBatch(dir, batch(2, [{ type: 'revert_to', revision: 1 }]));
  doc = await readProject(dir);
  assert.equal(doc.revision, 3);
  assert.deepEqual(doc.items, v2Fixture().items);
});
test('create accepts a v2 spec; add_asset dry-run probes without copying', async t => {
  const dir = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'creative-v2-create-'));
  t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const clip = path.join(dir, 'clip.mp4'), extra = path.join(dir, 'extra.mp4'), root = path.join(dir, 'project');
  await run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=24:duration=1', '-pix_fmt', 'yuv420p', clip]);
  await run('ffmpeg', ['-v', 'error', '-f', 'lavfi', '-i', 'smptebars=size=128x72:rate=24:duration=1', '-pix_fmt', 'yuv420p', extra]);
  const unprovenanced = { project_id: 'spec2', title: 'v2 spec', canvas: { width: 128, height: 72, fps: 24 },
    assets: [{ id: 'clip', path: clip, origin: { kind: 'generated' } }], tracks: [{ id: 'v_main', kind: 'video', locked: false }],
    items: [{ id: 'one', track_id: 'v_main', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 24, source_in_seconds: 0, volume: 0 }] };
  await assert.rejects(createProject(root, unprovenanced), /provenance_ref/, 'create applies the add_asset provenance rule');
  const created = await createProject(root, { project_id: 'spec2', title: 'v2 spec', canvas: { width: 128, height: 72, fps: 24 },
    assets: [{ id: 'clip', path: clip }], tracks: [{ id: 'v_main', kind: 'video', locked: false }],
    items: [{ id: 'one', track_id: 'v_main', kind: 'media', asset_id: 'clip', start_frame: 0, frames: 24, source_in_seconds: 0, volume: 0 }] });
  assert.equal(created.schema_version, SCHEMA_V2);
  const ops = [{ type: 'add_asset', id: 'extra', path: extra }, { type: 'add_track', track: { id: 'v_top', kind: 'video' } },
    { type: 'add_item', item: { id: 'two', track_id: 'v_top', kind: 'media', asset_id: 'extra', start_frame: 12, frames: 12, source_in_seconds: 0, volume: 0 } }];
  const before = (await fs.readdir(path.join(root, 'assets'))).length;
  const dry = await editBatch(root, batch(1, ops), { dryRun: true });
  assert.deepEqual(dry.diff.assets_added, ['extra']);
  assert.equal((await fs.readdir(path.join(root, 'assets'))).length, before);
  await editBatch(root, batch(1, ops));
  const doc = await readProject(root);
  assert.equal((await fs.readdir(path.join(root, 'assets'))).length, before + 1);
  assert.deepEqual(doc.assets.find(a => a.id === 'extra').origin, { kind: 'import' });
  assert.deepEqual(doc.tracks.at(-1), { locked: false, id: 'v_top', kind: 'video' });
});
