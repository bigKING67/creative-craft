import * as fs from 'node:fs/promises';
import { createProject, editBatch, editProject, readProject } from './project.mjs';
import { renderProject } from './render.mjs';
import { qaRender } from './qa.mjs';
import { parseTranscribeArgs, transcribe } from './asr.mjs';

// The upstream capture layer still emits console.log diagnostics. In this
// dedicated CLI process reserve stdout for exactly one machine-readable result.
console.log = console.info = (...args) => console.error(...args);

const help = `Creative Craft local production (optional, local media only)
  node cli.mjs create PROJECT SPEC.json
  node cli.mjs read PROJECT [REVISION]
  node cli.mjs edit PROJECT BATCH.json [--dry-run]            (edit-document.v2 batch)
  node cli.mjs edit PROJECT EXPECTED_REVISION OPERATIONS.json (legacy local-edit.v1 projects only)
  node cli.mjs preview PROJECT NEW_OUTPUT_DIR [REVISION]
  node cli.mjs render PROJECT NEW_OUTPUT_DIR [REVISION]
  node cli.mjs qa PROJECT RENDER_DIR NEW_QA_DIR
  node cli.mjs transcribe MEDIA NEW_OUT.json [--lang zh] [--model PATH] [--clean auto|on|off]  (local whisper.cpp)
Output, QA directories and projects must be new. Media paths in SPEC/BATCH are relative to cwd.
No natural-language planner, model calls or DataHub integration is included.`;
const [command, root, arg, extra, ...rest] = process.argv.slice(2);
const json = async file => JSON.parse(await fs.readFile(file, 'utf8'));
const rev = value => {
  if (!/^\d+$/.test(value ?? '') || Number(value) < 1) throw new Error('Positive revision required');
  return Number(value);
};
try {
  let result;
  if (!command || command === '--help') { process.stdout.write(help + '\n'); }
  else if (command === 'create' && root && arg) result = await createProject(root, await json(arg));
  else if (command === 'read' && root) result = await readProject(root, arg ? rev(arg) : undefined);
  else if (command === 'edit' && root && /^\d+$/.test(arg ?? '') && extra && !rest.length) result = await editProject(root, rev(arg), await json(extra));
  else if (command === 'edit' && root && arg && (extra === undefined || extra === '--dry-run') && !rest.length) {
    result = await editBatch(root, await json(arg), { dryRun: extra === '--dry-run' });
  } else if (['preview', 'render'].includes(command) && root && arg) {
    const controller = new AbortController();
    process.once('SIGINT', () => controller.abort());
    process.once('SIGTERM', () => controller.abort());
    result = await renderProject(root, arg, { revision: extra ? rev(extra) : undefined, preview: command === 'preview', signal: controller.signal,
      onProgress: event => process.stderr.write(JSON.stringify(event) + '\n') });
  } else if (command === 'transcribe') {
    const { media, output, options } = parseTranscribeArgs(process.argv.slice(3));
    result = await transcribe(media, output, options);
  } else if (command === 'qa' && root && arg && extra && !rest.length) result = await qaRender(root, arg, extra);
  else throw new Error(help);
  if (result) process.stdout.write(JSON.stringify(result, null, 2) + '\n');
} catch (error) { console.error(JSON.stringify({ status: 'failed', error: error.message })); process.exitCode = 1; }
