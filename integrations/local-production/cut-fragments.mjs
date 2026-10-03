import path from 'node:path';
import { speedOf } from './timeline.mjs';
import { mapLimit } from './media-analysis.mjs';
import { CAPTION_CUT, TIME_EPS, containerStarts, cutPoints, decodeWindow, frameStep } from './burned-captions.mjs';

// Fragments of adjacent source shots at cut points. An in-point chosen a little
// before the source's own shot change opens the item with the tail of the
// previous shot (e.g. in 22.68 s while the source cuts at 23.23 s: 0.55 s of the
// old shot); an in-point inside a flash transition opens with a few white
// frames; an out-point a little after a source change ends with the head of
// the next shot. This checks the SOURCE around every video item's in/out point.
//
// Shot change at decoded transition k (frame k − 1 → k), on full grey frames
// scaled like the burned-caption check: the mean absolute difference MAD(k) is
// ≥ shot_mad (the burned-caption check's full-frame shot threshold, 30 grey
// levels) AND either
//   - MAD(k) − MAD(k − 1) ≥ scene_jump (= render scene threshold × 100, i.e. 30
//     for the default 0.3; ffmpeg's scene score is min(MAD, ΔMAD)/100 on the
//     same 0–255 scale), a hard cut that stands out of the motion around it, or
//   - the mean grey level steps by ≥ shot_mad, a flash/fade frame.
// Fast camera motion has a high but steady MAD and a steady mean, so it is not a
// change; a white flash steps the mean on its way in and out.
//
// A change inside the item within window_seconds of an edge is a FRAGMENT when
// the shot piece shown at that edge belongs mostly to the neighbouring shot
// (more of that shot lies outside the item than inside it) or the piece is a
// flash: a shot shorter than flash_seconds. A short shot shown whole from its
// first frame (in) or to its last frame (out) is a deliberate edit, not a
// fragment, and a change exactly on the in-point frame / on the first frame
// after the out-point is aligned.
export const CUT_FRAGMENT = Object.freeze({
  window_seconds: 1.0, // look this far inside the item from each edge (source seconds)
  flash_seconds: 0.5, // a shot shorter than this next to a cut is a flash
  shot_mad: CAPTION_CUT.shot_mad, // 0–255 grey levels
  analysis_short_edge: CAPTION_CUT.analysis_short_edge,
  concurrency: CAPTION_CUT.concurrency,
});
export const FRAGMENT_METHOD = 'full-frame grey difference on the source around each cut point (hard cut: MAD ≥ shot_mad and MAD jump ≥ scene_jump; flash/fade: mean step ≥ shot_mad)';

// Indices k ≥ 2 of decoded frames that start a new shot (see above).
export function shotChanges(frames, { sceneJump, shotMad = CUT_FRAGMENT.shot_mad }) {
  const mad = [NaN], mean = [];
  for (let k = 0; k < frames.length; k++) {
    const cur = frames[k], prev = frames[k - 1];
    let sum = 0, diff = 0;
    for (let i = 0; i < cur.length; i++) { sum += cur[i]; if (prev) diff += Math.abs(cur[i] - prev[i]); }
    mean.push(sum / cur.length);
    if (k) mad.push(diff / cur.length);
  }
  const changes = [];
  for (let k = 2; k < frames.length; k++) {
    if (mad[k] >= shotMad && (mad[k] - mad[k - 1] >= sceneJump || Math.abs(mean[k] - mean[k - 1]) >= shotMad)) changes.push(k);
  }
  return changes;
}

const lastAtOrBefore = (times, t) => { let k = -1; while (k + 1 < times.length && times[k + 1] <= t + TIME_EPS) k++; return k; };
const round6 = value => Math.round(value * 1e6) / 1e6;
const midOf = (times, k, frame) => k + 1 < times.length ? (times[k] + times[k + 1]) / 2 : times[k] + frame / 2;

// Judge one cut point. times: decoded source frame times; changes: sorted
// shot-change indices; at: source in/out seconds; step: source seconds per
// output frame; frame: source frame duration; first/last: the item's first and
// last shown source times; fileStart/fileEnd: the window reached the file's
// first/last frame (the shot really starts/ends there).
export function judgeFragment(edge, { times, changes, at, step, frame, first, last, fileStart = false, fileEnd = false, itemFrames }, p = CUT_FRAGMENT) {
  const W = p.window_seconds, F = p.flash_seconds;
  if (edge === 'in') {
    const k0 = lastAtOrBefore(times, at);
    if (k0 < 0) throw new Error('in-point frame not decoded');
    const before = changes.filter(k => k <= k0), s = before.length ? before.at(-1) : fileStart ? 0 : -1;
    const e = changes.find(k => k > k0 && times[k] <= Math.min(at + W, last) + TIME_EPS);
    if (e === undefined) return { result: s === k0 ? 'aligned' : 'clear' };
    const outside = s < 0 ? Infinity : times[k0] - times[s], shown = times[e] - times[k0];
    const flash = outside + shown < F - TIME_EPS;
    if (!flash && outside <= shown) return { result: s === k0 ? 'aligned' : 'clear', change_seconds: round6(times[e]) };
    let c = e; // skip further short shots (a flash's way out) after the first change
    for (let n = changes.find(k => k > c); n !== undefined && times[n] - times[c] < F - TIME_EPS && times[n] <= last + TIME_EPS; n = changes.find(k => k > c)) c = n;
    const suggested = round6(midOf(times, c, frame));
    return { result: 'warn', kind: flash || c !== e ? 'flash' : 'fragment', fragment_frames: c - k0, change_seconds: round6(times[e]),
      suggested_source_in_seconds: suggested, suggested_shift_seconds: round6(suggested - at) };
  }
  const kL = lastAtOrBefore(times, at - step);
  if (kL < 0) throw new Error('out-point frame not decoded');
  const e = changes.find(k => k > kL);
  const inside = changes.filter(k => k <= kL && times[k] >= at - W - TIME_EPS && times[k] > first + TIME_EPS);
  if (!inside.length) return { result: e === kL + 1 ? 'aligned' : 'clear' };
  const s = inside.at(-1), after0 = kL + 1 < times.length ? times[kL + 1] : times[kL] + frame;
  const after = (e !== undefined ? times[e] : fileEnd ? times.at(-1) + frame : Infinity) - after0, shown = after0 - times[s];
  const flash = shown + after < F - TIME_EPS;
  if (!flash && after <= shown) return { result: e === kL + 1 ? 'aligned' : 'clear', change_seconds: round6(times[s]) };
  let c = s; // skip further short shots before the last change (a flash's way in)
  for (let q = inside.findLast(k => k < c); q !== undefined && times[c] - times[q] < F - TIME_EPS; q = inside.findLast(k => k < c)) c = q;
  // Keep output frames whose source time is before frame c: the last shown frame is c − 1.
  const keep = Math.max(1, Math.ceil((times[c] - first) / step - TIME_EPS));
  const suggested = round6(midOf(times, c, frame));
  return { result: 'warn', kind: flash || c !== s ? 'flash' : 'fragment', fragment_frames: kL + 1 - c, change_seconds: round6(times[s]),
    suggested_source_out_seconds: suggested, suggested_frames: keep, drop_output_frames: itemFrames - keep };
}

// Analyse every video item's in/out point on its source. Returns the check
// fields (status, observation, measured, refs) for render-qa.
export async function cutFragmentCheck(doc, root, { sceneThreshold = 0.3, sampleAt = () => null } = {}) {
  const p = CUT_FRAGMENT, fps = doc.canvas.fps, sceneJump = round6(sceneThreshold * 100);
  const assets = new Map(doc.assets.map(a => [a.id, a]));
  const points = cutPoints(doc);
  const measured = { method: FRAGMENT_METHOD, window_seconds: p.window_seconds, flash_seconds: p.flash_seconds,
    thresholds: { analysis_short_edge: p.analysis_short_edge, shot_mad: p.shot_mad, scene_jump: sceneJump, scene_threshold: sceneThreshold }, points: [] };
  if (!points.length) return { status: 'not_applicable', observation: 'No video media items, so no source cut points to check for shot fragments.', measured };
  const pad = 0.2, startOf = containerStarts(), W = p.window_seconds, F = p.flash_seconds;
  measured.points = await mapLimit(points, p.concurrency, async point => {
    const { item } = point, file = path.join(root, assets.get(item.asset_id).file), step = speedOf(item) / fps;
    const first = item.source_in_seconds, last = first + (item.frames - 1) * step;
    const [from, to] = point.edge === 'in' ? [point.source_seconds - W - pad, point.source_seconds + W + F + pad]
      : [point.source_seconds - W - F - pad, point.source_seconds + W + pad];
    const entry = { item_id: item.id, edge: point.edge, source_seconds: round6(point.source_seconds), output_seconds: round6(point.output_frame / fps) };
    try {
      const window = await decodeWindow(file, from, to, p, await startOf(file));
      if (window.frames.length < 4) throw new Error('too few decoded frames');
      const frame = frameStep(window.times), changes = shotChanges(window.frames, { sceneJump, shotMad: p.shot_mad });
      const judged = judgeFragment(point.edge, { times: window.times, changes, at: point.source_seconds, step, frame, first, last, itemFrames: item.frames,
        fileStart: from <= 0, fileEnd: window.times.at(-1) + 1.5 * frame < to }, p);
      const near = changes.map(k => window.times[k]).filter(t => Math.abs(t - point.source_seconds) <= W + F);
      return { ...entry, ...judged, shot_changes: near.map(round6) };
    } catch (error) {
      return { ...entry, result: 'unknown', error: error.message.slice(0, 200) };
    }
  });
  const warned = measured.points.filter(e => e.result === 'warn'), unknown = measured.points.filter(e => e.result === 'unknown');
  const what = e => e.kind === 'flash' ? 'a flash / very short shot (< 0.5 s)' : e.edge === 'in' ? 'the previous source shot' : 'the next source shot';
  const describe = e => e.edge === 'in'
    ? `${e.item_id} in-point opens with ${e.fragment_frames} frame(s) of ${what(e)}: source in ${e.source_seconds.toFixed(4)} s → ${e.suggested_source_in_seconds.toFixed(6)} s (midpoint of the first frame after the change)`
    : `${e.item_id} out-point ends with ${e.fragment_frames} frame(s) of ${what(e)}: end before the source change at ${e.change_seconds.toFixed(4)} s → ${e.suggested_frames} output frame(s) (drop ${e.drop_output_frames}; source out ${e.suggested_source_out_seconds.toFixed(6)} s)`;
  const status = warned.length ? 'warn' : unknown.length ? 'unknown' : 'pass';
  const scope = `${points.length} source cut point(s)`;
  const unchecked = unknown.length ? ` ${unknown.length} of ${points.length} cut point(s) were not checked (${unknown.map(e => `${e.item_id} ${e.edge}`).join(', ')}): ${[...new Set(unknown.map(e => e.error))].join('; ')}.` : '';
  const observation = warned.length
    ? `${warned.length} of ${scope} show a fragment of an adjacent source shot within ${W} s inside the cut: ${warned.map(describe).join('; ')}.${unchecked}`
    : unknown.length ? `No adjacent-shot fragment at the ${points.length - unknown.length} analysed point(s) of ${scope}, but the check is incomplete.${unchecked}`
      : `No adjacent-shot fragment or flash within ${W} s inside any of ${scope}.`;
  const refs = warned.map(e => {
    const sample = sampleAt(e);
    return { time_seconds: e.output_seconds, item_id: e.item_id, ...(sample ? { sample_id: sample } : {}) };
  });
  return { status, observation, measured, ...(refs.length ? { refs } : {}) };
}
