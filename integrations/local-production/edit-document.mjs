import { validateCaptionFont } from './caption-font.mjs';
import { outputFrames } from './timeline.mjs';

export const SCHEMA_V1 = 'creative-craft.local-edit.v1';
export const SCHEMA_V2 = 'creative-craft.edit-document.v2';
export const fail = (message) => { throw new Error(message); };
export const integer = (v, min, max) => Number.isInteger(v) && v >= min && v <= max;
export const number = (v, min, max) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
export const id = (v) => typeof v === 'string' && /^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(v);
export const text = (v) => typeof v === 'string' && v.length > 0 && v.length <= 2000;
export const hex64 = (v) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export function keys(value, allowed) {
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

export function validateCanvas(canvas) {
  keys(canvas, ['width', 'height', 'fps']);
  const { width, height, fps } = canvas;
  if (![24, 30, 60].includes(fps) || !integer(width, 64, 3840) || !integer(height, 64, 3840) || width % 2 || height % 2) fail('Invalid canvas');
}

export function validateOrigin(origin) {
  keys(origin, ['kind', 'label', 'provenance_ref']);
  if (!['import', 'generated', 'render'].includes(origin.kind) || ('label' in origin && !text(origin.label)) ||
      ('provenance_ref' in origin && !text(origin.provenance_ref))) fail('Invalid asset origin');
}

const MEDIA_KEYS = ['id', 'track_id', 'kind', 'asset_id', 'start_frame', 'frames', 'source_in_seconds', 'volume'];
const VISUAL_KEYS = ['fit', 'opacity', 'transform'];
const CAPTION_KEYS = ['id', 'track_id', 'kind', 'text', 'style', 'link', 'start_frame', 'frames'];

// Semantic validation of creative-craft.edit-document.v2. JSON Schema covers
// shape; these rules cover kinds, references, ranges, overlap and output length.
export function validateV2(doc) {
  keys(doc, ['schema_version', 'project_id', 'revision', 'parent_sha256', 'title', 'canvas', 'caption_font', 'assets', 'tracks', 'items', 'change']);
  if (doc.schema_version !== SCHEMA_V2 || !id(doc.project_id) || !text(doc.title) || !integer(doc.revision, 1, 999999)) fail('Invalid project identity');
  if (doc.revision === 1 ? doc.parent_sha256 !== null : !hex64(doc.parent_sha256)) fail('Invalid parent digest');
  if ('caption_font' in doc) validateCaptionFont(doc.caption_font);
  validateCanvas(doc.canvas);
  const { fps } = doc.canvas, limit = 600 * fps;
  keys(doc.change, ['author', 'summary', 'operations_sha256']);
  if (!['agent', 'human', 'system', 'migration'].includes(doc.change.author) || !text(doc.change.summary) ||
      ('operations_sha256' in doc.change && doc.change.operations_sha256 !== null && !hex64(doc.change.operations_sha256))) fail('Invalid change record');
  if (!Array.isArray(doc.assets) || !doc.assets.length || doc.assets.length > 200 ||
      !Array.isArray(doc.tracks) || !doc.tracks.length || doc.tracks.length > 32 ||
      !Array.isArray(doc.items) || doc.items.length > 2000) fail('Invalid project collections');
  const assets = new Map();
  for (const asset of doc.assets) {
    keys(asset, ['id', 'file', 'sha256', 'duration', 'video', 'audio', 'width', 'height', 'origin']);
    if (!id(asset.id) || assets.has(asset.id) || !hex64(asset.sha256) ||
        asset.file !== `assets/${asset.sha256}.media` || !number(asset.duration, 0.001, 1800) ||
        typeof asset.video !== 'boolean' || typeof asset.audio !== 'boolean' ||
        !integer(asset.width, 0, 32768) || !integer(asset.height, 0, 32768)) fail('Invalid asset');
    validateOrigin(asset.origin);
    assets.set(asset.id, asset);
  }
  const tracks = new Map();
  for (const track of doc.tracks) {
    keys(track, ['id', 'kind', 'locked', 'name']);
    if (!id(track.id) || tracks.has(track.id) || !['video', 'audio', 'caption'].includes(track.kind) ||
        typeof track.locked !== 'boolean' || ('name' in track && !text(track.name))) fail('Invalid track');
    tracks.set(track.id, track);
  }
  const items = new Map();
  for (const item of doc.items) {
    if (!item || typeof item !== 'object' || !id(item.id)) fail('Invalid item');
    if (items.has(item.id)) fail(`Duplicate item id: ${item.id}`);
    items.set(item.id, item);
    const track = tracks.get(item.track_id) ?? fail(`Unknown track: ${item.track_id}`);
    if (item.kind === 'media') {
      if (track.kind === 'caption') fail(`Media item ${item.id} cannot be on a caption track`);
      keys(item, track.kind === 'video' ? [...MEDIA_KEYS, ...VISUAL_KEYS] : MEDIA_KEYS);
      const asset = assets.get(item.asset_id) ?? fail(`Unknown asset: ${item.asset_id}`);
      if (track.kind === 'video' ? !asset.video : !asset.audio) fail(`Asset ${asset.id} has no ${track.kind} for track ${track.id}`);
      if (!integer(item.start_frame, 0, limit) || !integer(item.frames, 1, limit) || !number(item.source_in_seconds, 0, 1800) ||
          !number(item.volume, 0, 1)) fail(`Media item ${item.id} requires asset_id/start_frame/frames/source_in_seconds/volume`);
      if (item.source_in_seconds + item.frames / fps > asset.duration + 0.001) fail(`Source range exceeds asset: ${item.id}`);
      if (('fit' in item && !['contain', 'cover'].includes(item.fit)) || ('opacity' in item && !number(item.opacity, 0, 1))) fail(`Invalid visual properties: ${item.id}`);
      if ('transform' in item) {
        keys(item.transform, ['x', 'y', 'scale']);
        if (!number(item.transform.x, 0, 1) || !number(item.transform.y, 0, 1) || !number(item.transform.scale, .05, 1)) fail(`Invalid transform: ${item.id}`);
      }
    } else if (item.kind === 'caption') {
      if (track.kind !== 'caption') fail(`Caption item ${item.id} must be on a caption track`);
      keys(item, CAPTION_KEYS);
      if (!text(item.text)) fail(`Invalid caption text: ${item.id}`);
      if ('style' in item) validateCaptionStyle(item.style);
      if ('link' in item) {
        keys(item.link, ['item_id', 'source_from', 'source_to']);
        if ('start_frame' in item || 'frames' in item) fail(`Linked caption ${item.id} must not store output time`);
        if (!number(item.link.source_from, 0, 1800) || !number(item.link.source_to, 0, 1800) ||
            item.link.source_to <= item.link.source_from) fail(`Invalid caption link range: ${item.id}`);
      } else if (!integer(item.start_frame, 0, limit) || !integer(item.frames, 1, limit)) fail(`Free caption ${item.id} requires start_frame/frames`);
    } else fail(`Invalid item kind: ${item.id}`);
  }
  for (const item of doc.items) {
    if (item.kind !== 'caption' || !item.link) continue;
    const media = items.get(item.link.item_id);
    if (media?.kind !== 'media') fail(`Caption ${item.id} links to unknown media item: ${item.link.item_id}`);
    if (item.link.source_to > assets.get(media.asset_id).duration + 0.001) fail(`Caption link exceeds asset: ${item.id}`);
  }
  for (const track of doc.tracks) {
    const spans = doc.items.filter(i => i.track_id === track.id && i.kind === 'media').sort((a, b) => a.start_frame - b.start_frame);
    for (let i = 1; i < spans.length; i++) {
      if (spans[i].start_frame < spans[i - 1].start_frame + spans[i - 1].frames) fail(`Overlapping media items on track ${track.id}: ${spans[i - 1].id}, ${spans[i].id}`);
    }
  }
  const frames = outputFrames(doc);
  if (frames < 1) fail('Empty timeline');
  if (frames > limit) fail('Output exceeds 10 minutes');
  return { frames, duration: frames / fps };
}

// In-memory v1 -> v2 conversion. Rendering is preserved: clips become sequential
// v_main items, clip captions become linked captions on c_main, and audio beds
// go to a_bed (overflow lanes a_bed_2… when v1 beds overlapped). v1 truncated beds
// at the last clip; that truncation is made explicit and fully hidden beds are
// dropped because v2 would otherwise extend the output.
export function migrateV1(v1) {
  const fps = v1.canvas.fps;
  const used = new Set([...v1.clips.map(c => c.id), ...v1.audio.map(a => a.id)]);
  let counter = 0;
  const captionId = () => { let key; do key = `cap${++counter}`; while (used.has(key)); used.add(key); return key; };
  const items = [], captions = [];
  let cursor = 0;
  for (const clip of v1.clips) {
    items.push({ id: clip.id, track_id: 'v_main', kind: 'media', asset_id: clip.asset_id, start_frame: cursor, frames: clip.frames,
      source_in_seconds: clip.in_seconds, volume: clip.volume, fit: clip.fit });
    for (const caption of clip.captions) {
      captions.push({ id: captionId(), track_id: 'c_main', kind: 'caption', text: caption.text, ...(caption.style ? { style: caption.style } : {}),
        link: { item_id: clip.id, source_from: caption.from, source_to: caption.to } });
    }
    cursor += clip.frames;
  }
  const lanes = [];
  for (const bed of v1.audio) {
    const frames = Math.min(bed.frames, cursor - bed.start_frame);
    if (frames <= 0) continue;
    let lane = lanes.findIndex(end => end <= bed.start_frame);
    if (lane < 0) { lane = lanes.length; lanes.push(0); }
    lanes[lane] = bed.start_frame + frames;
    items.push({ id: bed.id, track_id: lane ? `a_bed_${lane + 1}` : 'a_bed', kind: 'media', asset_id: bed.asset_id,
      start_frame: bed.start_frame, frames, source_in_seconds: bed.in_seconds, volume: bed.volume });
  }
  const tracks = [{ id: 'v_main', kind: 'video', locked: false, name: 'Main' },
    ...(lanes.length ? lanes : [0]).map((_, i) => ({ id: i ? `a_bed_${i + 1}` : 'a_bed', kind: 'audio', locked: false, name: 'Audio bed' })),
    { id: 'c_main', kind: 'caption', locked: false, name: 'Captions' }];
  return { schema_version: SCHEMA_V2, project_id: v1.project_id, revision: v1.revision, parent_sha256: v1.parent_sha256, title: v1.title,
    canvas: { ...v1.canvas }, ...(v1.caption_font ? { caption_font: { ...v1.caption_font } } : {}),
    assets: v1.assets.map(a => ({ ...a, origin: { kind: 'import' } })), tracks, items: [...items, ...captions],
    change: { author: 'migration', summary: `Migrated from ${SCHEMA_V1} revision ${v1.revision}`, operations_sha256: null } };
}
