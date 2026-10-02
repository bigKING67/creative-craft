import * as fs from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createProject, editProject, editBatch, readProject, digest, run } from './project.mjs';
import { renderProject } from './render.mjs';
import { verifySmoke, verifyMultitrack, frameAt, pcmAt, mae } from './verify-smoke.mjs';

// Self-authored synthetic signals; no customer assets, ASR, TTS or paid APIs.
const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, '../..');
const base = path.resolve(process.argv[2] || path.join(repo, 'dist/local-production', new Date().toISOString().replace(/[:.]/g, '-')));
// QA output must validate against the shared JSON Schema. A Python with
// jsonschema is mandatory: missing it fails the smoke instead of skipping.
const python = process.env.CREATIVE_PYTHON || path.join(repo, '.venv/bin/python');
if (!existsSync(python)) throw new Error(`Schema validation needs Python with jsonschema: set CREATIVE_PYTHON or create ${python}`);
const validateSchema = async (schema, files) => run(python, ['-c', `import json,sys
from jsonschema import Draft202012Validator
schema=json.load(open(sys.argv[1]))
Draft202012Validator.check_schema(schema)
for f in sys.argv[2:]:
    Draft202012Validator(schema).validate(json.load(open(f)))
print(len(sys.argv)-2)`, path.join(repo, 'skills/creative-craft/schemas', schema), ...files]);
await validateSchema('render-qa.schema.json', [path.join(repo, 'tests/fixtures/render-qa/sample.json')]);

await fs.mkdir(base, { recursive: true });
const ffmpeg = process.env.CREATIVE_FFMPEG || 'ffmpeg';
const source = path.join(base, 'source.mp4'), broll = path.join(base, 'broll.mp4'), music = path.join(base, 'music.m4a');
await run(ffmpeg, ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24:duration=6',
  '-f', 'lavfi', '-i', 'aevalsrc=0.1*sin(2*PI*if(lt(t\\,3)\\,440\\,880)*t):s=48000:d=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', source]);
await run(ffmpeg, ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'smptehdbars=size=640x360:rate=24:duration=4', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', broll]);
await run(ffmpeg, ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'sine=frequency=660:sample_rate=48000:duration=8', '-c:a', 'aac', music]);
const before = await digest(source);
const summary = { status: 'running', fixture: 'synthetic technical scenarios; not real creative evaluation', listening: 'unverified' };

// 1. Legacy local-edit.v1 project: unchanged v1 operations and CLI form.
const clip = (id, start, caption) => ({ id, asset_id: 'source', in_seconds: start, frames: 24, volume: 0.7,
  fit: 'contain', captions: [{ from: start, to: start + 1, text: caption }] });
const root = path.join(base, 'project');
await createProject(root, { project_id: 'production-smoke', title: 'Creative Craft 技术样例', canvas: { width: 1280, height: 720, fps: 24 },
  assets: [{ id: 'source', path: source }], clips: [clip('opening', 0, '口播：保留这一句'), clip('detail', 3, '产品：细节画面')], audio: [] }, { legacyV1: true });
const outcomes = [];
outcomes.push(await renderProject(root, path.join(base, 'talking-head-preview'), { preview: true, revision: 1 }));
await editProject(root, 1, [{ type: 'reorder', clip_ids: ['detail', 'opening'] },
  { type: 'update_clip', clip_id: 'detail', changes: { captions: [{ from: 3, to: 4, text: '品牌：让细节先说话' }] } }]);
outcomes.push(await renderProject(root, path.join(base, 'brand-export'), { revision: 2 }));
await editProject(root, 2, [{ type: 'update_clip', clip_id: 'detail', changes: { in_seconds: 4, frames: 12,
  captions: [{ from: 4, to: 4.5, text: '电商：换一个开场' }] } }]);
outcomes.push(await renderProject(root, path.join(base, 'commerce-export'), { revision: 3 }));
if ((await readProject(root)).revision !== 3 || before !== await digest(source)) throw new Error('Reopen or input preservation failed');
await verifySmoke(base);
await fs.writeFile(path.join(base, 'mute.json'), JSON.stringify([{ type: 'update_clip', clip_id: 'opening', changes: { volume: 0 } },
  { type: 'update_clip', clip_id: 'detail', changes: { volume: 0 } }]));
const cli = async (...args) => JSON.parse((await run(process.execPath, [path.join(here, 'cli.mjs'), ...args], { timeout: 300000, maxBuffer: 8 * 1024 * 1024 })).stdout);
assert.equal((await cli('edit', root, '3', path.join(base, 'mute.json'))).revision, 4, 'legacy CLI edit form');
const silent = await cli('render', root, path.join(base, 'silent-export'), '4'); // Also protects stdout from upstream diagnostics.
if (silent.status !== 'completed' || silent.output.audio) throw new Error('Silent CLI export failed');
await editProject(root, 4, [{ type: 'set_audio', audio: [{ id: 'music', asset_id: 'source', in_seconds: 3,
  start_frame: 12, frames: 24, volume: 0.2 }] }]);
const bed = await renderProject(root, path.join(base, 'independent-audio-export'), { revision: 5 });
const rms = pcm => {
  if (pcm.length < 1000) throw new Error('Missing audio samples');
  let power = 0; for (let i = 0; i < pcm.length; i += 4) power += pcm.readFloatLE(i) ** 2;
  return Math.sqrt(power / (pcm.length / 4));
};
const bedFile = path.join(base, 'independent-audio-export/video.mp4');
const beforeBed = rms(await pcmAt(bedFile, 0.125)), duringBed = rms(await pcmAt(bedFile, 0.75));
if (beforeBed > 0.001 || duringBed < 0.005) throw new Error('Independent audio placement failed');
summary.legacy_v1 = { outputs: [...outcomes, silent, bed].map(r => r.status), independent_audio: { before_rms: beforeBed, during_rms: duringBed } };

// 2. First v2 batch on the v1 project: pure migration revision, then the edit.
const migrated = await editBatch(root, { base_revision: 5, author: 'agent', summary: 'Rename main track', operations: [
  { type: 'edit_track', track_id: 'v_main', name: '主轨' }] });
assert.equal(migrated.migration_revision, 6);
assert.equal((await readProject(root, 6)).change.author, 'migration');
assert.equal((await readProject(root, 5)).schema_version, 'creative-craft.local-edit.v1', 'old v1 revision stays readable');
const migratedRender = await renderProject(root, path.join(base, 'migrated-export'), { revision: 6 });
const migration = [];
for (const time of [0.25, 0.75, 1.25]) {
  const a = await frameAt(bedFile, time, 'scale=64:36'), b = await frameAt(path.join(base, 'migrated-export/video.mp4'), time, 'scale=64:36');
  const pa = rms(await pcmAt(bedFile, time)), pb = rms(await pcmAt(path.join(base, 'migrated-export/video.mp4'), time));
  migration.push({ time, picture_mae: mae(a, b), rms_v1: pa, rms_v2: pb });
  if (mae(a, b) > 6 || Math.abs(pa - pb) > 0.01) throw new Error(`Migration changed the render at ${time}s`);
}
summary.migration = { revisions: [6, 7], render: migratedRender.status, comparison: migration };

// 3. Native v2 project: multi-track B-roll, music bed, linked and free captions.
const v2 = path.join(base, 'multitrack');
const created = await createProject(v2, { project_id: 'multitrack-smoke', title: '多轨技术样例', canvas: { width: 1280, height: 720, fps: 24 },
  assets: [{ id: 'talk', path: source }, { id: 'music', path: music }],
  tracks: [{ id: 'v_main', kind: 'video', locked: false, name: '主轨' }, { id: 'a_music', kind: 'audio', locked: false },
    { id: 'c_sub', kind: 'caption', locked: false }],
  items: [
    { id: 'talk1', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 0, frames: 48, source_in_seconds: 0, volume: 0.8, fit: 'cover' },
    { id: 'talk2', track_id: 'v_main', kind: 'media', asset_id: 'talk', start_frame: 48, frames: 48, source_in_seconds: 3, volume: 0.8, fit: 'cover' },
    { id: 'bed', track_id: 'a_music', kind: 'media', asset_id: 'music', start_frame: 0, frames: 96, source_in_seconds: 0, volume: 0.6 },
    { id: 'cap1', track_id: 'c_sub', kind: 'caption', text: '口播：第一句', link: { item_id: 'talk1', source_from: 0.2, source_to: 1.5 } },
    { id: 'cap2', track_id: 'c_sub', kind: 'caption', text: '口播：第二句', link: { item_id: 'talk2', source_from: 3.2, source_to: 4.2 } },
    { id: 'title', track_id: 'c_sub', kind: 'caption', text: '标题：多轨合成', start_frame: 72, frames: 24 }] });
assert.equal(created.schema_version, 'creative-craft.edit-document.v2');
const assetCount = async () => (await fs.readdir(path.join(v2, 'assets'))).length;
const revisionCount = async () => (await fs.readdir(path.join(v2, 'revisions'))).filter(n => n.endsWith('.json')).length;
const addBroll = { base_revision: 1, author: 'agent', summary: 'Add generated-style B-roll above the main track', operations: [
  { type: 'add_asset', id: 'broll', path: broll, origin: { kind: 'import', label: 'synthetic bars' } },
  { type: 'add_track', track: { id: 'v_broll', kind: 'video', locked: false, name: 'B-roll' }, index: 1 },
  { type: 'add_item', item: { id: 'over', track_id: 'v_broll', kind: 'media', asset_id: 'broll', start_frame: 12, frames: 24,
    source_in_seconds: 0, volume: 0, fit: 'contain', transform: { x: 0.75, y: 0.25, scale: 0.4 } } }] };
await fs.writeFile(path.join(base, 'add-broll.json'), JSON.stringify(addBroll));
const assetsBefore = await assetCount();
const dry = await cli('edit', v2, path.join(base, 'add-broll.json'), '--dry-run');
assert.equal(dry.status, 'dry_run');
assert.deepEqual(dry.diff.items.added, ['over']);
assert.equal(await revisionCount(), 1, 'dry-run must not publish');
assert.equal(await assetCount(), assetsBefore, 'dry-run must not copy assets');
assert.equal((await cli('edit', v2, path.join(base, 'add-broll.json'))).revision, 2);
assert.equal(await assetCount(), assetsBefore + 1, 'add_asset imports after create');
await assert.rejects(editBatch(v2, { ...addBroll, summary: 'stale' }), /Revision conflict/);
await editBatch(v2, { base_revision: 2, author: 'human', summary: 'Lock picture', operations: [{ type: 'edit_track', track_id: 'v_main', locked: true }] });
await assert.rejects(editBatch(v2, { base_revision: 3, author: 'agent', summary: 'Trim locked', operations: [{ type: 'trim_item', item_id: 'talk1', tail_frames: 6 }] }), /locked/);
assert.equal(await revisionCount(), 3, 'locked edit must not publish');
await editBatch(v2, { base_revision: 3, author: 'agent', summary: 'Unlock and split', operations: [{ type: 'edit_track', track_id: 'v_main', locked: false },
  { type: 'split_item', item_id: 'talk2', at_frame: 72, new_item_id: 'talk2b' }] });
await editBatch(v2, { base_revision: 4, author: 'agent', summary: 'Back to the B-roll cut', operations: [{ type: 'revert_to', revision: 2 }] });
const reverted = await readProject(v2), target = await readProject(v2, 2);
assert.deepEqual([reverted.items, reverted.tracks], [target.items, target.tracks]);
const multi = await renderProject(v2, path.join(base, 'multitrack-export'), { revision: 5 });
const multitrackSignals = await verifyMultitrack(base, 'multitrack-export');
summary.multitrack = { revisions: await revisionCount(), render: multi.status, lint: multi.lint, signals: multitrackSignals };

// 4. QA on the actual export, schema-validated; then a deliberately failing export.
const qa = await cli('qa', v2, path.join(base, 'multitrack-export'), path.join(base, 'multitrack-qa'));
assert.notEqual(qa.verdict, 'fail', JSON.stringify(qa.checks.filter(c => c.status === 'fail')));
for (const [id, status] of [['duration-matches-revision', 'pass'], ['resolution', 'pass'], ['audio-stream', 'pass'], ['caption-sampled', 'pass']]) {
  assert.equal(qa.checks.find(c => c.id === id).status, status, id);
}
assert.ok(qa.samples.length >= 8 && qa.boundary_clips.length >= 2 && qa.contact_sheet, 'QA evidence');
const tampered = path.join(base, 'tampered-export');
await fs.cp(path.join(base, 'multitrack-export'), tampered, { recursive: true });
// Fault injection: an exporter that drops audio yet claims completion.
await fs.rename(path.join(tampered, 'video.mp4'), path.join(tampered, 'with-audio.mp4'));
await run(ffmpeg, ['-v', 'error', '-i', path.join(tampered, 'with-audio.mp4'), '-c', 'copy', '-an', path.join(tampered, 'video.mp4')]);
await fs.unlink(path.join(tampered, 'with-audio.mp4'));
const receipt = JSON.parse(await fs.readFile(path.join(tampered, 'receipt.json'), 'utf8'));
receipt.output = { ...receipt.output, sha256: await digest(path.join(tampered, 'video.mp4')), audio: false };
await fs.writeFile(path.join(tampered, 'receipt.json'), JSON.stringify(receipt, null, 2));
const bad = await cli('qa', v2, tampered, path.join(base, 'tampered-qa'));
assert.equal(bad.verdict, 'fail');
assert.equal(bad.checks.find(c => c.id === 'audio-stream').status, 'fail');
const revisionFiles = (await fs.readdir(path.join(v2, 'revisions'))).filter(n => n.endsWith('.json')).map(n => path.join(v2, 'revisions', n));
revisionFiles.push(...[6, 7].map(n => path.join(root, 'revisions', `00000${n}.json`)));
await validateSchema('edit-document-v2.schema.json', revisionFiles);
await validateSchema('render-qa.schema.json', [path.join(base, 'multitrack-qa/qa.json'), path.join(base, 'tampered-qa/qa.json')]);
summary.qa = { verdict: qa.verdict, checks: Object.fromEntries(qa.checks.map(c => [c.id, c.status])), samples: qa.samples.length,
  boundary_clips: qa.boundary_clips.length, schema: 'passed', fault_injection: { verdict: bad.verdict, audio_stream: 'fail' } };
summary.input_preserved = before === await digest(source);
summary.status = 'passed';
await fs.writeFile(path.join(base, 'summary.json'), JSON.stringify(summary, null, 2));
console.log(`SMOKE_ARTIFACTS=${base}`);
