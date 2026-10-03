// Render- and QA-time re-check of asset frame_rate (source frame alignment).
// frame_rate is recorded at import; a project imported by 0.6.0 can hold it on
// a source whose video does not start at media time 0 (the earliest stream
// start, e.g. an MKV/WebM with a negative audio start), where the truncation
// correction would aim at the wrong frame grid. Before compiling, every asset
// with frame_rate is probed again (mediaZeroProblem, the import rule); a
// failing asset gets no correction (its items keep the written in-point, the
// renderer behaviour) and the result is recorded. The project files are never
// rewritten.
import path from 'node:path';
import { digest, ffprobeJson, safePath } from './project.mjs';
import { compiledView, mediaZeroProblem } from './source-frames.mjs';

// mediaZeroProblem per content address (asset.sha256): the same bytes give the
// same answer, so each source is probed once per process. Only bytes whose
// digest matched are cached; a failed probe is not cached.
const PROBLEMS = new Map();
function problemOf(root, asset) {
  if (!PROBLEMS.has(asset.sha256)) {
    const pending = (async () => {
      const file = await safePath(path.join(root, asset.file));
      if (await digest(file) !== asset.sha256) throw new Error(`Asset changed: ${asset.id}`);
      return mediaZeroProblem(await ffprobeJson(file));
    })();
    PROBLEMS.set(asset.sha256, pending);
    pending.catch(() => PROBLEMS.delete(asset.sha256));
  }
  return PROBLEMS.get(asset.sha256);
}

// { view, frame_alignment } for a v2 document: the compiled view (compiledView)
// without the corrections of stale frame_rate assets, and one entry per asset
// with frame_rate: { asset_id, frame_rate, applied: true } or
// { asset_id, frame_rate, applied: false, reason }. Render receipts record
// frame_alignment; QA computes the same view and reports it with the cut-point
// checks.
export async function frameAlignment(root, doc) {
  const frame_alignment = [];
  for (const asset of doc.assets.filter(a => a.frame_rate)) {
    const reason = await problemOf(root, asset);
    frame_alignment.push({ asset_id: asset.id, frame_rate: asset.frame_rate, applied: !reason, ...(reason ? { reason } : {}) });
  }
  const skip = new Set(frame_alignment.filter(a => !a.applied).map(a => a.asset_id));
  return { view: compiledView(doc, { skip }), frame_alignment };
}
