import { speedOf } from './timeline.mjs';
import { CAPTION_CUT, TIME_EPS, frameMidAt, frameStep, round6 } from './burned-captions.mjs';

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

// Judge one cut point. times: decoded source frame times; changes: sorted
// shot-change indices; at: source in/out seconds; step: source seconds per
// output frame; frame: source frame duration; first/last: the item's first and
// last shown source times; fileStart/fileEnd: the window reached the file's
// first/last frame (the shot really starts/ends there); itemFrames: the item's
// output frames.
//
// A shot piece at an edge warns only when part of that shot lies OUTSIDE the
// item (in: shown before the in-point; out: after the out-point) and either it
// is mostly outside or the shot is a flash. A shot shown from its own first
// frame (outside = 0) or to its own last frame (after = 0) is aligned with the
// cut even when it is short: it is shown whole on that side, an edit choice.
//
// fragment_frames counts OUTPUT frames of the render that show the fragment
// (through speed and source vs canvas frame rate: output frame j shows the
// source frame at or before first + j × step); source_frames counts the source
// frames of the fragment. change_mid_seconds is the midpoint of the changed frame.
export function judgeFragment(edge, { times, changes, at, step, frame, first, last, fileStart = false, fileEnd = false, itemFrames }, p = CUT_FRAGMENT) {
  const W = p.window_seconds, F = p.flash_seconds;
  // Output frames whose source time is before t (they show frames before t).
  const outputBefore = t => Math.min(itemFrames, Math.max(0, Math.ceil((t - first) / step - TIME_EPS)));
  const change = k => ({ change_seconds: round6(times[k]), change_mid_seconds: round6(frameMidAt(times, k, frame)) });
  if (edge === 'in') {
    const k0 = lastAtOrBefore(times, at);
    if (k0 < 0) throw new Error('in-point frame not decoded');
    const before = changes.filter(k => k <= k0), s = before.length ? before.at(-1) : fileStart ? 0 : -1;
    const e = changes.find(k => k > k0 && times[k] <= Math.min(at + W, last) + TIME_EPS);
    if (e === undefined) return { result: s === k0 ? 'aligned' : 'clear' };
    const outside = s < 0 ? Infinity : times[k0] - times[s], shown = times[e] - times[k0];
    const flash = outside + shown < F - TIME_EPS;
    if (!(outside > TIME_EPS && (flash || outside > shown))) return { result: s === k0 ? 'aligned' : 'clear', ...change(e) };
    let c = e; // skip further short shots (a flash's way out) after the first change
    for (let n = changes.find(k => k > c); n !== undefined && times[n] - times[c] < F - TIME_EPS && times[n] <= last + TIME_EPS; n = changes.find(k => k > c)) c = n;
    const suggested = round6(frameMidAt(times, c, frame));
    return { result: 'warn', kind: flash || c !== e ? 'flash' : 'fragment', fragment_frames: outputBefore(times[c]), source_frames: c - k0, ...change(e),
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
  if (!(after > TIME_EPS && (flash || after > shown))) return { result: e === kL + 1 ? 'aligned' : 'clear', ...change(s) };
  let c = s; // skip further short shots before the last change (a flash's way in)
  for (let q = inside.findLast(k => k < c); q !== undefined && times[c] - times[q] < F - TIME_EPS; q = inside.findLast(k => k < c)) c = q;
  // Keep output frames whose source time is before frame c: the last shown frame is c − 1.
  const before = outputBefore(times[c]), keep = Math.max(1, before);
  const suggested = round6(frameMidAt(times, c, frame));
  return { result: 'warn', kind: flash || c !== s ? 'flash' : 'fragment', fragment_frames: itemFrames - before, source_frames: kL + 1 - c, ...change(s),
    suggested_source_out_seconds: suggested, suggested_frames: keep, drop_output_frames: itemFrames - keep };
}

// The fragment analysis for the shared cut-point pass (cut-checks.mjs): the
// source range it needs around a cut point, the per-point judgement on the
// decoded frames of that range, and the texts of its summary.
export function fragmentCutCheck(sceneThreshold = 0.3, p = CUT_FRAGMENT) {
  const sceneJump = round6(sceneThreshold * 100), pad = 0.2, W = p.window_seconds, F = p.flash_seconds;
  const what = e => e.kind === 'flash' ? 'a flash / very short shot (< 0.5 s)' : e.edge === 'in' ? 'the previous source shot' : 'the next source shot';
  return {
    measured: { method: FRAGMENT_METHOD, window_seconds: W, flash_seconds: F,
      thresholds: { analysis_short_edge: p.analysis_short_edge, shot_mad: p.shot_mad, scene_jump: sceneJump, scene_threshold: sceneThreshold } },
    none: 'No video media items, so no source cut points to check for shot fragments.',
    range: point => point.edge === 'in' ? [point.source_seconds - W - pad, point.source_seconds + W + F + pad]
      : [point.source_seconds - W - F - pad, point.source_seconds + W + pad],
    analyse(point, window, fps, [from, to]) {
      if (window.frames.length < 4) throw new Error('too few decoded frames');
      const { item } = point, step = speedOf(item) / fps, first = item.source_in_seconds, last = first + (item.frames - 1) * step;
      const frame = frameStep(window.times), changes = shotChanges(window.frames, { sceneJump, shotMad: p.shot_mad });
      const judged = judgeFragment(point.edge, { times: window.times, changes, at: point.source_seconds, step, frame, first, last, itemFrames: item.frames,
        fileStart: from <= 0, fileEnd: window.times.at(-1) + 1.5 * frame < to }, p);
      const near = changes.map(k => window.times[k]).filter(t => Math.abs(t - point.source_seconds) <= W + F);
      return { ...judged, shot_changes: near.map(round6) };
    },
    summary: n => ({
      scope: `${n} source cut point(s)`, finding: 'adjacent-shot fragment',
      describe: e => e.edge === 'in'
        ? `${e.item_id} in-point opens with ${e.fragment_frames} output frame(s) (${e.source_frames} source frame(s)) of ${what(e)}: source in ${e.source_seconds.toFixed(6)} s → ${e.suggested_source_in_seconds.toFixed(6)} s (midpoint of the first frame after the change)`
        : `${e.item_id} out-point ends with ${e.fragment_frames} output frame(s) (${e.source_frames} source frame(s)) of ${what(e)}: end before the source change (changed frame midpoint ${e.change_mid_seconds.toFixed(6)} s) → ${e.suggested_frames} output frame(s) (drop ${e.drop_output_frames}; source out ${e.suggested_source_out_seconds.toFixed(6)} s, midpoint of the changed frame)`,
      warned: (count, details, unchecked) => `${count} of ${n} source cut point(s) show a fragment of an adjacent source shot within ${W} s inside the cut: ${details}.${unchecked}`,
      pass: `No adjacent-shot fragment or flash within ${W} s inside any of ${n} source cut point(s).`,
    }),
  };
}
