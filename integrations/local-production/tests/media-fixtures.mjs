// Short synthetic media for the render-size tests and the support matrix.
// Self-authored lavfi signals only; every file is a few hundred kilobytes.
import * as fs from 'node:fs/promises';
import { run } from '../project.mjs';
import { mediaTool } from '../media-analysis.mjs';

const VIDEO = {
  h264: ['-c:v', 'libx264', '-preset', 'ultrafast'],
  hevc: ['-c:v', 'libx265', '-preset', 'ultrafast', '-x265-params', 'log-level=error', '-tag:v', 'hvc1'],
  vp9: ['-c:v', 'libvpx-vp9', '-deadline', 'realtime', '-cpu-used', '8'],
};
const AUDIO = {
  aac: ['-c:a', 'aac'], mp3: ['-c:a', 'libmp3lame'], opus: ['-c:a', 'libopus'], pcm: ['-c:a', 'pcm_s16le'],
  flac: ['-c:a', 'flac'], alac: ['-c:a', 'alac'],
};
const encoder = (table, name) => table[name] ?? (() => { throw new Error(`Unknown codec ${name}`); })();

// Video `seconds` long at `rate`, solid `color`, with an optional sine track.
// options: { vcodec: 'h264'|'hevc'|'vp9', pix: 'yuv420p'…, acodec, size, rate,
//   seconds, color, vfr (drop 2 of every 5 frames: variable frame rate),
//   rotate (display-matrix degrees), extra: [...output args] }
export async function synthVideo(file, { vcodec = 'h264', pix = 'yuv420p', acodec = null, size = '320x240', rate = 30, seconds = 2,
  color = 'red', vfr = false, rotate = null, extra = [] } = {}) {
  const inputs = ['-f', 'lavfi', '-i', `color=c=${color}:s=${size}:r=${rate}:d=${seconds}`];
  if (acodec) inputs.push('-f', 'lavfi', '-i', `sine=frequency=440:sample_rate=48000:duration=${seconds}`);
  const audio = acodec ? ['-map', '1:a', ...encoder(AUDIO, acodec)] : [];
  const target = rotate === null ? file : `${file}.unrotated${file.slice(file.lastIndexOf('.'))}`;
  const variable = vfr ? ['-vf', 'select=lt(mod(n\\,5)\\,3)', '-fps_mode', 'vfr'] : [];
  await run(mediaTool('ffmpeg'), ['-v', 'error', '-y', ...inputs, '-map', '0:v', ...variable, ...encoder(VIDEO, vcodec), '-pix_fmt', pix, ...audio,
    ...extra, '-t', String(seconds), target], { timeout: 120000 });
  if (rotate !== null) {
    await run(mediaTool('ffmpeg'), ['-v', 'error', '-y', '-display_rotation', String(rotate), '-i', target, '-map', '0', '-c', 'copy', file]);
    await fs.rm(target);
  }
  return file;
}

// Audio-only sine `seconds` long.
export async function synthAudio(file, { acodec = 'aac', seconds = 2, extra = [] } = {}) {
  await run(mediaTool('ffmpeg'), ['-v', 'error', '-y', '-f', 'lavfi', '-i', `sine=frequency=440:sample_rate=48000:duration=${seconds}`,
    ...encoder(AUDIO, acodec), ...extra, file], { timeout: 60000 });
  return file;
}

// Mean RGB of the centre quarter of decoded frame `n` of `file` (select=eq(n,N)).
export async function frameColor(file, n = 0) {
  const { stdout } = await run(mediaTool('ffmpeg'), ['-v', 'error', '-i', file, '-vf', `select=eq(n\\,${n}),crop=iw/2:ih/2,scale=16:16`, '-frames:v', '1',
    '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], { encoding: 'buffer', maxBuffer: 1024 * 1024 });
  const sum = [0, 0, 0];
  for (let i = 0; i < stdout.length; i++) sum[i % 3] += stdout[i];
  return sum.map(v => v / (stdout.length / 3));
}

// Mean volume (dB) of the first audio stream; -Infinity when silent or absent.
export async function meanVolume(file) {
  const { stderr } = await run(mediaTool('ffmpeg'), ['-v', 'info', '-nostats', '-i', file, '-map', '0:a:0?', '-af', 'volumedetect', '-f', 'null', '-'],
    { maxBuffer: 4 * 1024 * 1024 });
  const m = /mean_volume:\s*(-?[\d.]+|-inf) dB/.exec(stderr);
  return m && m[1] !== '-inf' ? Number(m[1]) : -Infinity;
}
