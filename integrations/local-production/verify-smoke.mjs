import * as fs from 'node:fs/promises';
import path from 'node:path';
import { run } from './project.mjs';

// Signal-level checks complement (and do not replace) human playback/listening.
const ffmpeg = () => process.env.CREATIVE_FFMPEG || 'ffmpeg';
export const frameAt = async (file, time, filter) => (await run(ffmpeg(), ['-v', 'error', '-ss', String(time), '-i', file,
  '-vf', filter, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'], { encoding: 'buffer', maxBuffer: 1024 * 1024 })).stdout;
export const pcmAt = async (file, time) => (await run(ffmpeg(), ['-v', 'error', '-ss', String(time), '-i', file,
  '-t', '0.125', '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', 'pipe:1'], { encoding: 'buffer' })).stdout;
export function mae(actual, expected) {
  if (!actual.length || expected.length !== actual.length) throw new Error('Invalid decoded frame size');
  return actual.reduce((sum, value, i) => sum + Math.abs(value - expected[i]), 0) / actual.length;
}
export function tonePower(pcm, hz) {
  let re = 0, im = 0;
  for (let i = 0; i < pcm.length / 4; i++) {
    const value = pcm.readFloatLE(i * 4), phase = 2 * Math.PI * hz * i / 8000;
    re += value * Math.cos(phase); im += value * Math.sin(phase);
  }
  return re * re + im * im;
}

export async function verifySmoke(base) {
  const samples = [
    ['talking-head-preview', 0.25, 0.25, 440], ['talking-head-preview', 1.25, 3.25, 880],
    ['brand-export', 0.25, 3.25, 880], ['brand-export', 1.25, 0.25, 440],
    ['commerce-export', 0.25, 4.25, 880], ['commerce-export', 0.75, 0.25, 440],
  ];
  const top = 'crop=iw:ih/2:0:0,scale=64:18';
  const results = [];
  for (const [name, time, sourceTime, frequency] of samples) {
    const file = path.join(base, name, 'video.mp4');
    const actual = await frameAt(file, time, top), expected = await frameAt(path.join(base, 'source.mp4'), sourceTime, top);
    if (actual.length !== 3456) throw new Error('Invalid decoded frame size');
    const picture = mae(actual, expected);
    if (picture > 18) throw new Error(`${name}@${time}: picture does not match source ${sourceTime} (MAE ${picture})`);
    const pcm = await pcmAt(file, time);
    const wanted = tonePower(pcm, frequency), other = tonePower(pcm, frequency === 440 ? 880 : 440);
    if (wanted < 1 || wanted < other * 10) throw new Error(`${name}@${time}: wrong/silent audio source`);
    results.push({ name, time, source_time: sourceTime, picture_mae: picture, tone_hz: frequency, signal: 'passed' });
  }
  await fs.writeFile(path.join(base, 'signal-checks.json'), JSON.stringify({ checks: results, human_listening: 'unverified' }, null, 2));
  return results;
}

// v2 multi-track export: main picture outside the B-roll box, B-roll inside it
// (z order + transform), and the music bed mixed with the main track's tone.
export async function verifyMultitrack(base, name) {
  const file = path.join(base, name, 'video.mp4'), source = path.join(base, 'source.mp4'), broll = path.join(base, 'broll.mp4');
  const box = 'crop=512:288:704:36,scale=64:36', left = 'crop=600:260:0:300,scale=60:26', sourceLeft = 'crop=300:130:0:150,scale=60:26';
  const checks = [];
  const compare = async (label, time, filter, reference, referenceTime, referenceFilter, limit = 18) => {
    const value = mae(await frameAt(file, time, filter), await frameAt(reference, referenceTime, referenceFilter));
    checks.push({ label, time, mae: value });
    if (value > limit) throw new Error(`${name}@${time}: ${label} (MAE ${value})`);
  };
  await compare('main picture before B-roll', 0.25, left, source, 0.25, sourceLeft);
  await compare('B-roll inside its transform box', 1.0, box, broll, 0.5, 'scale=64:36');
  await compare('main picture beside B-roll', 1.0, left, source, 1.0, sourceLeft);
  const outside = mae(await frameAt(file, 0.25, box), await frameAt(broll, 0.5, 'scale=64:36'));
  if (outside < 30) throw new Error(`${name}: B-roll box visible before its start (MAE ${outside})`);
  checks.push({ label: 'B-roll absent before start', time: 0.25, mae: outside });
  for (const [time, main] of [[0.25, 440], [2.25, 880]]) {
    const pcm = await pcmAt(file, time);
    const music = tonePower(pcm, 660), dialogue = tonePower(pcm, main), wrong = tonePower(pcm, main === 440 ? 880 : 440);
    if (music < 1 || dialogue < 1 || dialogue < wrong * 10) throw new Error(`${name}@${time}: expected ${main} Hz main tone and 660 Hz music bed`);
    checks.push({ label: 'main tone + music bed', time, main_hz: main, music_power: music, dialogue_power: dialogue });
  }
  return checks;
}
