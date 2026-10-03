// Render-support matrix (explicit opt-in, real producer + Chrome):
//   PRODUCER_HEADLESS_SHELL_PATH=… node tests/media-support.matrix.mjs [--json]
// Each case is a 1 s synthetic source imported into a v2 project (createProject),
// rendered as a preview, then judged: completed, the centre of the first frame
// shows the source colour, and (cases with audio) the output carries the tone
// (mean volume above -40 dB). The producer's capture stall watchdog is shortened
// (HF_DE_STALL_MS, default 60 s) so a stalling case fails in ~15 s instead of
// 60 s; cases run 3 at a time. Results: README「素材兼容」.
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createProject, ffprobeJson } from '../project.mjs';
import { renderProject } from '../render.mjs';
import { mapLimit } from '../media-analysis.mjs';
import { frameColor, meanVolume, synthAudio, synthVideo } from './media-fixtures.mjs';

process.env.HF_DE_STALL_MS ??= '15000';
console.log = console.info = console.warn = () => {}; // upstream capture diagnostics

// [label, kind, file name, synth options]
export const CASES = [
  ['H.264 8-bit yuv420p / AAC', 'video', 'h264.mp4', { acodec: 'aac' }],
  ['H.264 8-bit yuv420p / AAC', 'video', 'h264.mov', { acodec: 'aac' }],
  ['H.264 10-bit (High 10) yuv420p10le', 'video', 'h264-10bit.mp4', { pix: 'yuv420p10le' }],
  ['H.264 yuv422p (High 4:2:2)', 'video', 'h264-422.mp4', { pix: 'yuv422p' }],
  ['H.264 yuv444p (High 4:4:4)', 'video', 'h264-444.mp4', { pix: 'yuv444p' }],
  ['HEVC 8-bit (hvc1)', 'video', 'hevc.mp4', { vcodec: 'hevc' }],
  ['HEVC 8-bit (hvc1) / AAC', 'video', 'hevc.mov', { vcodec: 'hevc', acodec: 'aac' }],
  ['HEVC 10-bit (hvc1)', 'video', 'hevc-10bit.mov', { vcodec: 'hevc', pix: 'yuv420p10le' }],
  ['VP9 / Opus', 'video', 'vp9.webm', { vcodec: 'vp9', acodec: 'opus' }],
  ['H.264 / AAC', 'video', 'h264.mkv', { acodec: 'aac' }],
  ['H.264 + MP3 track', 'video', 'h264-mp3.mp4', { acodec: 'mp3' }],
  ['H.264 + Opus track', 'video', 'h264-opus.mp4', { acodec: 'opus' }],
  ['H.264 + PCM s16le track', 'video', 'h264-pcm.mov', { acodec: 'pcm' }],
  ['H.264 + FLAC track', 'video', 'h264-flac.mp4', { acodec: 'flac' }],
  ['H.264 + ALAC track', 'video', 'h264-alac.mov', { acodec: 'alac' }],
  ['H.264 + ALAC track', 'video', 'h264-alac.mp4', { acodec: 'alac' }],
  ['HEVC 10-bit HLG (iPhone HDR)', 'video', 'hevc-hlg.mov', { vcodec: 'hevc', pix: 'yuv420p10le', acodec: 'aac',
    extra: ['-color_primaries', 'bt2020', '-color_trc', 'arib-std-b67', '-colorspace', 'bt2020nc'] }],
  ['HEVC 8-bit variable frame rate', 'video', 'hevc-vfr.mov', { vcodec: 'hevc', vfr: true, acodec: 'aac' }],
  ['H.264 variable frame rate', 'video', 'h264-vfr.mp4', { vfr: true }],
  ['HEVC 8-bit rotated 90°', 'video', 'hevc-rot.mov', { vcodec: 'hevc', rotate: 90 }],
  ['AAC', 'audio', 'aac.m4a', { acodec: 'aac' }],
  ['MP3', 'audio', 'mp3.mp3', { acodec: 'mp3' }],
  ['Opus in MP4', 'audio', 'opus.mp4', { acodec: 'opus' }],
  ['Opus in Ogg', 'audio', 'opus.ogg', { acodec: 'opus' }],
  ['PCM s16le WAV', 'audio', 'pcm.wav', { acodec: 'pcm' }],
  ['FLAC', 'audio', 'flac.flac', { acodec: 'flac' }],
  ['ALAC in M4A', 'audio', 'alac.m4a', { acodec: 'alac' }],
];

const FPS = 30;
// Knobs for reproducing heavier sources: MATRIX_ONLY (regex on the file name),
// MATRIX_SECONDS (source length, default 1), MATRIX_IN (in-point, default 0),
// MATRIX_SIZE (source and canvas WxH, default 320x240), MATRIX_FULL=1 (export
// instead of preview).
const ONLY = new RegExp(process.env.MATRIX_ONLY ?? '.'), SECONDS = Number(process.env.MATRIX_SECONDS ?? 1), IN = Number(process.env.MATRIX_IN ?? 0);
const SIZE = process.env.MATRIX_SIZE ?? '320x240', [WIDTH, HEIGHT] = SIZE.split('x').map(Number), FULL = process.env.MATRIX_FULL === '1';
async function runCase([label, kind, name, options], dir) {
  const work = path.join(dir, name.replace(/\W/g, '_')), source = path.join(work, name), root = path.join(work, 'project');
  await fs.mkdir(work);
  try {
    if (kind === 'video') await synthVideo(source, { seconds: SECONDS, size: SIZE, ...options });
    else await synthAudio(source, { seconds: SECONDS, ...options });
  } catch (error) { return { label, kind, container: path.extname(name).slice(1), ok: false, error: `synthesis failed: ${error.message.split('\n')[0]}`, seconds: 0 }; }
  const sources = kind === 'video' ? [['src', source]] : [['bg', await synthVideo(path.join(work, 'bg.mp4'), { seconds: SECONDS, size: SIZE })], ['src', source]];
  const tracks = [{ id: 'v', kind: 'video', locked: false }, ...(kind === 'audio' ? [{ id: 'a', kind: 'audio', locked: false }] : [])];
  const media = (id, track, asset) => ({ id, track_id: track, kind: 'media', asset_id: asset, start_frame: 0, frames: FPS - 3, source_in_seconds: IN, volume: 1 });
  const items = kind === 'video' ? [media('one', 'v', 'src')] : [media('pic', 'v', 'bg'), media('snd', 'a', 'src')];
  const spec = { project_id: 'matrix', title: label, canvas: { width: WIDTH, height: HEIGHT, fps: FPS },
    assets: sources.map(([id, file]) => ({ id, path: file })), tracks, items };
  const info = await ffprobeJson(source), v = info.streams.find(s => s.codec_type === 'video'), a = info.streams.find(s => s.codec_type === 'audio');
  const row = { label, kind, container: path.extname(name).slice(1), format: info.format.format_name,
    video: v ? `${v.codec_name}/${v.profile ?? '-'}/${v.pix_fmt}` : null, audio: a?.codec_name ?? null };
  const started = Date.now();
  try {
    const out = path.join(work, 'render');
    await createProject(root, spec);
    await renderProject(root, out, { preview: !FULL, signal: AbortSignal.timeout(120000) });
    const [r, g, b] = await frameColor(path.join(out, 'video.mp4'), 0);
    row.first_frame = r > 150 && g < 80 && b < 80 ? 'red' : `rgb(${[r, g, b].map(Math.round)})`;
    if (a) row.mean_volume_db = Math.round(await meanVolume(path.join(out, 'video.mp4')));
    row.ok = row.first_frame === 'red' && (!a || row.mean_volume_db > -40);
  } catch (error) {
    row.ok = false;
    row.error = error.message.split('\n')[0].slice(0, 160);
  }
  row.seconds = Math.round((Date.now() - started) / 1000);
  return row;
}

if (!process.env.PRODUCER_HEADLESS_SHELL_PATH) throw new Error('Set PRODUCER_HEADLESS_SHELL_PATH for the support matrix');
const dir = await fs.mkdtemp('/private/tmp/media-matrix-');
try {
  const rows = await mapLimit(CASES.filter(c => ONLY.test(c[2])), 3, c => runCase(c, dir));
  if (process.argv.includes('--json')) process.stdout.write(JSON.stringify(rows, null, 2) + '\n');
  else {
    process.stdout.write('| 用例 | 用途 | 容器 | 视频 | 音频 | 结果 | 用时 |\n|---|---|---|---|---|---|---|\n');
    for (const r of rows) process.stdout.write(`| ${r.label} | ${r.kind === 'video' ? '视频' : '独立音频'} | ${r.container} | ${r.video ?? '—'} | ${r.audio ?? '—'} | ${r.ok ? '可渲染' : `失败：${r.error ?? `首帧 ${r.first_frame}，音量 ${r.mean_volume_db} dB`}`} | ${r.seconds} s |\n`);
  }
} finally { await fs.rm(dir, { recursive: true, force: true }); }
