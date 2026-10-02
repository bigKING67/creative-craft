import * as fs from 'node:fs/promises';
import path from 'node:path';
import { run } from './project.mjs';

// Signal-level checks complement (and do not replace) human playback/listening.
export async function verifySmoke(base) {
  const ffmpeg = process.env.CREATIVE_FFMPEG || 'ffmpeg';
  const samples = [
    ['talking-head-preview', 0.25, 0.25, 440], ['talking-head-preview', 1.25, 3.25, 880],
    ['brand-export', 0.25, 3.25, 880], ['brand-export', 1.25, 0.25, 440],
    ['commerce-export', 0.25, 4.25, 880], ['commerce-export', 0.75, 0.25, 440],
  ];
  const frame = async (file, time) => (await run(ffmpeg, ['-v', 'error', '-ss', String(time), '-i', file,
    '-vf', 'crop=iw:ih/2:0:0,scale=64:18', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], { encoding: 'buffer', maxBuffer: 1024 * 1024 })).stdout;
  const results = [];
  for (const [name, time, sourceTime, frequency] of samples) {
    const file = path.join(base, name, 'video.mp4');
    const actual = await frame(file, time), expected = await frame(path.join(base, 'source.mp4'), sourceTime);
    if (actual.length !== 3456 || expected.length !== actual.length) throw new Error('Invalid decoded frame size');
    const mae = actual.reduce((sum, value, i) => sum + Math.abs(value - expected[i]), 0) / actual.length;
    if (mae > 18) throw new Error(`${name}@${time}: picture does not match source ${sourceTime} (MAE ${mae})`);
    const { stdout: pcm } = await run(ffmpeg, ['-v', 'error', '-ss', String(time), '-i', file,
      '-t', '0.125', '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', 'pipe:1'], { encoding: 'buffer' });
    const power = hz => {
      let re = 0, im = 0;
      for (let i = 0; i < pcm.length / 4; i++) {
        const value = pcm.readFloatLE(i * 4), phase = 2 * Math.PI * hz * i / 8000;
        re += value * Math.cos(phase); im += value * Math.sin(phase);
      }
      return re * re + im * im;
    };
    const wanted = power(frequency), other = power(frequency === 440 ? 880 : 440);
    if (wanted < 1 || wanted < other * 10) throw new Error(`${name}@${time}: wrong/silent audio source`);
    results.push({ name, time, source_time: sourceTime, picture_mae: mae, tone_hz: frequency, signal: 'passed' });
  }
  await fs.writeFile(path.join(base, 'signal-checks.json'), JSON.stringify({ checks: results, human_listening: 'unverified' }, null, 2));
  return results;
}
