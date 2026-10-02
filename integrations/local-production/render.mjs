import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { digest, probe, readProject, safePath, verifyAssets, run } from './project.mjs';
import { compose, webVtt } from './composition.mjs';
import { copyCaptionFont } from './caption-font.mjs';

const require = createRequire(import.meta.url);
export async function renderProject(root, destination, { revision, preview = false, onProgress = () => {}, signal } = {}) {
  const project = await readProject(root, revision);
  await verifyAssets(root, project);
  const scale = preview ? Math.min(1, 640 / Math.max(project.canvas.width, project.canvas.height)) : 1;
  const width = Math.max(2, Math.round(project.canvas.width * scale / 2) * 2);
  const height = Math.max(2, Math.round(project.canvas.height * scale / 2) * 2);
  const compiled = compose(project, { width, height });
  destination = await safePath(destination);
  root = await safePath(root);
  if (destination === root || destination.startsWith(root + path.sep)) throw new Error('Render outside the immutable project');
  await fs.mkdir(destination);
  const receipt = { schema_version: 'creative-craft.local-render.v1', status: 'running', project_id: project.project_id,
    revision: project.revision, engine: '@hyperframes/producer', engine_version: '0.8.53', preview,
    started_at: new Date().toISOString(), assets: project.assets.map(({ id, sha256 }) => ({ id, sha256 })),
    inspection: { structure: 'pending', decode: 'pending', visual: 'unverified', listening: 'unverified' } };
  receipt.caption_font = project.caption_font ? { ...project.caption_font, integrity: 'passed',
    glyph_coverage: 'passed', runtime_load: compiled.cues.length ? 'pending' : 'not_required', source_match: 'unverified' } :
    { profile: 'legacy-system-fonts', runtime_load: 'unverified', source_match: 'unverified' };
  const writeReceipt = async () => {
    const temp = path.join(destination, '.receipt.json');
    await fs.writeFile(temp, JSON.stringify(receipt, null, 2) + '\n');
    await fs.rename(temp, path.join(destination, 'receipt.json'));
  };
  await writeReceipt();
  try {
    signal?.throwIfAborted();
    await fs.writeFile(path.join(destination, 'project.json'), JSON.stringify(project, null, 2) + '\n', { flag: 'wx' });
    receipt.project_sha256 = await digest(path.join(destination, 'project.json'));
    await copyCaptionFont(root, destination, project);
    await fs.mkdir(path.join(destination, 'assets'));
    for (const asset of project.assets) {
      const target = path.join(destination, asset.file);
      try { await fs.copyFile(await safePath(path.join(root, asset.file)), target, 1); }
      catch (error) { if (error.code !== 'EEXIST') throw error; }
      if (await digest(target) !== asset.sha256) throw new Error('Asset changed while preparing render');
    }
    await fs.copyFile(require.resolve('gsap/dist/gsap.min.js'), path.join(destination, 'gsap.min.js'), 1);
    await fs.writeFile(path.join(destination, 'index.html'), compiled.html, { flag: 'wx' });
    receipt.composition_sha256 = await digest(path.join(destination, 'index.html'));
    await fs.writeFile(path.join(destination, 'captions.vtt'), webVtt(compiled.cues), { flag: 'wx' });
    const { createRenderJob, executeRenderJob } = await import('@hyperframes/producer');
    const job = createRenderJob({ fps: project.canvas.fps, quality: preview ? 'draft' : 'standard',
      format: 'mp4', workers: 1, useGpu: false, hdrMode: 'force-sdr', strictness: 'strict' });
    const output = path.join(destination, 'video.mp4');
    await executeRenderJob(job, destination, output, (state, message) => onProgress({ status: state.status, progress: state.progress, message }), signal);
    if (job.status !== 'complete' || job.warnings.length) throw new Error(`Unqualified render outcome: ${job.status}`);
    if (project.caption_font && compiled.cues.length) receipt.caption_font.runtime_load = 'passed';
    const media = await probe(output);
    const expectsAudio = project.clips.some(c => c.volume > 0 && project.assets.find(a => a.id === c.asset_id)?.audio) ||
      project.audio.some(a => a.volume > 0 && a.start_frame < compiled.frames);
    if (!media.video || media.width !== width || media.height !== height || media.audio !== expectsAudio ||
        Math.abs(media.duration - compiled.duration) > Math.max(0.1, 2 / project.canvas.fps)) throw new Error('Output media does not match the project');
    receipt.inspection.structure = 'passed';
    await run(process.env.CREATIVE_FFMPEG || 'ffmpeg', ['-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'], { timeout: 180000, maxBuffer: 1024 * 1024 });
    receipt.inspection.decode = 'passed';
    receipt.output = { file: 'video.mp4', sha256: await digest(output), ...media };
    receipt.status = 'completed';
    return receipt;
  } catch (error) {
    receipt.status = signal?.aborted ? 'cancelled' : 'failed';
    receipt.error = error.message;
    throw error;
  } finally {
    receipt.finished_at = new Date().toISOString();
    await writeReceipt();
  }
}
