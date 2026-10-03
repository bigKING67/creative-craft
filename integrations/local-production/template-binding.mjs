import * as fs from 'node:fs/promises';
import path from 'node:path';
import { writeOnce } from './content-store.mjs';
import { parseTemplate, runtimeTemplate, templateSha256 } from './templates.mjs';

// Graphic templates pinned to edit revisions (graphic_templates). Like the
// caption font, a binding is content-addressed: the template JSON's raw bytes
// live at templates/<sha256>.json inside the project, and a pinned revision
// renders only from those bytes (hash and template rules re-checked on load).
// Callers pass project roots already resolved through safePath.
const fail = message => { throw new Error(message); };
export const bindingFile = sha256 => `templates/${sha256}.json`;
// Malformed template fields are left to validateV2 to report.
export const usedTemplates = doc => [...new Set((Array.isArray(doc.items) ? doc.items : []).filter(i => i?.kind === 'graphic' && typeof i.template === 'string').map(i => i.template))].sort();

async function boundBytes(root, binding) {
  const file = path.join(root, binding.file);
  try {
    // Never through a link into mutable host locations.
    if ((await fs.lstat(path.dirname(file))).isSymbolicLink() || !(await fs.lstat(file)).isFile()) fail(`Graphic template ${binding.id}: ${binding.file} must be a regular file`);
  } catch (error) {
    if (error.code === 'ENOENT') fail(`Graphic template ${binding.id}: bound file missing (${binding.file})`);
    throw error;
  }
  const bytes = await fs.readFile(file);
  if (templateSha256(bytes) !== binding.sha256) fail(`Graphic template ${binding.id}: bound file hash mismatch (${binding.file})`);
  return bytes;
}

export async function loadBoundTemplate(root, binding) {
  const bytes = await boundBytes(root, binding);
  let template;
  try { template = parseTemplate(binding.id, bytes); }
  catch (error) { fail(`Graphic template ${binding.id} bound to this revision fails template validation: ${error.message}`); }
  if (template.version !== binding.version) fail(`Graphic template ${binding.id}: bound file is version ${template.version}, binding says ${binding.version}`);
  return template;
}

// Loads the bound template set of a pinned revision (bindings already
// shape-checked: id, sha256 and file = templates/<sha256>.json).
export async function loadPinnedTemplates(root, bindings) {
  const templates = new Map();
  for (const binding of bindings) templates.set(binding.id, await loadBoundTemplate(root, binding));
  return templates;
}

// Bindings of a new revision `next` built from `base` (null on create), whose
// loaded template set is `baseTemplates` (reused, not re-read). Every template a
// graphic uses keeps its existing binding; otherwise it reuses the revert
// target's binding (`earlier`: {doc, templates}), else pins the current
// execution-layer bytes. `rebind` forces one template to the execution-layer
// bytes. Bindings no graphic uses are dropped. Returns the files to write
// (nothing is written here), notes for the batch result and the template set of
// `next` for validation.
export function planTemplateBindings(base, next, { baseTemplates = null, rebind = null, earlier = null } = {}) {
  const used = usedTemplates(next), writes = [], notes = [], templates = new Map();
  if (!used.length && !base?.graphic_templates) {
    delete next.graphic_templates;
    return { writes, notes, templates };
  }
  const current = new Map((base?.graphic_templates ?? []).map(b => [b.id, b]));
  const previous = new Map((earlier?.doc.graphic_templates ?? []).map(b => [b.id, b]));
  const bindings = [];
  for (const id of used) {
    let binding = id === rebind ? null : current.get(id), template = binding && baseTemplates?.get(id);
    if (!binding && previous.has(id)) [binding, template] = [previous.get(id), earlier.templates?.get(id)];
    if (binding) template ?? fail(`Graphic template ${id}: the bound template set is not loaded`);
    else {
      const runtime = runtimeTemplate(id);
      binding = { id, version: runtime.template.version, sha256: runtime.sha256, file: bindingFile(runtime.sha256) };
      template = runtime.template;
      writes.push({ binding, bytes: runtime.bytes }); // One per template id; ids are part of the bytes.
    }
    templates.set(id, template);
    bindings.push({ ...binding });
  }
  next.graphic_templates = bindings;
  if (base && !base.graphic_templates && used.length) {
    notes.push(`Revision ${base.revision} predates graphic template pinning; this revision binds ${used.join(', ')} to the current execution-layer template bytes`);
  }
  return { writes, notes, templates };
}

// Content-addressed copies; an existing identical file is reused, never replaced.
export async function installTemplates(root, writes) {
  if (!writes.length) return;
  const dir = path.join(root, 'templates');
  await fs.mkdir(dir, { recursive: true });
  if (!(await fs.lstat(dir)).isDirectory()) fail('Project templates/ must be a directory');
  for (const { binding, bytes } of writes) {
    await writeOnce(path.join(root, binding.file), { bytes }, { expected: binding.sha256, mismatch: `Graphic template ${binding.id} changed while binding` });
    await boundBytes(root, binding); // Regular file, digest of what is now on disk.
  }
}

// Render directories carry the bound bytes so a render replays independently.
export async function copyBoundTemplates(root, destination, doc) {
  if (!doc.graphic_templates?.length) return;
  await fs.mkdir(path.join(destination, 'templates'));
  for (const binding of doc.graphic_templates) {
    await fs.copyFile(path.join(root, binding.file), path.join(destination, binding.file), fs.constants.COPYFILE_EXCL);
    await loadBoundTemplate(destination, binding);
  }
}
