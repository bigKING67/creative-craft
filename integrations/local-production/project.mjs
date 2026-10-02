import { createHash, randomUUID } from 'node:crypto';
import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { bindCaptionFont, validateCaptionFont, verifyCaptionFont } from './caption-font.mjs';

export const run = promisify(execFile);
export const SCHEMA = 'creative-craft.local-edit.v1';
const fail = (message) => { throw new Error(message); };
const integer = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
const number = (v, min, max) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
const id = (v) => typeof v === 'string' && /^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(v);
const text = (v) => typeof v === 'string' && v.length > 0 && v.length <= 2000;
function keys(value, allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail('Expected object');
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`Unknown field: ${key}`);
}

// Source-matched caption geometry is data, never caller-supplied CSS.
export function validateCaptionStyle(style) {
  keys(style, ['fontHeight', 'centerY', 'color', 'strokeWidth', 'weight']);
  if (!number(style.fontHeight, .015, .08) || !number(style.centerY, .1, .9) ||
      !number(style.strokeWidth, 0, .004) || ![400, 600, 700, 900].includes(style.weight) ||
      typeof style.color !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(style.color)) fail('Invalid caption style');
}

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

export async function probe(file) {
  const { stdout } = await run(process.env.CREATIVE_FFPROBE || 'ffprobe',
    ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file],
    { timeout: 30000, maxBuffer: 4 * 1024 * 1024 });
  const result = JSON.parse(stdout);
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
  keys(project.canvas, ['width', 'height', 'fps']);
  const { width, height, fps } = project.canvas;
  if (![24, 30, 60].includes(fps) || !integer(width, 64, 3840) || !integer(height, 64, 3840) || width % 2 || height % 2) fail('Invalid canvas');
  if (!Array.isArray(project.assets) || !project.assets.length || project.assets.length > 100 ||
      !Array.isArray(project.clips) || !project.clips.length || project.clips.length > 500 ||
      !Array.isArray(project.audio) || project.audio.length > 32) fail('Invalid project collections');
  const assets = new Map();
  for (const asset of project.assets) {
    keys(asset, ['id', 'file', 'sha256', 'duration', 'video', 'audio', 'width', 'height']);
    if (!id(asset.id) || assets.has(asset.id) || !/^[a-f0-9]{64}$/.test(asset.sha256) ||
        asset.file !== `assets/${asset.sha256}.media` || !number(asset.duration, 0.001, 1800) ||
        typeof asset.video !== 'boolean' || typeof asset.audio !== 'boolean' ||
        !integer(asset.width, 0, 32768) || !integer(asset.height, 0, 32768)) fail('Invalid asset');
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
  validate(project);
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
  await fs.writeFile(temp, `${JSON.stringify(project, null, 2)}\n`, { flag: 'wx' });
  try {
    // Atomic, no-replace publication. Two writers cannot publish the same revision.
    await fs.link(temp, path.join(dir, revisionName(project.revision)));
  } catch (error) {
    if (error.code === 'EEXIST') fail('Revision conflict; read the latest project');
    throw error;
  } finally { await fs.unlink(temp); }
}

export async function createProject(root, spec) {
  keys(spec, ['project_id', 'title', 'canvas', 'assets', 'clips', 'audio']);
  if (!Array.isArray(spec.assets) || !spec.assets.length || spec.assets.length > 100) fail('Invalid assets');
  const imports = [];
  for (const item of spec.assets) {
    keys(item, ['id', 'path']);
    if (!id(item.id) || typeof item.path !== 'string') fail('Invalid import');
    const source = await safePath(item.path);
    if (!(await fs.stat(source)).isFile()) fail('Source must be a file');
    const sha256 = await digest(source);
    imports.push({ source, asset: { id: item.id, file: `assets/${sha256}.media`, sha256, ...await probe(source) } });
  }
  const project = { schema_version: SCHEMA, project_id: spec.project_id, revision: 1, parent_sha256: null,
    title: spec.title, canvas: spec.canvas, assets: imports.map(i => i.asset), clips: spec.clips, audio: spec.audio ?? [] };
  validate(project);
  root = await safePath(root);
  await fs.mkdir(root); // Existing projects are never replaced.
  await fs.mkdir(path.join(root, 'assets'));
  await fs.mkdir(path.join(root, 'revisions'));
  const copied = new Set();
  for (const { source, asset } of imports) {
    if (copied.has(asset.file)) continue;
    const target = path.join(root, asset.file);
    await fs.copyFile(source, target, 1);
    if (await digest(target) !== asset.sha256) fail('Source changed during import');
    copied.add(asset.file);
  }
  await bindCaptionFont(root, project);
  await publish(root, project);
  return project;
}

export async function editProject(root, expectedRevision, operations) {
  const project = await readProject(root);
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

export async function verifyAssets(root, project) {
  await verifyCaptionFont(root, project);
  for (const asset of project.assets) {
    const file = await safePath(path.join(root, asset.file));
    if (await digest(file) !== asset.sha256) fail(`Asset changed: ${asset.id}`);
  }
}
