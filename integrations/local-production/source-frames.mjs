// Source frame snapping (EditDocument v2 asset.frame_rate). Pure, no imports,
// so compilation, font binding and QA can all share it.
//
// A media item's source_in_seconds is a decimal the author (or an agent) wrote,
// often truncated: 24.4333 for frame 733 of a 30 fps source (733/30 =
// 24.43333…). The renderer shows the frame whose time is ≤ the seek time, so a
// truncated in-point shows the PREVIOUS frame. For a video asset with an exact
// frame_rate, compilation therefore maps the in-point to a source frame and
// starts playback at that frame's midpoint:
//   - an in-point less than SNAP_TOLERANCE_FRAMES (0.01 frame) below a frame's
//     start is that frame (absorbs decimal truncation);
//   - otherwise it is the frame containing the in-point (floor).
// Arithmetic is exact: the in-point is taken as the decimal the document holds
// (the shortest round-trip form of the JSON number) and the frame rate as an
// integer ratio, both as BigInt fractions. The document is never rewritten.
export const SNAP_TOLERANCE_FRAMES = Object.freeze({ num: 1n, den: 100n }); // 0.01 frame
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

// Source frame shown first for an in-point of `seconds` on a source of
// `frameRate`: { frame, start_seconds, mid_seconds } (frame k spans
// [k / rate, (k + 1) / rate); mid_seconds is the time the compiler seeks to).
export function sourceFrameAt(seconds, frameRate) {
  const { num, den } = typeof frameRate === 'string' ? parseFrameRate(frameRate) : frameRate;
  const { p, q } = decimalFraction(seconds);
  // Position in frames: seconds × num / den = P / Q.
  const P = p * num, Q = q * den;
  let frame = P / Q;
  const rest = P - frame * Q; // 0 ≤ rest < Q
  // Below the next frame start by (Q − rest) / Q frames: absorbed when < 0.01.
  if (rest && (Q - rest) * SNAP_TOLERANCE_FRAMES.den < Q * SNAP_TOLERANCE_FRAMES.num) frame += 1n;
  return { frame: Number(frame), start_seconds: Number(frame * den) / Number(num), mid_seconds: Number((2n * frame + 1n) * den) / Number(2n * num) };
}

// Source time compilation plays from for a media item: the snapped frame
// midpoint for a video asset with frame_rate, else source_in_seconds unchanged.
export function snappedSourceIn(item, asset) {
  if (!asset?.video || !asset.frame_rate) return { seconds: item.source_in_seconds, snapped: false };
  const at = sourceFrameAt(item.source_in_seconds, asset.frame_rate);
  return { seconds: at.mid_seconds, snapped: true, frame: at.frame };
}

// The document as compiled: every media item of a video asset with frame_rate
// (on video or audio tracks, so picture and its own sound stay together) plays
// from its snapped frame midpoint. Returns the same object when nothing snaps;
// otherwise a shallow copy with copied items, the input is never mutated.
// Validate the original document first; this does not validate.
export function snapSourceFrames(doc) {
  const assets = new Map((doc.assets ?? []).filter(a => a.video && a.frame_rate).map(a => [a.id, a]));
  if (!assets.size) return doc;
  return { ...doc, items: doc.items.map(item => {
    if (item.kind !== 'media' || !assets.has(item.asset_id)) return item;
    const { seconds } = snappedSourceIn(item, assets.get(item.asset_id));
    return seconds === item.source_in_seconds ? item : { ...item, source_in_seconds: seconds };
  }) };
}

// frame_rate recorded at import from one ffprobe JSON (-show_streams
// -show_format), or null. Recorded only when the frame grid k / rate is
// trustworthy:
//   - the analysed video stream (first one that is not cover art) reports the
//     same rate as r_frame_rate and avg_frame_rate (compared reduced). They
//     differ for variable-frame-rate sources (and for some damaged or edited
//     constant-rate files); such sources get no frame_rate, so compilation and
//     QA keep the renderer behaviour (seek time, decoded timestamps);
//   - the video stream starts at the media-time origin (its start_pts ×
//     time_base equals the earliest stream start), so frame k starts at k / rate.
// Audio-only files and cover art have no video stream and get none.
export function probedFrameRate(info) {
  const streams = info?.streams ?? [], video = streams.find(s => s.codec_type === 'video' && !s.disposition?.attached_pic);
  if (!video) return null;
  const rate = reduceFrameRate(video.r_frame_rate);
  if (!rate || rate !== reduceFrameRate(video.avg_frame_rate)) return null;
  const startOf = s => {
    const tb = /^(\d+)\/(\d+)$/.exec(String(s.time_base ?? '')), pts = Number(s.start_pts);
    return tb && Number(tb[2]) > 0 && s.start_pts !== undefined && Number.isInteger(pts) ? pts * Number(tb[1]) / Number(tb[2]) : null;
  };
  const starts = streams.map(startOf).filter(v => v !== null), own = startOf(video);
  if (own === null || Math.abs(own - Math.min(...starts)) > 1e-9) return null;
  return rate;
}
