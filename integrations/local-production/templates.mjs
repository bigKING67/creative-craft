import { readFileSync, readdirSync } from 'node:fs';

// Graphic templates are versioned execution-layer resources: fixed HTML/CSS in
// this repository plus typed variables. Documents only choose a template id and
// supply primitive values; nothing caller-supplied becomes markup, CSS, a URL or
// a script. Text is HTML-escaped, colours are #rrggbb, booleans become a fixed
// data attribute, numbers a CSS custom property.
export const TEMPLATE_SCHEMA = 'creative-craft.graphic-template.v1';
export const SAFE_MARGIN = 0.05;
const fail = message => { throw new Error(message); };
const VAR_NAME = /^[a-z][a-z0-9_]{0,31}$/;
const COLOR = /^#[0-9a-fA-F]{6}$/;
const FORBIDDEN = /<\s*(script|style|iframe|object|embed|img|link|meta|svg|math|base|form)|\son\w+\s*=|javascript:|url\s*\(|@import|expression\s*\(|\b(src|href|srcset|action)\s*=/i;
export const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const plain = value => value && typeof value === 'object' && !Array.isArray(value);
const exact = (value, allowed, label) => {
  if (!plain(value)) fail(`${label} must be an object`);
  for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(`${label}: unknown field ${key}`);
};
const fraction = v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;

function validateDefinition(name, def) {
  const label = `Graphic template ${name}`;
  exact(def, ['type', 'optional', 'default', 'max_length', 'font_em', 'weight', 'min', 'max'], `${label} var`);
  if (!['string', 'color', 'boolean', 'number'].includes(def.type)) fail(`${label}: unsupported var type ${def.type}`);
  if ('optional' in def && typeof def.optional !== 'boolean') fail(`${label}: optional must be boolean`);
  if (def.type === 'string') {
    if ('default' in def || !Number.isInteger(def.max_length) || def.max_length < 1 || def.max_length > 200 ||
        typeof def.font_em !== 'number' || !(def.font_em > 0) || ![400, 600, 700, 900].includes(def.weight)) fail(`${label}: string vars need max_length 1–200, font_em and weight`);
  } else if ('max_length' in def || 'font_em' in def || 'weight' in def) fail(`${label}: text metrics only apply to strings`);
  if (def.type === 'number' && !(Number.isFinite(def.min) && Number.isFinite(def.max) && def.min <= def.max)) fail(`${label}: number vars need min/max`);
  if (def.type !== 'number' && ('min' in def || 'max' in def)) fail(`${label}: min/max only apply to numbers`);
  if ('default' in def && !def.optional) fail(`${label}: only optional vars take a default`);
  if ('default' in def) checkValue(name, def, def.default, label);
}

function checkValue(name, def, value, label) {
  const ok = def.type === 'string' ? typeof value === 'string' && value.length >= 1 && value.length <= def.max_length
    : def.type === 'color' ? typeof value === 'string' && COLOR.test(value)
      : def.type === 'boolean' ? typeof value === 'boolean'
        : typeof value === 'number' && Number.isFinite(value) && value >= def.min && value <= def.max;
  if (!ok) fail(`${label}: var ${name} must be ${def.type === 'string' ? `a string of 1–${def.max_length} characters` : def.type === 'color' ? 'a #rrggbb colour' : def.type === 'number' ? `a number in ${def.min}–${def.max}` : 'a boolean'}`);
}

// Fails closed at load: a template that could escape its box, the safe area or
// the fixed-markup rule never becomes available.
export function validateTemplate(name, template) {
  exact(template, ['schema_version', 'id', 'version', 'description', 'box', 'vars', 'html', 'css'], `Graphic template ${name}`);
  if (template.schema_version !== TEMPLATE_SCHEMA || template.id !== name || !/^[a-z][a-z0-9-]{0,47}$/.test(name) ||
      !Number.isInteger(template.version) || template.version < 1 || typeof template.description !== 'string') fail(`Invalid graphic template identity: ${name}`);
  exact(template.box, ['left', 'top', 'width', 'height'], `Graphic template ${name} box`);
  const { left, top, width, height } = template.box;
  if (![left, top, width, height].every(fraction) || width <= 0 || height <= 0 || left < SAFE_MARGIN || top < SAFE_MARGIN ||
      left + width > 1 - SAFE_MARGIN + 1e-9 || top + height > 1 - SAFE_MARGIN + 1e-9) fail(`Graphic template ${name} box leaves the 5% safe area`);
  if (!plain(template.vars) || !Object.keys(template.vars).length) fail(`Graphic template ${name} has no vars`);
  for (const [key, def] of Object.entries(template.vars)) {
    if (!VAR_NAME.test(key)) fail(`Graphic template ${name}: invalid var name ${key}`);
    validateDefinition(key, def);
    // Worst case: every character is full-width (1 em). The box is at least
    // 100 × width em wide because 1 em = 1% of the shorter canvas edge.
    if (def.type === 'string' && def.max_length * def.font_em > 100 * width * 0.95) fail(`Graphic template ${name}: ${key} cannot fit its box at max_length`);
  }
  if (typeof template.html !== 'string' || typeof template.css !== 'string' || FORBIDDEN.test(template.html) || FORBIDDEN.test(template.css) ||
      template.css.includes('<')) fail(`Graphic template ${name} contains forbidden markup`);
  const holes = [...template.html.matchAll(/\{\{([^}]*)\}\}/g)].map(m => m[1]);
  const strings = Object.keys(template.vars).filter(k => template.vars[k].type === 'string');
  if (holes.length !== strings.length || holes.some(h => !strings.includes(h)) || new Set(holes).size !== holes.length) fail(`Graphic template ${name}: each string var must appear exactly once in html`);
  // Every CSS rule is scoped to this template's root class.
  for (const rule of template.css.split('}').map(r => r.trim()).filter(Boolean)) {
    const [selectors] = rule.split('{');
    if (!rule.includes('{') || selectors.split(',').some(s => !s.trim().startsWith(`.gfx-${name}`))) fail(`Graphic template ${name}: CSS must be scoped to .gfx-${name}`);
  }
  return template;
}

const directory = new URL('./templates/', import.meta.url);
export const TEMPLATES = new Map(readdirSync(directory).filter(n => n.endsWith('.json')).sort().map(file => {
  const name = file.slice(0, -5);
  return [name, Object.freeze(validateTemplate(name, JSON.parse(readFileSync(new URL(file, directory), 'utf8'))))];
}));

export const getTemplate = name => TEMPLATES.get(name) ?? fail(`Unknown graphic template: ${name}`);

// Node-side semantic check of a graphic item's vars against its template.
export function validateGraphicVars(item) {
  const template = getTemplate(item.template), label = `Graphic item ${item.id}`;
  for (const key of Object.keys(item.vars)) if (!(key in template.vars)) fail(`${label}: template ${template.id} has no var ${key}`);
  for (const [key, def] of Object.entries(template.vars)) {
    if (!(key in item.vars)) { if (!def.optional) fail(`${label}: missing required var ${key}`); continue; }
    checkValue(key, def, item.vars[key], label);
  }
  return template;
}

// Resolved values (defaults applied) for a validated graphic item.
export function graphicValues(item) {
  const template = getTemplate(item.template);
  return Object.fromEntries(Object.entries(template.vars).map(([k, def]) => [k, k in item.vars ? item.vars[k] : def.default]));
}

// Text runs the bound font must cover, with their weights.
export function graphicTexts(item) {
  const template = getTemplate(item.template), values = graphicValues(item);
  return Object.entries(template.vars).filter(([k, d]) => d.type === 'string' && typeof values[k] === 'string')
    .map(([k, d]) => ({ text: values[k], weight: d.weight, font_em: d.font_em, var: k }));
}

// Fixed markup with escaped text. Returns the inner HTML, root attributes and
// inline custom properties; the caller adds timing, id and stacking.
export function renderGraphic(item) {
  const template = getTemplate(item.template), values = graphicValues(item);
  const inner = template.html.replace(/\{\{([a-z][a-z0-9_]*)\}\}/g, (_, key) => values[key] === undefined ? '' : escapeHtml(values[key]));
  const properties = [], attributes = [];
  for (const [key, def] of Object.entries(template.vars)) {
    const value = values[key];
    if (value === undefined) continue;
    if (def.type === 'color' || def.type === 'number') properties.push(`--${key}:${def.type === 'color' ? value.toLowerCase() : String(value)}`);
    if (def.type === 'boolean') attributes.push(`data-${key.replace(/_/g, '-')}="${value ? 'true' : 'false'}"`);
  }
  return { template, inner, properties, attributes };
}
