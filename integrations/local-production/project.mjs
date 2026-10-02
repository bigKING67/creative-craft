import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { bindCaptionFont, installCaptionFont, planCaptionFont, validateCaptionFont, verifyCaptionFont, activeCaptions } from './caption-font.mjs';
import { SCHEMA_V1, SCHEMA_V2, fail, id, integer, keys, number, text, validateCanvas, validateCaptionStyle, validateAssetFields, validateNewAssetOrigin,
  validateV2, migrateV1 } from './edit-document.mjs';
import { applyOperations, diffDocuments, operationsSha256 } from './operations.mjs';
import { checkVolumeAutomation } from './timeline.mjs';

export const run = promisify(execFile);
export const SCHEMA = SCHEMA_V1;
export { SCHEMA_V2, validateV2, validateCaptionStyle, migrateV1 };
const sha256 = value => createHash('sha256').update(value).digest('hex');
const serialize = doc => `${JSON.stringify(doc, null, 2)}\n`;

export async function digest(file) {
  const hash = createHash('sha256');
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest('hex');
}

// This is a local single-user tool, not a filesystem sandbox for hostile users.
export async function safePath(value) {
  const absolute = path.resolve(value);
  let cursor = path.parse(absolute).root;
  for (const part of absolute.slice(cursor.length).split(path.sep).filter(Boolean)) {
    cursor = path.join(cursor, part);
    const stat = await fs.lstat(cursor).catch(e => { if (e.code !== 'ENOENT') throw e; });
    if (stat?.isSymbolicLink()) fail(`Symlink not allowed: ${cursor}`);
  }
  return absolute;
}

// Single ffprobe invocation shared by import probing and render QA.
export async function ffprobeJson(file) {
  const { stdout } = await run(process.env.CREATIVE_FFPROBE || 'ffprobe',
    ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file],
    { timeout: 30000, maxBuffer: 4 * 1024 * 1024 });
  return JSON.parse(stdout);
}

export async function probe(file) {
  const result = await ffprobeJson(file);
  const video = result.streams.find(s => s.codec_type === 'video');
  const audio = result.streams.find(s => s.codec_type === 'audio');
  const duration = Number(result.format.duration);
  if (!number(duration, 0.001, 1800)) fail('Media duration must be 0–1800 seconds');
  return { duration, video: Boolean(video), audio: Boolean(audio),
    width: video?.width ?? 0, height: video?.height ?? 0 };
}

export function validate(project) {
  keys(project, ['schema_version', 'project_id', 'revision', 'parent_sha256', 'title', 'canvas', 'assets', 'clips', 'audio', 'caption_font']);
  if ('caption_font' in project) validateCaptionFont(project.caption_font);
  if (project.schema_version !== SCHEMA || !id(project.project_id) || !text(project.title) ||
      !integer(project.revision, 1, 999999)) fail('Invalid project identity');
  if (project.revision === 1 ? project.parent_sha256 !== null :
      typeof project.parent_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(project.parent_sha256)) fail('Invalid parent digest');
  validateCanvas(project.canvas);
  const { fps } = project.canvas;
  if (!Array.isArray(project.assets) || !project.assets.length || project.assets.length > 100 ||
      !Array.isArray(project.clips) || !project.clips.length || project.clips.length > 500 ||
      !Array.isArray(project.audio) || project.audio.length > 32) fail('Invalid project collections');
  const assets = new Map();
  for (const asset of project.assets) {
    validateAssetFields(asset);
    if (assets.has(asset.id)) fail('Invalid asset');
    assets.set(asset.id, asset);
  }
  const ids = new Set();
  let frames = 0;
  for (const clip of project.clips) {
    keys(clip, ['id', 'asset_id', 'in_seconds', 'frames', 'volume', 'fit', 'captions']);
    const asset = assets.get(clip.asset_id);
    if (!id(clip.id) || ids.has(clip.id) || !asset?.video || !number(clip.in_seconds, 0, 1800) ||
        !integer(clip.frames, 1, 600 * fps) || clip.in_seconds + clip.frames / fps > asset.duration + 0.001 ||
        !number(clip.volume, 0, 1) || !['contain', 'cover'].includes(clip.fit) || !Array.isArray(clip.captions) || clip.captions.length > 500) fail('Invalid clip or source range');
    ids.add(clip.id);
    for (const caption of clip.captions) {
      keys(caption, ['from', 'to', 'text', 'style']);
      if ('style' in caption) validateCaptionStyle(caption.style);
      if (!number(caption.from, 0, asset.duration) || !number(caption.to, 0, asset.duration) ||
          caption.to <= caption.from || !text(caption.text)) fail('Invalid source-timed caption');
    }
    frames += clip.frames;
  }
  if (frames > 600 * fps) fail('Output exceeds 10 minutes');
  for (const track of project.audio) {
    keys(track, ['id', 'asset_id', 'in_seconds', 'start_frame', 'frames', 'volume']);
    const asset = assets.get(track.asset_id);
    if (!id(track.id) || ids.has(track.id) || !asset?.audio || !number(track.in_seconds, 0, 1800) ||
        !integer(track.start_frame, 0, 600 * fps) || !integer(track.frames, 1, 600 * fps) ||
        track.in_seconds + track.frames / fps > asset.duration + 0.001 || !number(track.volume, 0, 1)) fail('Invalid audio range');
    ids.add(track.id);
  }
  return { frames, duration: frames / fps };
}

// Either document generation; v1 revisions stay readable and renderable.
export const validateDocument = doc => doc?.schema_version === SCHEMA_V2 ? validateV2(doc) : validate(doc);

const revisionName = (revision) => `${String(revision).padStart(6, '0')}.json`;
export async function readProject(root, revision) {
  root = await safePath(root);
  const revisions = await safePath(path.join(root, 'revisions'));
  const names = (await fs.readdir(revisions)).filter(n => /^\d{6}\.json$/.test(n)).sort();
  if (!names.length) fail('No project revisions');
  const name = revision === undefined ? names.at(-1) : revisionName(revision);
  if (!names.includes(name)) fail('Revision not found');
  const file = await safePath(path.join(revisions, name));
  const project = JSON.parse(await fs.readFile(file, 'utf8'));
  validateDocument(project);
  if (revisionName(project.revision) !== name) fail('Revision filename mismatch');
  if (project.revision > 1) {
    const previous = await safePath(path.join(revisions, revisionName(project.revision - 1)));
    if (await digest(previous) !== project.parent_sha256) fail('Parent revision changed');
  }
  return project;
}

async function publish(root, project) {
  const dir = await safePath(path.join(root, 'revisions'));
  const temp = path.join(dir, `.pending-${randomUUID()}`);
  await fs.writeFile(temp, serialize(project), { flag: 'wx' });
  try {
    // Atomic, no-replace publication. Two writers cannot publish the same revision.
    await fs.link(temp, path.join(dir, revisionName(project.revision)));
  } catch (error) {
    if (error.code === 'EEXIST') fail('Revision conflict; read the latest project');
    throw error;
  } finally { await fs.unlink(temp); }
}

async function importAsset(file) {
  if (typeof file !== 'string') fail('Invalid import');
  const source = await safePath(file);
  if (!(await fs.stat(source)).isFile()) fail('Source must be a file');
  const sha256 = await digest(source);
  return { source, asset: { file: `assets/${sha256}.media`, sha256, ...await probe(source) } };
}

// Content-addressed copies; an existing identical file is reused, never replaced.
async function copyImports(root, imports) {
  for (const { source, asset } of imports) {
    const target = path.join(root, asset.file);
    try { await fs.copyFile(source, target, 1); }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
    if (await digest(target) !== asset.sha256) fail('Source changed during import');
  }
}

// The spec format selects the project format, so existing hosts keep working:
// a v1 spec (clips/audio) creates a local-edit.v1 project that still accepts the
// v1 CLI and operations, and migrates on its first v2 edit batch; a v2 spec
// (tracks/items) creates an edit-document.v2 project.
export async function createProject(root, spec) {
  const v1 = spec && typeof spec === 'object' && 'clips' in spec;
  keys(spec, v1 ? ['project_id', 'title', 'canvas', 'assets', 'clips', 'audio'] : ['project_id', 'title', 'canvas', 'assets', 'tracks', 'items']);
  if (!Array.isArray(spec.assets) || !spec.assets.length || spec.assets.length > (v1 ? 100 : 200)) fail('Invalid assets');
  const imports = [];
  for (const item of spec.assets) {
    keys(item, v1 ? ['id', 'path'] : ['id', 'path', 'origin']);
    if (!id(item.id)) fail('Invalid import');
    const origin = item.origin ?? { kind: 'import' };
    if (!v1) validateNewAssetOrigin(origin);
    const imported = await importAsset(item.path);
    imported.asset = { id: item.id, ...imported.asset, ...(v1 ? {} : { origin }) };
    imports.push(imported);
  }
  let project;
  if (v1) {
    project = { schema_version: SCHEMA, project_id: spec.project_id, revision: 1, parent_sha256: null,
      title: spec.title, canvas: spec.canvas, assets: imports.map(i => i.asset), clips: spec.clips, audio: spec.audio ?? [] };
    validate(project);
  } else {
    project = { schema_version: SCHEMA_V2, project_id: spec.project_id, revision: 1, parent_sha256: null, title: spec.title,
      canvas: spec.canvas, assets: imports.map(i => i.asset), tracks: spec.tracks, items: spec.items,
      change: { author: 'system', summary: 'Created project', operations_sha256: null } };
  }
  validateDocument(project);
  if (!v1) checkVolumeAutomation(project); // Compile limits fail here, not at render.
  root = await safePath(root);
  await fs.mkdir(root); // Existing projects are never replaced.
  await fs.mkdir(path.join(root, 'assets'));
  await fs.mkdir(path.join(root, 'revisions'));
  await copyImports(root, imports);
  await bindCaptionFont(root, project);
  await publish(root, project);
  return project;
}

export async function editProject(root, expectedRevision, operations) {
  const project = await readProject(root);
  if (project.schema_version !== SCHEMA) fail('This project is edit-document.v2; v1 operations are not supported. Submit an edit batch (edit PROJECT BATCH.json)');
  if (project.revision !== expectedRevision) fail('Revision conflict; read the latest project');
  if (!Array.isArray(operations) || !operations.length || operations.length > 100) fail('Invalid operations');
  const next = structuredClone(project);
  for (const op of operations) {
    if (op.type === 'reorder') {
      keys(op, ['type', 'clip_ids']);
      if (!Array.isArray(op.clip_ids) || op.clip_ids.length !== next.clips.length || new Set(op.clip_ids).size !== next.clips.length) fail('Reorder must name every clip once');
      next.clips = op.clip_ids.map(key => next.clips.find(c => c.id === key) ?? fail('Unknown clip'));
    } else if (op.type === 'update_clip') {
      keys(op, ['type', 'clip_id', 'changes']);
      keys(op.changes, ['in_seconds', 'frames', 'volume', 'fit', 'captions', 'asset_id']);
      const clip = next.clips.find(c => c.id === op.clip_id) ?? fail('Unknown clip');
      if (op.changes.asset_id && op.changes.asset_id !== clip.asset_id && !('captions' in op.changes)) clip.captions = [];
      Object.assign(clip, op.changes);
    } else if (op.type === 'replace_clips') {
      keys(op, ['type', 'clips']);
      next.clips = op.clips;
    } else if (op.type === 'set_audio') {
      keys(op, ['type', 'audio']);
      next.audio = op.audio;
    } else fail('Unknown edit operation');
  }
  next.revision += 1;
  next.parent_sha256 = await digest(await safePath(path.join(root, 'revisions', revisionName(project.revision))));
  validate(next);
  await publish(root, next);
  return next;
}

const asV2 = doc => doc.schema_version === SCHEMA_V2 ? structuredClone(doc) : migrateV1(doc);

// Whole-document restore as a new revision. Locked tracks protect their items:
// a revert that would change any item on a currently locked track is refused.
async function revertContent(root, base, op) {
  keys(op, ['type', 'revision']);
  if (!integer(op.revision, 1, base.revision - 1)) fail('revert_to requires an earlier revision');
  const target = asV2(await readProject(root, op.revision));
  for (const track of base.tracks.filter(t => t.locked)) {
    const on = doc => JSON.stringify(doc.items.filter(i => i.track_id === track.id));
    if (!target.tracks.some(t => t.id === track.id) || on(base) !== on(target)) fail(`Track is locked: ${track.id}`);
  }
  // Lock state is current editorial intent, not history: a revert never unlocks.
  const locked = new Set(base.tracks.filter(t => t.locked).map(t => t.id));
  const tracks = target.tracks.map(t => ({ ...t, locked: t.locked || locked.has(t.id) }));
  const next = { ...structuredClone(base), title: target.title, canvas: target.canvas, assets: target.assets, tracks, items: target.items };
  if (target.caption_font && !next.caption_font) next.caption_font = target.caption_font;
  return next;
}

// Edit batch v2: {base_revision, author, summary, operations[]}. All-or-nothing:
// every operation and the resulting document validate before anything is
// written. A v1 project first gets a pure migration revision (author
// "migration"), then the edit revision on top. dryRun returns the diff and
// writes nothing (add_asset only probes).
export async function editBatch(root, batch, { dryRun = false } = {}) {
  keys(batch, ['base_revision', 'author', 'summary', 'operations']);
  if (!integer(batch.base_revision, 1, 999999) || !['agent', 'human', 'system'].includes(batch.author) || !text(batch.summary) ||
      !Array.isArray(batch.operations) || !batch.operations.length || batch.operations.length > 100) fail('Invalid edit batch');
  root = await safePath(root);
  const latest = await readProject(root);
  if (latest.revision !== batch.base_revision) fail('Revision conflict; read the latest project');
  let base = latest, baseSha = await digest(await safePath(path.join(root, 'revisions', revisionName(latest.revision)))), migration = null;
  if (latest.schema_version === SCHEMA) {
    migration = { ...migrateV1(latest), revision: latest.revision + 1, parent_sha256: baseSha,
      change: { author: 'migration', summary: `Migrated ${SCHEMA} revision ${latest.revision} to ${SCHEMA_V2}`, operations_sha256: null } };
    validateV2(migration);
    base = migration;
    baseSha = sha256(serialize(migration));
  }
  // A lock change is its own revision, so unlock-then-edit cannot hide in one batch.
  if (batch.operations.length > 1 && batch.operations.some(op => op?.type === 'edit_track' && 'locked' in op)) {
    fail('Changing a track lock must be the only operation in its batch');
  }
  const imports = [];
  const next = batch.operations.some(op => op?.type === 'revert_to')
    ? (batch.operations.length === 1 ? await revertContent(root, base, batch.operations[0]) : fail('revert_to must be the only operation in its batch'))
    : await applyOperations(base, batch.operations, { importAsset, imports });
  const operations_sha256 = operationsSha256(batch.operations);
  Object.assign(next, { revision: base.revision + 1, parent_sha256: baseSha,
    change: { author: batch.author, summary: batch.summary, operations_sha256 } });
  validateV2(next);
  checkVolumeAutomation(next); // Same envelope code as compilation; refused before dry-run or publish.
  // Fixed caption font: bound when captions or graphics are introduced. Legacy projects that
  // already had captions without a binding keep the system-font contract.
  let installFont = false;
  if (next.caption_font) await verifyCaptionFont(root, next);
  else if (!activeCaptions(base).length) installFont = await planCaptionFont(next);
  else if (next.items.some(i => i.kind === 'graphic')) {
    // Graphics reuse the bound caption font; binding it now would silently restyle
    // this legacy project's system-font captions, so refuse instead.
    fail('Graphic items need the bound caption font; this legacy project renders captions with system fonts. Create a new project to add graphics');
  }
  const result = { status: dryRun ? 'dry_run' : 'published', base_revision: latest.revision, migration_revision: migration?.revision ?? null,
    revision: next.revision, operations_sha256, diff: diffDocuments(base, next) };
  if (dryRun) return result;
  await copyImports(root, imports);
  if (installFont) await installCaptionFont(root);
  if (migration) await publish(root, migration);
  await publish(root, next);
  return result;
}

export async function verifyAssets(root, project) {
  await verifyCaptionFont(root, project);
  for (const asset of project.assets) {
    const file = await safePath(path.join(root, asset.file));
    if (await digest(file) !== asset.sha256) fail(`Asset changed: ${asset.id}`);
  }
}
