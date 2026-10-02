// Pure EditDocument v2 timeline math shared by validation, font binding,
// composition and QA. No I/O and no imports, so every layer can depend on it.
export const isV2 = doc => Array.isArray(doc?.items);
export const round9 = value => Math.round(value * 1e9) / 1e9;
// P2 speed: output frames play `speed` seconds of source per output second.
export const speedOf = item => item.speed ?? 1;
export const sourceSeconds = (item, fps) => item.frames / fps * speedOf(item);

// Linked captions store source time only. Their output window is the
// intersection of the link range with the media item's current source window,
// mapped through the item's speed to its output position. Null when nothing is visible.
export function captionWindow(doc, caption, byId = new Map(doc.items.map(i => [i.id, i]))) {
  const fps = doc.canvas.fps;
  if (!caption.link) return { start: caption.start_frame / fps, end: (caption.start_frame + caption.frames) / fps };
  const media = byId.get(caption.link.item_id);
  if (!media || media.kind !== 'media') return null;
  const sourceIn = media.source_in_seconds, speed = speedOf(media);
  const from = Math.max(caption.link.source_from, sourceIn), to = Math.min(caption.link.source_to, sourceIn + sourceSeconds(media, fps));
  if (to <= from) return null;
  const output = source => media.start_frame / fps + (source - sourceIn) / speed;
  return { start: output(from), end: output(to) };
}

// Visible captions in document order with their resolved output seconds.
export function resolveCaptions(doc) {
  const byId = new Map(doc.items.map(i => [i.id, i]));
  return doc.items.filter(i => i.kind === 'caption').flatMap(item => {
    const window = captionWindow(doc, item, byId);
    return window ? [{ item, ...window }] : [];
  });
}

// Output length = furthest end of any media/graphic item or free (unlinked) caption.
export function outputFrames(doc) {
  return doc.items.reduce((max, i) => i.kind === 'media' || !i.link ? Math.max(max, i.start_frame + i.frames) : max, 0);
}

export const trackOf = (doc, item) => doc.tracks.find(t => t.id === item.track_id);

// Media that the renderer must emit as sound (video items with audio, audio items).
export function audibleItems(doc) {
  const assets = new Map(doc.assets.map(a => [a.id, a]));
  return doc.items.filter(i => i.kind === 'media' && i.volume > 0 && assets.get(i.asset_id)?.audio);
}

// ---- P2 envelopes: piecewise-linear curves over composition seconds. ----
// A curve is [[t, v], …] sorted by t and held constant outside its points.
const MIN_RAMP = 0.001; // A zero-frame attack/release still ramps over 1 ms (no click).
// Linear interpolation for non-decreasing t: the cursor only moves forward
// (amortised O(1) per sample).
function sampler(points) {
  let i = 1;
  return t => {
    if (t <= points[0][0]) return points[0][1];
    while (i < points.length && t > points[i][0]) i++;
    if (i === points.length) return points.at(-1)[1];
    const [t0, v0] = points[i - 1], [t1, v1] = points[i];
    return t1 === t0 ? v1 : v0 + (v1 - v0) * (t - t0) / (t1 - t0);
  };
}
// The part of a curve that decides its value over [s, e]: inner points plus one
// neighbour on each side (binary search, so a long curve costs O(log n) per item).
function curveWindow(points, s, e) {
  const first = t => {
    let lo = 0, hi = points.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (points[mid][0] < t) lo = mid + 1; else hi = mid; }
    return lo;
  };
  let to = first(e);
  while (to < points.length && points[to][0] === e) to++; // keep points exactly at e
  return points.slice(Math.max(0, first(s) - 1), to + 1);
}

// Output intervals (seconds) where the duck's reference track has sound:
// audible media (volume > 0, asset with audio). Intervals whose release and
// next attack would meet are merged, so the level stays down between them.
export function duckIntervals(doc, track, audible = audibleItems(doc)) {
  const fps = doc.canvas.fps, { under_track_id, attack_frames, release_frames } = track.duck;
  const spans = audible.filter(i => i.track_id === under_track_id)
    .map(i => [i.start_frame / fps, (i.start_frame + i.frames) / fps]).sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const [s, e] of spans) {
    const last = merged.at(-1);
    if (last && s - attack_frames / fps <= last[1] + release_frames / fps) last[1] = Math.max(last[1], e);
    else merged.push([s, e]);
  }
  return merged;
}

// Gain factor of a ducked track: 1 outside speech, 10^(depth_db/20) inside.
// The attack ramp ends at speech start (look-ahead: the timeline is known) and
// the release ramp starts at speech end.
export function duckCurve(doc, track, audible) {
  const fps = doc.canvas.fps, intervals = duckIntervals(doc, track, audible);
  if (!intervals.length) return null;
  const depth = 10 ** (track.duck.depth_db / 20);
  const attack = Math.max(MIN_RAMP, track.duck.attack_frames / fps), release = Math.max(MIN_RAMP, track.duck.release_frames / fps);
  return intervals.flatMap(([s, e]) => [[s - attack, 1], [s, depth], [e, depth], [e + release, 1]]);
}

// Lookup tables built once per document state and shared by every envelope of
// it: crossfade successor/predecessor (a map lookup instead of a scan per item)
// and one duck curve per ducked track (instead of one per item).
export function envelopeIndex(doc) {
  // A crossfading item o joins the same-track item that ends where o's overlap ends.
  const incoming = new Map();
  for (const o of doc.items) {
    if (!o.transition_in) continue;
    const key = `${o.track_id}\n${o.start_frame + o.transition_in.frames}`;
    if (!incoming.has(key)) incoming.set(key, []);
    incoming.get(key).push(o);
  }
  const successor = new Map(), predecessor = new Map();
  for (const item of doc.items) {
    const next = incoming.get(`${item.track_id}\n${item.start_frame + item.frames}`)?.find(o => o !== item);
    if (!next) continue;
    successor.set(item, next);
    if (!predecessor.has(next)) predecessor.set(next, item);
  }
  const audible = audibleItems(doc);
  const ducks = new Map(doc.tracks.filter(t => t.duck).map(t => [t.id, duckCurve(doc, t, audible)]));
  return { successor, predecessor, ducks };
}

// Next same-track item that crossfades in over this item's tail, if any.
export const crossfadeSuccessor = (doc, item, index = envelopeIndex(doc)) => index.successor.get(item);

// Level of one item over its own output window as [[t, v]] in composition
// seconds, or null when constant. 'audio': volume × fades × crossfade in/out ×
// duck. 'visual': opacity × fades × crossfade in; the outgoing picture stays
// opaque underneath, so the overlap mid-point is a true 50/50 mix. Factors are
// multiplied exactly at every breakpoint and interpolated linearly between.
// Callers computing many envelopes of one document pass one envelopeIndex(doc).
export function itemEnvelope(doc, item, kind, index = envelopeIndex(doc)) {
  const fps = doc.canvas.fps, s = item.start_frame / fps, e = (item.start_frame + item.frames) / fps;
  const factors = [];
  if (item.fade_in_frames) factors.push([[s, 0], [s + item.fade_in_frames / fps, 1]]);
  if (item.fade_out_frames) factors.push([[e - item.fade_out_frames / fps, 1], [e, 0]]);
  if (item.transition_in) factors.push([[s, 0], [s + item.transition_in.frames / fps, 1]]);
  if (kind === 'audio') {
    const next = index.successor.get(item);
    if (next) factors.push([[next.start_frame / fps, 1], [e, 0]]);
    const duck = index.ducks.get(item.track_id);
    if (duck) factors.push(curveWindow(duck, s, e));
  }
  if (!factors.length) return null;
  const base = kind === 'audio' ? item.volume : item.opacity ?? 1;
  const times = [...new Set([s, e, ...factors.flat().map(p => p[0])].filter(t => t >= s && t <= e))].sort((a, b) => a - b);
  const samplers = factors.map(sampler);
  return times.map(t => [t, Math.round(base * samplers.reduce((g, f) => g * f(t), 1) * 1e6) / 1e6]);
}

// HyperFrames accepts at most 512 points per automation lane.
export const MAX_VOLUME_POINTS = 512;
// Volume lane of one audible item (null when constant), refused when too long.
// Compilation and edit/create validation both go through here, so a lane that
// would fail to compile is rejected before a revision is published.
export function volumeEnvelope(doc, item, index = envelopeIndex(doc)) {
  const envelope = itemEnvelope(doc, item, 'audio', index);
  if (envelope && envelope.length > MAX_VOLUME_POINTS) {
    throw new Error(`Volume automation for item ${item.id} on track ${item.track_id} has ${envelope.length} points (max ${MAX_VOLUME_POINTS}); reduce ducking intervals, fades or crossfades`);
  }
  return envelope;
}
export function checkVolumeAutomation(doc) {
  const index = envelopeIndex(doc);
  for (const item of audibleItems(doc)) volumeEnvelope(doc, item, index);
}
