import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { isV2, resolveCaptions } from './timeline.mjs';

// Versioned renderer resource, not an assertion about the original video's font.
const bundle = new URL('./fonts/', import.meta.url);
const manifest = JSON.parse(await fs.readFile(new URL('manifest.json', bundle), 'utf8'));
export const CAPTION_FONT = Object.freeze({ profile: manifest.profile, sha256: manifest.sha256,
  file: `fonts/${manifest.sha256}.ttf` });
export const FONT_FAMILY = 'CreativeCaptionNotoSCV1';

export function validateCaptionFont(binding) {
  if (!binding || Array.isArray(binding) || Object.keys(binding).length !== 3 ||
      Object.entries(CAPTION_FONT).some(([key, value]) => binding[key] !== value)) {
    throw new Error('Unsupported caption font binding');
  }
}

export function activeCaptions(project) {
  if (isV2(project)) return resolveCaptions(project).map(caption => caption.item);
  return project.clips.flatMap(clip => clip.captions.filter(caption =>
    caption.to > clip.in_seconds && caption.from < clip.in_seconds + clip.frames / project.canvas.fps));
}

async function fontBytes(file) {
  // Callers resolve the project root through safePath. The font directory/file
  // must also be ordinary files, never a link into mutable host font locations.
  if ((await fs.lstat(path.dirname(file))).isSymbolicLink() || !(await fs.lstat(file)).isFile()) {
    throw new Error('Caption font must be a regular file');
  }
  const bytes = await fs.readFile(file);
  if (createHash('sha256').update(bytes).digest('hex') !== CAPTION_FONT.sha256) {
    throw new Error('Caption font hash mismatch');
  }
  return bytes;
}

// This parser only consumes the hash-verified bundled SFNT. Its Unicode format
// 12 cmap covers both BMP and supplementary characters. A fallback glyph or a
// host emoji font must not silently change a caption's appearance.
function glyphRanges(bytes) {
  let cmap;
  for (let index = 0; index < bytes.readUInt16BE(4); index++) {
    const table = 12 + index * 16;
    if (bytes.toString('ascii', table, table + 4) === 'cmap') cmap = bytes.readUInt32BE(table + 8);
  }
  if (cmap === undefined) throw new Error('Caption font cmap missing');
  for (let index = 0; index < bytes.readUInt16BE(cmap + 2); index++) {
    const record = cmap + 4 + index * 8;
    const platform = bytes.readUInt16BE(record), encoding = bytes.readUInt16BE(record + 2);
    const offset = cmap + bytes.readUInt32BE(record + 4);
    if ((platform === 0 || (platform === 3 && encoding === 10)) && bytes.readUInt16BE(offset) === 12) {
      return Array.from({ length: bytes.readUInt32BE(offset + 12) }, (_, i) => {
        const group = offset + 16 + i * 12;
        return [bytes.readUInt32BE(group), bytes.readUInt32BE(group + 4), bytes.readUInt32BE(group + 8)];
      });
    }
  }
  throw new Error('Caption font Unicode cmap missing');
}

function checkGlyphs(bytes, project) {
  const ranges = glyphRanges(bytes);
  for (const char of new Set(activeCaptions(project).flatMap(caption => Array.from(caption.text)))) {
    if ('\n\r\t'.includes(char)) continue;
    const code = char.codePointAt(0);
    if (!ranges.some(([start, end, glyph]) => code >= start && code <= end && glyph + code - start > 0)) {
      throw new Error(`Caption font missing glyph U+${code.toString(16).toUpperCase()}`);
    }
  }
}

// Check glyphs against the bundled font and record the binding (no writes).
export async function planCaptionFont(project) {
  if (!activeCaptions(project).length) return false;
  checkGlyphs(await fontBytes(fileURLToPath(new URL(manifest.file, bundle))), project);
  project.caption_font = { ...CAPTION_FONT };
  return true;
}

// Copy the bundled bytes into a project; an existing identical copy is reused.
export async function installCaptionFont(root) {
  await fs.mkdir(path.join(root, 'fonts'), { recursive: true });
  const target = path.join(root, CAPTION_FONT.file);
  try { await fs.copyFile(fileURLToPath(new URL(manifest.file, bundle)), target, 1); }
  catch (error) { if (error.code !== 'EEXIST') throw error; }
  await fontBytes(target);
}

export async function bindCaptionFont(root, project) {
  if (!activeCaptions(project).length) return;
  const binding = { ...project };
  await planCaptionFont(binding);
  await fs.mkdir(path.join(root, 'fonts'));
  await installCaptionFont(root);
  project.caption_font = binding.caption_font;
}

export async function verifyCaptionFont(root, project) {
  if (!project.caption_font) return; // Legacy projects retain their old rendering contract.
  validateCaptionFont(project.caption_font);
  checkGlyphs(await fontBytes(path.join(root, project.caption_font.file)), project);
}

export async function copyCaptionFont(root, destination, project) {
  if (!project.caption_font) return;
  await fs.mkdir(path.join(destination, 'fonts'));
  await fs.copyFile(path.join(root, project.caption_font.file), path.join(destination, project.caption_font.file), 1);
  await verifyCaptionFont(destination, project);
}

export function captionFontCss(project) {
  if (!project.caption_font) return '';
  return `@font-face{font-family:'${FONT_FAMILY}';src:url('${project.caption_font.file}') format('truetype');font-weight:100 900;font-style:normal;font-display:block}.caption{font-family:'${FONT_FAMILY}';font-synthesis:none}`;
}

export function captionFontReady(project) {
  if (!project.caption_font) return '';
  const weights = [...new Set(activeCaptions(project).map(c => c.style?.weight ?? 600))];
  // Producer's tween interceptor owns __hfTimelinesBuilding, and fonts.ready
  // resolves even on font failure. Use its explicit async build registry.
  // Producer 0.8.53 treated rejected build promises as settled (gate re-verified
  // on 0.8.108 by tests/font-render.integration.mjs): on error keep
  // this readiness entry pending so its bounded readiness timeout fails the
  // job. The rejection remains observable through __captionFontReady.
  return `window.__captionFontLoaded=false;
window.__captionFontReady=Promise.all(${JSON.stringify(weights)}.map(async weight=>{
  const faces=await document.fonts.load(weight+' 32px "${FONT_FAMILY}"','字幕');
  if(faces.length!==1||faces[0].status!=='loaded')throw new Error('Caption font load failed');
})).then(()=>{window.__captionFontLoaded=true;});
window.__hf=window.__hf||{};window.__hf.buildReady=window.__hf.buildReady||{};
window.__hf.buildReady.captionFont=window.__captionFontReady.catch(error=>{
  console.error('Caption font load failed',error);return new Promise(()=>{});
});`;
}
