import path from 'node:path';
import { mapLimit } from './media-analysis.mjs';
import { CAPTION_CUT, TIME_EPS, captionCutCheck, cutPoints, decodeWindow, round6, sourceTimings } from './burned-captions.mjs';
import { fragmentCutCheck } from './cut-fragments.mjs';

// One pass over the SOURCE around every video item's in/out point for all
// cut-point checks (burned-in captions, adjacent-shot fragments). Each cut point
// is decoded once, over the union of the ranges the checks need, and each check
// judges the frames of its own range; each source file is probed once. A decode
// failure makes the point unknown for every check, a check's own failure only
// for that check.
//
// A check (captionCutCheck, fragmentCutCheck) provides measured (method and
// thresholds), none (observation without cut points), range(point) → [from, to]
// source seconds, analyse(point, window, fps, range) → result fields, and
// summary(n) → texts for summarizeCutChecks.
const within = (window, [from, to]) => {
  const keep = window.times.flatMap((t, k) => t >= from - TIME_EPS && t < to ? [k] : []);
  return { ...window, frames: keep.map(k => window.frames[k]), times: keep.map(k => window.times[k]) };
};

export async function runCutChecks(doc, root, checks, { sampleAt = () => null, decode = decodeWindow } = {}) {
  const fps = doc.canvas.fps, assets = new Map(doc.assets.map(a => [a.id, a]));
  const points = cutPoints(doc), timingOf = sourceTimings();
  if (!points.length) return checks.map(check => ({ status: 'not_applicable', observation: check.none, measured: { ...check.measured, points: [] } }));
  const results = await mapLimit(points, CAPTION_CUT.concurrency, async point => {
    const file = path.join(root, assets.get(point.item.asset_id).file), ranges = checks.map(check => check.range(point));
    // source_seconds is the time the render plays (the compiled view, see
    // cutPoints); a corrected in-point also keeps the document's value and frame.
    const written = 'document_source_seconds' in point ? { document_source_seconds: round6(point.document_source_seconds) } : {};
    const frame = 'source_frame' in point ? { source_frame: point.source_frame } : {};
    const entry = { item_id: point.item.id, edge: point.edge, source_seconds: round6(point.source_seconds), ...written, ...frame, output_seconds: round6(point.output_frame / fps) };
    const unknown = error => ({ ...entry, result: 'unknown', error: error.message.slice(0, 200) });
    let window;
    try {
      window = await decode(file, Math.min(...ranges.map(r => r[0])), Math.max(...ranges.map(r => r[1])), CAPTION_CUT, await timingOf(file));
    } catch (error) {
      return checks.map(() => unknown(error));
    }
    return checks.map((check, i) => {
      try {
        return { ...entry, ...check.analyse(point, within(window, ranges[i]), fps, ranges[i]) };
      } catch (error) {
        return unknown(error);
      }
    });
  });
  return checks.map((check, i) => {
    const entries = results.map(r => r[i]);
    return { ...summarizeCutChecks(entries, { ...check.summary(points.length), sampleAt }), measured: { ...check.measured, points: entries } };
  });
}

// Status, observation and refs of one cut-point check. Any warn → warn;
// otherwise any point that could not be checked → unknown (the observation
// names the unchecked points and why); pass only when every cut point was
// analysed and none warned. refs point at the warned cut points in the render.
export function summarizeCutChecks(entries, { scope, finding, describe, warned: warnedText, pass, sampleAt = () => null }) {
  const warned = entries.filter(e => e.result === 'warn'), unknown = entries.filter(e => e.result === 'unknown');
  const status = warned.length ? 'warn' : unknown.length ? 'unknown' : 'pass';
  const unchecked = unknown.length ? ` ${unknown.length} of ${entries.length} cut point(s) were not checked (${unknown.map(e => `${e.item_id} ${e.edge}`).join(', ')}): ${[...new Set(unknown.map(e => e.error))].join('; ')}.` : '';
  const observation = warned.length ? warnedText(warned.length, warned.map(describe).join('; '), unchecked)
    : unknown.length ? `No ${finding} found at the ${entries.length - unknown.length} analysed point(s) of ${scope}, but the check is incomplete.${unchecked}`
      : pass;
  const refs = warned.map(e => {
    const sample = sampleAt(e);
    return { time_seconds: e.output_seconds, item_id: e.item_id, ...(sample ? { sample_id: sample } : {}) };
  });
  return { status, observation, ...(refs.length ? { refs } : {}) };
}

// Both render-qa cut-point checks from one decode per cut point.
export async function cutPointChecks(doc, root, { band, sceneThreshold, sampleAt, decode } = {}) {
  const [burned, fragments] = await runCutChecks(doc, root, [captionCutCheck(band), fragmentCutCheck(sceneThreshold)], { sampleAt, decode });
  return { burned, fragments };
}

// Each check on its own (same pass, one check).
export const burnedCaptionCheck = async (doc, root, { band, sampleAt } = {}) => (await runCutChecks(doc, root, [captionCutCheck(band)], { sampleAt }))[0];
export const cutFragmentCheck = async (doc, root, { sceneThreshold, sampleAt } = {}) => (await runCutChecks(doc, root, [fragmentCutCheck(sceneThreshold)], { sampleAt }))[0];
