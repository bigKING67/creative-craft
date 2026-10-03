// Source frame alignment (EditDocument v2 asset.frame_rate). Pure (only the
// pure timeline math), so compilation, font binding and QA can all share it.
//
// A media item's source_in_seconds is a decimal the author (or an agent) wrote,
// sometimes truncated: 24.4333 for frame 733 of a 30 fps source (733/30 =
// 24.43333…). The renderer shows the frame whose time is ≤ the seek time, so a
// truncated in-point shows the PREVIOUS frame. Compilation corrects exactly this
// case and nothing else: for a video-track media item of an asset with
// frame_rate, an in-point strictly less than TRUNCATION_FRAMES (0.01 frame)
// below a frame's start plays from that frame's start + CORRECTION_SECONDS
// (0.1 ms). Every other in-point (on a frame start, or further inside a frame)
// is kept, so a split stays continuous, an exact audio in-point stays exact and
// the shift is at most 0.01 frame + 0.1 ms. Audio-track items are never changed.
// Arithmetic is exact: the in-point is taken as the decimal the document holds
// (the shortest round-trip form of the JSON number) and the frame rate as an
// integer ratio, both as BigInt fractions. The document is never rewritten.
import { SOURCE_END_TOLERANCE, round9, sourceSeconds } from './timeline.mjs';

export const TRUNCATION_FRAMES = Object.freeze({ num: 1n, den: 100n }); // 0.01 frame
export const CORRECTION_SECONDS = 0.0001;
const FRAME_RATE = /^([1-9][0-9]{0,5})\/([1-9][0-9]{0,5})$/;

export const validFrameRate = value => typeof value === 'string' && FRAME_RATE.test(value);
export function parseFrameRate(value) {
  const m = FRAME_RATE.exec(String(value ?? ''));
  if (!m) throw new Error(`Invalid frame_rate ${JSON.stringify(value)} (expected "<num>/<den>", e.g. "30/1" or "30000/1001")`);
  return { num: BigInt(m[1]), den: BigInt(m[2]) };
}

// Exact {p, q} with value = p / q for a finite non-negative JS number, from its
// shortest round-trip decimal form ("24.4333", "1e-7", "1.5e+21").
function decimalFraction(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw new Error(`Source time must be a finite non-negative number: ${value}`);
  const m = /^(\d+)(?:\.(\d+))?(?:e([+-]\d+))?$/.exec(String(value));
  if (!m) throw new Error(`Unsupported number form: ${value}`);
  const digits = BigInt(`${m[1]}${m[2] ?? ''}`), exponent = Number(m[3] ?? 0) - (m[2]?.length ?? 0);
  return exponent >= 0 ? { p: digits * 10n ** BigInt(exponent), q: 1n } : { p: digits, q: 10n ** BigInt(-exponent) };
}

const gcd = (a, b) => { while (b) [a, b] = [b, a % b]; return a; };
// "30/1", "30000/1001" from ffprobe ratios, reduced; null when not a usable rate.
export function reduceFrameRate(value) {
  const m = /^(\d+)\/(\d+)$/.exec(String(value ?? ''));
  if (!m) return null;
  let num = BigInt(m[1]), den = BigInt(m[2]);
  if (!num || !den) return null;
  const g = gcd(num, den); num /= g; den /= g;
  const text = `${num}/${den}`;
  return validFrameRate(text) ? text : null;
}

// The source frame k whose start (k / rate) a truncated in-point fell short of:
// `seconds` is below k / rate by strictly less than 0.01 frame. Null for any
// other in-point (exactly on a frame start, or 0.01 frame or more inside one).
export function truncatedFrame(seconds, frameRate) {
  const { num, den } = typeof frameRate === 'string' ? parseFrameRate(frameRate) : frameRate;
  const { p, q } = decimalFraction(seconds);
  // Position in frames: seconds × num / den = P / Q.
  const P = p * num, Q = q * den, rest = P % Q; // 0 ≤ rest < Q
  // Below the next frame start by (Q − rest) / Q frames.
  if (!rest || (Q - rest) * TRUNCATION_FRAMES.den >= Q * TRUNCATION_FRAMES.num) return null;
  return Number(P / Q + 1n);
}

// Compiled in-point for an in-point on a source of `frameRate`:
// { seconds: frame start + 0.1 ms, frame } when truncated, else null (keep it).
export function correctedSourceIn(seconds, frameRate) {
  const frame = truncatedFrame(seconds, frameRate);
  if (frame === null) return null;
  const { num, den } = parseFrameRate(frameRate);
  return { seconds: round9(frame * Number(den) / Number(num) + CORRECTION_SECONDS), frame };
}

// The document as compiled, computed once per render or QA pass and shared by
// everything that depends on source time (data-media-start, linked caption
// windows, font runs, QA caption samples, cut-point checks). Video-track media
// items of assets with frame_rate get their corrected in-point; an item whose
// corrected range would pass the asset end (beyond SOURCE_END_TOLERANCE, as
// validateV2) keeps its in-point. Audio-track items are unchanged.
// validateV2 is the single source of the asset rules (frame_rate only on assets
// with a picture); this reads frame_rate only and does not validate.
// The input is never mutated; a view passed in again is returned as is.
const VIEWS = new WeakSet(), CORRECTIONS = new WeakMap();
export function compiledView(doc) {
  if (VIEWS.has(doc)) return doc;
  const fps = doc.canvas.fps, assets = new Map(doc.assets.filter(a => a.frame_rate).map(a => [a.id, a]));
  const video = new Set(doc.tracks.filter(t => t.kind === 'video').map(t => t.id));
  const items = doc.items.map(item => {
    const asset = item.kind === 'media' && video.has(item.track_id) ? assets.get(item.asset_id) : undefined;
    const fix = asset ? correctedSourceIn(item.source_in_seconds, asset.frame_rate) : null;
    if (!fix || fix.seconds + sourceSeconds(item, fps) > asset.duration + SOURCE_END_TOLERANCE) return item;
    const compiled = { ...item, source_in_seconds: fix.seconds };
    CORRECTIONS.set(compiled, { written: item, frame: fix.frame });
    return compiled;
  });
  const view = { ...doc, items };
  VIEWS.add(view);
  return view;
}

// For an item of a compiled view: { written, frame } (the document's item and
// the source frame its in-point was corrected to), or null when unchanged.
export const correctionOf = item => CORRECTIONS.get(item) ?? null;

// The video stream analysed for an asset (width, height, frame_rate and the
// `video` flag): the first video stream that is not cover art, or null.
export const pictureStream = info => (info?.streams ?? []).find(s => s.codec_type === 'video' && !s.disposition?.attached_pic) ?? null;

// frame_rate recorded at import from one ffprobe JSON (-show_streams
// -show_format), or null. Recorded only when the frame grid k / rate is
// trustworthy:
//   - the picture stream reports the same rate as r_frame_rate and
//     avg_frame_rate (compared reduced). They differ for variable-frame-rate
//     sources (and for some damaged or edited constant-rate files); such
//     sources get no frame_rate and keep the renderer behaviour;
//   - the picture stream starts at media time 0 and so does the file (stream
//     start_time and format start_time both 0), so frame k starts at k / rate.
// Audio-only files and cover art have no picture stream and get none.
export function probedFrameRate(info, video = pictureStream(info)) {
  if (!video) return null;
  const rate = reduceFrameRate(video.r_frame_rate);
  if (!rate || rate !== reduceFrameRate(video.avg_frame_rate)) return null;
  const zero = value => value !== undefined && value !== null && value !== '' && Number(value) === 0;
  return zero(video.start_time) && zero(info?.format?.start_time) ? rate : null;
}
