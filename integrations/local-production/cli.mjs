import * as fs from 'node:fs/promises';
import { createProject, editProject, readProject } from './project.mjs';
import { renderProject } from './render.mjs';

// The upstream capture layer still emits console.log diagnostics. In this
// dedicated CLI process reserve stdout for exactly one machine-readable result.
console.log = console.info = (...args) => console.error(...args);

const help = `Creative Craft local production (optional, local media only)
  node cli.mjs create PROJECT SPEC.json
  node cli.mjs read PROJECT [REVISION]
  node cli.mjs edit PROJECT EXPECTED_REVISION OPERATIONS.json
  node cli.mjs preview PROJECT NEW_OUTPUT_DIR [REVISION]
  node cli.mjs render PROJECT NEW_OUTPUT_DIR [REVISION]
Output directories and projects must be new. Media paths in SPEC are relative to cwd.
No natural-language planner, model calls or DataHub integration is included.`;
const [command, root, arg, extra] = process.argv.slice(2);
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
  else if (command === 'edit' && root && arg && extra) result = await editProject(root, rev(arg), await json(extra));
  else if (['preview', 'render'].includes(command) && root && arg) {
    const controller = new AbortController();
    process.once('SIGINT', () => controller.abort());
    process.once('SIGTERM', () => controller.abort());
    result = await renderProject(root, arg, { revision: extra ? rev(extra) : undefined, preview: command === 'preview', signal: controller.signal,
      onProgress: event => process.stderr.write(JSON.stringify(event) + '\n') });
  } else throw new Error(help);
  if (result) process.stdout.write(JSON.stringify(result, null, 2) + '\n');
} catch (error) { console.error(JSON.stringify({ status: 'failed', error: error.message })); process.exitCode = 1; }
