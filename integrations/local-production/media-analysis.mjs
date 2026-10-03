// Shared media-tool plumbing for ASR, render, QA and smoke verification: the
// ffmpeg/ffprobe executable lookup, ffmpeg filter-log interval parsing
// (silencedetect / blackdetect / freezedetect) and interval arithmetic.
// No imports, so every layer (project.mjs included) can depend on it.

const TOOL_ENV = Object.freeze({ ffmpeg: 'CREATIVE_FFMPEG', ffprobe: 'CREATIVE_FFPROBE' });
// Executable for ffmpeg or ffprobe: CREATIVE_FFMPEG / CREATIVE_FFPROBE, else PATH.
export function mediaTool(name) {
  const variable = TOOL_ENV[name];
  if (!variable) throw new Error(`Unknown media tool ${name}`);
  return process.env[variable] || name;
}

// Union of [start, end) intervals, sorted and merged.
export function union(intervals) {
  const sorted = intervals.filter(([a, b]) => b > a).map(([a, b]) => [a, b]).sort((x, y) => x[0] - y[0]), merged = [];
  for (const [a, b] of sorted) {
    if (merged.length && a <= merged.at(-1)[1]) merged.at(-1)[1] = Math.max(merged.at(-1)[1], b);
    else merged.push([a, b]);
  }
  return merged;
}
// Total length of the union of intervals clipped to [0, duration].
export const unionLength = (intervals, duration = Infinity) =>
  union(intervals.map(([a, b]) => [Math.max(0, a), Math.min(duration, b)])).reduce((sum, [a, b]) => sum + b - a, 0);
// Overlap length of one {start, end} segment with merged spans.
export const overlap = (segment, spans) => spans.reduce((sum, [a, b]) => sum + Math.max(0, Math.min(b, segment.end) - Math.max(a, segment.start)), 0);

// {start, end} segments from an ffmpeg detector log, e.g. prefix 'silence' for
// silencedetect (silence_start / silence_end). Events are read in log order; a
// start without a matching end runs to `duration`. Starts are clamped to 0
// (silencedetect can report a slightly negative first start).
export function logSegments(log, prefix, duration) {
  const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`${escaped}_(start|end):\\s*(-?[\\d.]+)`, 'g'), segments = [];
  let open = null;
  for (const [, kind, value] of log.matchAll(pattern)) {
    if (kind === 'start') { if (open !== null) segments.push({ start: open, end: Number(value) }); open = Math.max(0, Number(value)); }
    else if (open !== null) { segments.push({ start: open, end: Number(value) }); open = null; }
  }
  if (open !== null) segments.push({ start: open, end: duration });
  return segments;
}

// silencedetect filter argument and its parsed silences.
export const silenceFilter = (noiseDb, minSeconds) => `silencedetect=n=${noiseDb}dB:d=${minSeconds}`;
export const silences = (log, duration) => logSegments(log, 'silence', duration);

// Map with at most `limit` calls in flight; results keep input order.
export async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  const worker = async () => { while (next < items.length) { const index = next++; results[index] = await fn(items[index], index); } };
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, worker));
  return results;
}
