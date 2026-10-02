import * as fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createProject, editProject, readProject, digest, run } from './project.mjs';
import { renderProject } from './render.mjs';
import { verifySmoke } from './verify-smoke.mjs';

// Self-authored synthetic signals; no customer assets, ASR, TTS or paid APIs.
const here = path.dirname(fileURLToPath(import.meta.url));
const base = path.resolve(process.argv[2] || path.join(here, '../../dist/local-production', new Date().toISOString().replace(/[:.]/g, '-')));
await fs.mkdir(base, { recursive: true });
const ffmpeg = process.env.CREATIVE_FFMPEG || 'ffmpeg';
const source = path.join(base, 'source.mp4');
await run(ffmpeg, ['-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=24:duration=6',
  '-f', 'lavfi', '-i', 'aevalsrc=0.1*sin(2*PI*if(lt(t\\,3)\\,440\\,880)*t):s=48000:d=6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', source]);
const before = await digest(source);
const clip = (id, start, caption) => ({ id, asset_id: 'source', in_seconds: start, frames: 24, volume: 0.7,
  fit: 'contain', captions: [{ from: start, to: start + 1, text: caption }] });
const root = path.join(base, 'project');
await createProject(root, { project_id: 'production-smoke', title: 'Creative Craft 技术样例', canvas: { width: 1280, height: 720, fps: 24 },
  assets: [{ id: 'source', path: source }], clips: [clip('opening', 0, '口播：保留这一句'), clip('detail', 3, '产品：细节画面')], audio: [] });
const outcomes = [];
outcomes.push(await renderProject(root, path.join(base, 'talking-head-preview'), { preview: true, revision: 1 }));
await editProject(root, 1, [{ type: 'reorder', clip_ids: ['detail', 'opening'] },
  { type: 'update_clip', clip_id: 'detail', changes: { captions: [{ from: 3, to: 4, text: '品牌：让细节先说话' }] } }]);
outcomes.push(await renderProject(root, path.join(base, 'brand-export'), { revision: 2 }));
await editProject(root, 2, [{ type: 'update_clip', clip_id: 'detail', changes: { in_seconds: 4, frames: 12,
  captions: [{ from: 4, to: 4.5, text: '电商：换一个开场' }] } }]);
outcomes.push(await renderProject(root, path.join(base, 'commerce-export'), { revision: 3 }));
if ((await readProject(root)).revision !== 3 || before !== await digest(source)) throw new Error('Reopen or input preservation failed');
await verifySmoke(base);
await editProject(root, 3, [{ type: 'update_clip', clip_id: 'opening', changes: { volume: 0 } },
  { type: 'update_clip', clip_id: 'detail', changes: { volume: 0 } }]);
const { stdout } = await run(process.execPath, [path.join(here, 'cli.mjs'), 'render', root, path.join(base, 'silent-export'), '4'],
  { timeout: 180000, maxBuffer: 8 * 1024 * 1024 });
const silent = JSON.parse(stdout); // Also protects stdout from upstream diagnostic contamination.
if (silent.status !== 'completed' || silent.output.audio) throw new Error('Silent CLI export failed');
await editProject(root, 4, [{ type: 'set_audio', audio: [{ id: 'music', asset_id: 'source', in_seconds: 3,
  start_frame: 12, frames: 24, volume: 0.2 }] }]);
const bed = await renderProject(root, path.join(base, 'independent-audio-export'), { revision: 5 });
const pcmAt = async time => (await run(ffmpeg, ['-v', 'error', '-ss', String(time), '-i', path.join(base, 'independent-audio-export/video.mp4'),
  '-t', '0.125', '-vn', '-ac', '1', '-ar', '8000', '-f', 'f32le', 'pipe:1'], { encoding: 'buffer' })).stdout;
const rms = pcm => {
  if (pcm.length < 1000) throw new Error('Missing audio samples');
  let power = 0; for (let i = 0; i < pcm.length; i += 4) power += pcm.readFloatLE(i) ** 2;
  return Math.sqrt(power / (pcm.length / 4));
};
const beforeBed = rms(await pcmAt(0.125)), duringBed = rms(await pcmAt(0.75));
if (beforeBed > 0.001 || duringBed < 0.005) throw new Error('Independent audio placement failed');
await fs.writeFile(path.join(base, 'summary.json'), JSON.stringify({ status: 'passed', fixture: 'synthetic technical scenarios; not real creative evaluation',
  project: root, outputs: [...outcomes, silent, bed], input_preserved: before === await digest(source),
  cli_json: 'passed', independent_audio: { before_rms: beforeBed, during_rms: duringBed }, listening: 'unverified' }, null, 2));
console.log(`SMOKE_ARTIFACTS=${base}`);
