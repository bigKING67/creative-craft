import path from 'node:path';
import { ffprobeJson, run } from './project.mjs';
import { sourceSeconds } from './timeline.mjs';
import { mapLimit, mediaTool } from './media-analysis.mjs';

// Burned-in caption cut points. Source footage often carries captions that are
// part of the picture and switch slightly after the speech they belong to; an
// in-point chosen from speech gaps can still show the previous line, an
// out-point can flash the next one. This is a frame-difference heuristic on a
// horizontal caption band of the SOURCE frames around each cut, not OCR: it
// cannot read, match or judge caption text, only report where the band
// changes as a step.
//
// Step detector (measured on real talking-head / product footage, see README):
// a pixel "steps" at transition k when it is steady (max − min ≤ steadyRange)
// over the steadyFrames frames before k and the steadyFrames frames from k on,
// and its mean level moves by ≥ stepDelta. Burned-in captions are static
// between changes and switch in one frame, so their glyph pixels step together
// inside one text line; hands, faces and camera motion are not steady and do
// not step. The score is the largest share of stepping pixels in any window of
// lineHeight rows inside the band (one caption line). A caption change is a
// transition whose score is ≥ lineShare. When the rest of the frame changes as
// well (mean absolute difference outside the band ≥ shotMad) the step is a
// full-frame shot change, not a caption change: it is reported as a shot and
// treated as aligned.
export const CAPTION_BAND = Object.freeze({ top: 0.62, bottom: 0.86 });
export const CAPTION_CUT = Object.freeze({
  window_seconds: 0.5, // look this far inside the item from each edge (source seconds)
  analysis_short_edge: 360, // frames are scaled so the shorter edge is this many pixels (grey)
  steady_frames: 3, steady_range: 12, step_delta: 40, // 0–255 grey levels
  line_height: 0.05, // caption line window, fraction of frame height
  line_share: 0.10, // ≥ 10% of the line window's pixels step …
  glyph_level: 200, glyph_share: 0.05, // … and ≥ 5% step to or from a light level (light caption glyphs)
  shot_mad: 30, // mean |Δ| outside the band ≥ 30 → full-frame shot change
  concurrency: 4, // cut-point windows decoded in parallel
});
export const CAPTION_METHOD = 'frame-difference step heuristic on the source caption band (not OCR)';
const round = (value, digits = 3) => Math.round(value * 10 ** digits) / 10 ** digits;

export function captionBand(option) {
  if (option === undefined) return CAPTION_BAND;
  const { top, bottom } = option ?? {};
  if (![top, bottom].every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1) || bottom - top < 0.05) {
    throw new Error('Caption band needs 0 ≤ top < bottom ≤ 1 with bottom − top ≥ 0.05');
  }
  return { top, bottom };
}

// Pure detector over decoded grey frames (Uint8Array/Buffer of width × height
// each) with their source times. Returns every transition that is a caption
// change or a full-frame shot change.
export function stepEvents({ frames, times, width, height }, band = CAPTION_BAND, p = CAPTION_CUT) {
  const N = width * height, m = p.steady_frames;
  const y0 = Math.round(height * band.top), y1 = Math.min(height, Math.round(height * band.bottom));
  const lineRows = Math.max(1, Math.round(height * p.line_height));
  const rows = new Float64Array(height), bright = new Float64Array(height), events = [];
  for (let k = m; k + m <= frames.length; k++) {
    rows.fill(0); bright.fill(0);
    let rest = 0, restCount = 0;
    const prev = frames[k - 1], cur = frames[k];
    for (let i = 0; i < N; i++) {
      const y = (i / width) | 0, inBand = y >= y0 && y < y1;
      if (!inBand) { rest += Math.abs(cur[i] - prev[i]); restCount++; continue; }
      let lo = 255, hi = 0, before = 0;
      for (let j = k - m; j < k; j++) { const v = frames[j][i]; if (v < lo) lo = v; if (v > hi) hi = v; before += v; }
      if (hi - lo > p.steady_range) continue;
      lo = 255; hi = 0; let after = 0;
      for (let j = k; j < k + m; j++) { const v = frames[j][i]; if (v < lo) lo = v; if (v > hi) hi = v; after += v; }
      if (hi - lo > p.steady_range || Math.abs(after - before) / m < p.step_delta) continue;
      rows[y]++;
      if (Math.max(after, before) / m >= p.glyph_level) bright[y]++;
    }
    const best = values => {
      let top = 0, acc = 0;
      for (let y = y0; y < y1; y++) { acc += values[y]; if (y - lineRows >= y0) acc -= values[y - lineRows]; if (acc > top) top = acc; }
      return top / (Math.min(lineRows, y1 - y0) * width);
    };
    const lineShare = best(rows), glyphShare = best(bright), restMad = restCount ? rest / restCount : 0;
    if (lineShare < p.line_share || glyphShare < p.glyph_share) continue;
    events.push({ source_seconds: round(times[k], 4), line_share: round(lineShare), glyph_share: round(glyphShare),
      rest_mad: round(restMad, 1), kind: restMad >= p.shot_mad ? 'shot' : 'caption' });
  }
  return events;
}

// Decode about [from, to) of a source file as grey frames (shorter edge
// analysis_short_edge) with their source times: -copyts keeps the decoded
// timestamps (showinfo pts_time), minus the container start time so they are
// media-time seconds like data-media-start. -fps_mode passthrough writes every
// decoded frame exactly once (the rawvideo muxer would otherwise default to
// constant frame rate and duplicate/drop frames of variable-frame-rate sources),
// so frame k is the frame showinfo reported k-th.
export async function decodeWindow(file, from, to, p = CAPTION_CUT, startTime = 0) {
  const e = p.analysis_short_edge, start = Math.max(0, from);
  const { stdout, stderr } = await run(mediaTool('ffmpeg'), ['-hide_banner', '-nostats', '-v', 'info', '-copyts', '-ss', String(start), '-t', String(Math.max(0.05, to - start)), '-i', file,
    '-an', '-sn', '-vf', `scale='if(lt(iw,ih),${e},-2)':'if(lt(iw,ih),-2,${e})',format=gray,showinfo`, '-fps_mode', 'passthrough', '-f', 'rawvideo', 'pipe:1'],
  { encoding: 'buffer', timeout: 120000, maxBuffer: 512 * 1024 * 1024 });
  return splitFrames(stdout, stderr.toString(), startTime);
}

// Pair raw grey frames with showinfo times. A frame/time count mismatch means
// the times cannot be trusted, so it throws (the cut point becomes unknown)
// instead of silently truncating to the shorter list.
export function splitFrames(raw, log, startTime = 0) {
  const size = log.match(/\bs:(\d+)x(\d+)/);
  if (!size) return { frames: [], times: [], width: 0, height: 0 };
  const width = Number(size[1]), height = Number(size[2]), N = width * height;
  const times = [...log.matchAll(/pts_time:\s*(-?[\d.]+)/g)].map(m => Number(m[1]) - startTime);
  if (raw.length % N !== 0 || raw.length / N !== times.length) {
    throw new Error(`decoded ${raw.length / N} frame(s) but showinfo reported ${times.length} timestamp(s); frame times are not trustworthy`);
  }
  const frames = Array.from({ length: times.length }, (_, k) => raw.subarray(k * N, (k + 1) * N));
  return { frames, times, width, height };
}

const frameStep = times => {
  const gaps = times.slice(1).map((t, i) => t - times[i]).filter(g => g > 1e-4).sort((a, b) => a - b);
  return gaps.length ? gaps[gaps.length >> 1] : 1 / 30;
};

// Judge one cut point from the caption events around it. In-point: a caption
// change strictly inside (edge, edge + window] means the previous line is still
// on screen at the cut → warn, suggest the change time (unless one is at the
// edge itself, i.e. the new line starts with the cut). Out-point: a change in
// [edge − window, edge) means the next line flashes before the cut → warn,
// suggest ending at the change. "At the edge" = within half a source frame.
export function judgeCutPoint(edge, at, events, { frame, window = CAPTION_CUT.window_seconds }) {
  const half = frame / 2, captions = events.filter(e => e.kind === 'caption');
  const inside = edge === 'in' ? captions.filter(e => e.source_seconds > at + half && e.source_seconds <= at + window + 1e-6)
    : captions.filter(e => e.source_seconds >= at - window - 1e-6 && e.source_seconds < at - half);
  const atEdge = captions.some(e => Math.abs(e.source_seconds - at) <= half);
  if (!inside.length) return { result: atEdge ? 'aligned' : 'clear' };
  if (edge === 'in' && atEdge) return { result: 'aligned' };
  const pick = inside[0]; // in: earliest change; out: earliest change before the cut
  return { result: 'warn', suggested_source_seconds: pick.source_seconds, suggested_shift_seconds: round(pick.source_seconds - at, 4) };
}

// Cut points of every video-track media item whose asset has picture.
export function cutPoints(doc) {
  const fps = doc.canvas.fps, assets = new Map(doc.assets.map(a => [a.id, a]));
  const video = new Set(doc.tracks.filter(t => t.kind === 'video').map(t => t.id));
  return doc.items.filter(i => i.kind === 'media' && video.has(i.track_id) && assets.get(i.asset_id)?.video !== false).flatMap(item => {
    const sourceOut = item.source_in_seconds + sourceSeconds(item, fps);
    return [{ item, edge: 'in', source_seconds: item.source_in_seconds, output_frame: item.start_frame },
      { item, edge: 'out', source_seconds: sourceOut, output_frame: item.start_frame + item.frames }];
  });
}

// Analyse every cut point on its source asset. Returns the check fields
// (status, observation, measured, refs) for render-qa.
export async function burnedCaptionCheck(doc, root, { band: bandOption, sampleAt = () => null } = {}) {
  const band = captionBand(bandOption), p = CAPTION_CUT, fps = doc.canvas.fps;
  const assets = new Map(doc.assets.map(a => [a.id, a]));
  const points = cutPoints(doc);
  const measured = { method: CAPTION_METHOD, band, window_seconds: p.window_seconds,
    thresholds: { analysis_short_edge: p.analysis_short_edge, steady_frames: p.steady_frames, steady_range: p.steady_range, step_delta: p.step_delta,
      line_height: p.line_height, line_share: p.line_share, glyph_level: p.glyph_level, glyph_share: p.glyph_share, shot_mad: p.shot_mad }, points: [] };
  if (!points.length) return { status: 'not_applicable', observation: 'No video media items, so no source cut points to check for burned-in captions.', measured };
  // Pad each window so transitions at its ends still have steady_frames on both
  // sides (sized for sources down to 15 fps). Windows decode with bounded
  // concurrency; each file's container start time is probed once.
  const pad = (p.steady_frames + 1) / 15, starts = new Map();
  const startOf = file => {
    if (!starts.has(file)) starts.set(file, ffprobeJson(file).then(info => Number(info.format.start_time) || 0));
    return starts.get(file);
  };
  measured.points = await mapLimit(points, p.concurrency, async point => {
    const asset = assets.get(point.item.asset_id), file = path.join(root, asset.file);
    const [from, to] = point.edge === 'in' ? [point.source_seconds - pad, point.source_seconds + p.window_seconds + pad]
      : [point.source_seconds - p.window_seconds - pad, point.source_seconds + pad];
    const entry = { item_id: point.item.id, edge: point.edge, source_seconds: round(point.source_seconds, 4), output_seconds: round(point.output_frame / fps, 6) };
    try {
      const window = await decodeWindow(file, from, to, p, await startOf(file));
      if (window.frames.length < 2 * p.steady_frames + 1) throw new Error('too few decoded frames');
      const events = stepEvents(window, band, p), frame = frameStep(window.times);
      const near = events.filter(e => Math.abs(e.source_seconds - point.source_seconds) <= p.window_seconds + frame);
      return { ...entry, ...judgeCutPoint(point.edge, point.source_seconds, near, { frame, window: p.window_seconds }),
        caption_changes: near.filter(e => e.kind === 'caption'), shot_changes: near.filter(e => e.kind === 'shot').map(e => e.source_seconds) };
    } catch (error) {
      return { ...entry, result: 'unknown', error: error.message.slice(0, 200) };
    }
  });
  // Any warn → warn; otherwise any point that could not be checked → unknown;
  // pass only when every cut point was analysed and none warned.
  const warned = measured.points.filter(e => e.result === 'warn'), unknown = measured.points.filter(e => e.result === 'unknown');
  const describe = e => `${e.item_id} ${e.edge}-point at source ${e.source_seconds.toFixed(3)} s → ${e.suggested_source_seconds.toFixed(3)} s`;
  const status = warned.length ? 'warn' : unknown.length ? 'unknown' : 'pass';
  const scope = `${points.length} source cut point(s), caption band ${round(band.top * 100, 1)}–${round(band.bottom * 100, 1)}% of the source frame height`;
  const reasons = [...new Set(unknown.map(e => e.error))].join('; ');
  const unchecked = unknown.length ? ` ${unknown.length} of ${points.length} cut point(s) were not checked (${unknown.map(e => `${e.item_id} ${e.edge}`).join(', ')}): ${reasons}.` : '';
  const observation = warned.length
    ? `${warned.length} of ${scope} show a burned-in caption change within ${p.window_seconds} s inside the cut (in-point: previous line still shown; out-point: next line flashes). Suggested source times: ${warned.map(describe).join('; ')}.${unchecked} Frame-difference heuristic, not OCR.`
    : unknown.length
      ? `No burned-in caption change found at the ${points.length - unknown.length} analysed point(s) of ${scope}, but the check is incomplete.${unchecked}`
      : `No burned-in caption change within ${p.window_seconds} s inside any of ${scope}. Frame-difference heuristic, not OCR; it cannot read caption text.`;
  const refs = warned.map(e => {
    const sample = sampleAt(e);
    return { time_seconds: e.output_seconds, item_id: e.item_id, ...(sample ? { sample_id: sample } : {}) };
  });
  return { status, observation, measured, ...(refs.length ? { refs } : {}) };
}
