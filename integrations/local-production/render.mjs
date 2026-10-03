import * as fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { digest, probe, readProject, safePath, verifyAssets, run } from './project.mjs';
import { compose, webVtt } from './composition.mjs';
import { copyCaptionFont } from './caption-font.mjs';
import { copyBoundTemplates } from './template-binding.mjs';
import { audibleItems, isV2 } from './timeline.mjs';
import { templateProvenance } from './templates.mjs';
import { mediaTool } from './media-analysis.mjs';

const require = createRequire(import.meta.url);
const packageVersion = async name => JSON.parse(await fs.readFile(new URL(`./node_modules/${name}/package.json`, import.meta.url), 'utf8')).version;
export const revisionFile = (root, revision) => path.join(root, 'revisions', `${String(revision).padStart(6, '0')}.json`);

// Preview: longest edge at most 640, even dimensions. Export: project canvas.
export function outputSize(canvas, preview) {
  const scale = preview ? Math.min(1, 640 / Math.max(canvas.width, canvas.height)) : 1;
  return { width: Math.max(2, Math.round(canvas.width * scale / 2) * 2), height: Math.max(2, Math.round(canvas.height * scale / 2) * 2) };
}

export function expectsAudio(project, frames) {
  if (isV2(project)) return audibleItems(project).length > 0;
  return project.clips.some(c => c.volume > 0 && project.assets.find(a => a.id === c.asset_id)?.audio) ||
    project.audio.some(a => a.volume > 0 && a.start_frame < frames);
}

// HyperFrames lint gate: any error-severity finding blocks the render.
export async function lintComposition(html) {
  const { lintHyperframeHtml, shouldBlockRender } = await import('@hyperframes/lint');
  const result = await lintHyperframeHtml(html, { filePath: 'index.html' });
  return { engine: '@hyperframes/lint', version: await packageVersion('@hyperframes/lint'), ok: result.ok,
    error_count: result.errorCount, warning_count: result.warningCount, info_count: result.infoCount,
    blocked: shouldBlockRender(true, false, result.errorCount, result.warningCount),
    findings: result.findings.map(({ code, severity, message, elementId }) => ({ code, severity, message, ...(elementId ? { element_id: elementId } : {}) })) };
}

export async function renderProject(root, destination, { revision, preview = false, onProgress = () => {}, signal } = {}) {
  const project = await readProject(root, revision);
  await verifyAssets(root, project);
  const { width, height } = outputSize(project.canvas, preview);
  const compiled = compose(project, { width, height });
  destination = await safePath(destination);
  root = await safePath(root);
  if (destination === root || destination.startsWith(root + path.sep)) throw new Error('Render outside the immutable project');
  await fs.mkdir(destination);
  const receipt = { schema_version: 'creative-craft.local-render.v1', status: 'running', project_id: project.project_id,
    revision: project.revision, document_schema: project.schema_version, revision_sha256: await digest(revisionFile(root, project.revision)),
    engine: '@hyperframes/producer', engine_version: await packageVersion('@hyperframes/producer'), preview,
    started_at: new Date().toISOString(), assets: project.assets.map(({ id, sha256 }) => ({ id, sha256 })),
    inspection: { structure: 'pending', decode: 'pending', visual: 'unverified', listening: 'unverified' } };
  receipt.caption_font = project.caption_font ? { ...project.caption_font, integrity: 'passed',
    glyph_coverage: 'passed', runtime_load: compiled.cues.length || compiled.graphics ? 'pending' : 'not_required', source_match: 'unverified' } :
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
    await copyBoundTemplates(root, destination, project); // Pinned template bytes travel with the render.
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
    receipt.templates = isV2(project) ? templateProvenance(project) : [];
    await fs.writeFile(path.join(destination, 'captions.vtt'), webVtt(compiled.cues), { flag: 'wx' });
    receipt.lint = await lintComposition(compiled.html);
    if (receipt.lint.blocked) throw new Error(`HyperFrames lint blocked render: ${receipt.lint.findings.filter(f => f.severity === 'error').map(f => f.code).join(', ')}`);
    signal?.throwIfAborted();
    const { createRenderJob, executeRenderJob } = await import('@hyperframes/producer');
    const job = createRenderJob({ fps: project.canvas.fps, quality: preview ? 'draft' : 'standard',
      format: 'mp4', workers: 1, useGpu: false, hdrMode: 'force-sdr', strictness: 'strict' });
    const output = path.join(destination, 'video.mp4');
    await executeRenderJob(job, destination, output, (state, message) => onProgress({ status: state.status, progress: state.progress, message }), signal);
    if (job.status !== 'complete' || job.warnings.length) throw new Error(`Unqualified render outcome: ${job.status}`);
    if (project.caption_font && (compiled.cues.length || compiled.graphics)) receipt.caption_font.runtime_load = 'passed';
    // HyperFrames' AAC true-peak limiter lowers the whole mix when it would pass
    // -1 dBTP and reports the attenuation on the job (absent = not engaged).
    if (expectsAudio(project, compiled.frames)) {
      const lowered = Number.isFinite(job.audioLoweredDb) ? job.audioLoweredDb : 0;
      receipt.audio_limiter = { ceiling_dbtp: -1, engaged: lowered > 0, audio_lowered_db: lowered, source: 'RenderJob.audioLoweredDb' };
    }
    const media = await probe(output);
    if (!media.video || media.width !== width || media.height !== height || media.audio !== expectsAudio(project, compiled.frames) ||
        Math.abs(media.duration - compiled.duration) > Math.max(0.1, 2 / project.canvas.fps)) throw new Error('Output media does not match the project');
    receipt.inspection.structure = 'passed';
    await run(mediaTool('ffmpeg'), ['-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'], { timeout: 180000, maxBuffer: 1024 * 1024 });
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
