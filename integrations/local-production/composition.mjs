import { validate } from './project.mjs';
import { validateV2 } from './edit-document.mjs';
import { isV2, resolveCaptions } from './timeline.mjs';
import { captionFontCss, captionFontReady } from './caption-font.mjs';

const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const seconds = value => String(Math.round(value * 1e9) / 1e9);
// Half-open intervals must include the frame at their start, exclude the frame
// at their end. Bias serialized edges by 1 ns to absorb floating-point error;
// never round an edge above the renderer's exact frame / fps sample time.
// This is far below one frame and does not change source-media seek positions.
const timelineTiming = (start, end) => {
  const from = Math.max(0, start - 1e-9);
  const to = Math.max(0, end - 1e-9);
  return `data-start="${from}" data-duration="${to - from}"`;
};
const captionStyle = (style, height) => style ? `top:${seconds(style.centerY * 100)}%;bottom:auto;transform:translateY(-50%);font-size:${seconds(height * style.fontHeight)}px;font-weight:${style.weight};line-height:1.1;color:${style.color};-webkit-text-stroke:${seconds(height * style.strokeWidth)}px #222222;paint-order:stroke fill;text-shadow:0 1px 1px #222222;background:transparent;padding:0;border-radius:0` : '';

export function compose(project, canvas = project.canvas) {
  if (isV2(project)) return composeV2(project, canvas);
  const { duration, frames } = validate(project);
  const { width, height } = canvas;
  const { fps } = project.canvas;
  const assets = new Map(project.assets.map(a => [a.id, a]));
  const elements = [], cues = [];
  const timing = (start, length, source = 0) => `${timelineTiming(start, start + length)} data-media-start="${source}"`;
  let cursor = 0;
  project.clips.forEach((clip, index) => {
    const start = cursor / fps, length = clip.frames / fps;
    const asset = assets.get(clip.asset_id);
    elements.push(`<video id="picture-${index}" src="${asset.file}" ${timing(start, length, clip.in_seconds)} data-track-index="0" muted playsinline style="object-fit:${clip.fit}"></video>`);
    if (asset.audio && clip.volume > 0) elements.push(`<audio id="sound-${index}" src="${asset.file}" ${timing(start, length, clip.in_seconds)} data-track-index="10" data-volume="${clip.volume}"></audio>`);
    clip.captions.forEach(caption => {
      const from = Math.max(clip.in_seconds, caption.from);
      const to = Math.min(clip.in_seconds + length, caption.to);
      if (to <= from) return;
      const cue = { start: start + from - clip.in_seconds, end: start + to - clip.in_seconds, text: caption.text };
      const cueId = `caption-${cues.length}`;
      const matched = caption.style ? ` style="${captionStyle(caption.style, height)}"` : '';
      elements.push(`<div id="${cueId}" class="caption"${matched} ${timelineTiming(cue.start, cue.end)} data-track-index="20">${escape(cue.text)}</div>`);
      cues.push(cue);
    });
    cursor += clip.frames;
  });
  project.audio.forEach((track, index) => {
    const length = Math.min(track.frames, frames - track.start_frame) / fps;
    if (length <= 0 || track.volume === 0) return;
    elements.push(`<audio id="bed-${index}" src="${assets.get(track.asset_id).file}" ${timing(track.start_frame / fps, length, track.in_seconds)} data-track-index="${30 + index}" data-volume="${track.volume}"></audio>`);
  });
  return { html: page(project, width, height, duration, elements), cues, duration, frames };
}

// EditDocument v2: tracks are layered in array order (later = above). Each
// track gets its own data-track-index lane (video n, sound 100+n, captions
// 200+n) and video/caption elements an explicit z-index; captions sit above
// every picture (captions carry class "clip" for HyperFrames lint/Studio; the
// render runtime does not select on it). transform x/y is the item centre as a fraction of the canvas,
// scale the fraction of the canvas box the item occupies.
function composeV2(doc, canvas) {
  const { duration, frames } = validateV2(doc);
  const { width, height } = canvas;
  const { fps } = doc.canvas;
  const assets = new Map(doc.assets.map(a => [a.id, a]));
  const lanes = new Map(doc.tracks.map((t, i) => [t.id, i]));
  const kinds = new Map(doc.tracks.map(t => [t.id, t.kind]));
  const byLane = (a, b) => lanes.get(a.track_id) - lanes.get(b.track_id);
  const timing = item => `${timelineTiming(item.start_frame / fps, (item.start_frame + item.frames) / fps)} data-media-start="${item.source_in_seconds}"`;
  const percent = v => `${seconds(v * 100)}%`;
  const elements = [];
  for (const item of doc.items.filter(i => i.kind === 'media').sort(byLane)) {
    const lane = lanes.get(item.track_id), asset = assets.get(item.asset_id);
    if (kinds.get(item.track_id) === 'video') {
      const style = [`z-index:${lane + 1}`, `object-fit:${item.fit ?? 'contain'}`];
      if (item.transform) {
        const { x, y, scale } = item.transform;
        style.push(`left:${percent(x - scale / 2)}`, `top:${percent(y - scale / 2)}`, 'right:auto', 'bottom:auto', `width:${percent(scale)}`, `height:${percent(scale)}`);
      }
      if ('opacity' in item && item.opacity !== 1) style.push(`opacity:${item.opacity}`);
      elements.push(`<video id="v-${item.id}" src="${asset.file}" ${timing(item)} data-track-index="${lane}" muted playsinline style="${style.join(';')}"></video>`);
    }
    if (asset.audio && item.volume > 0) elements.push(`<audio id="a-${item.id}" src="${asset.file}" ${timing(item)} data-track-index="${100 + lane}" data-volume="${item.volume}"></audio>`);
  }
  const cues = [];
  for (const { item, start, end } of resolveCaptions(doc).sort((a, b) => byLane(a.item, b.item))) {
    const lane = lanes.get(item.track_id);
    elements.push(`<div id="c-${item.id}" class="clip caption" style="z-index:${200 + lane};${captionStyle(item.style, height)}" ${timelineTiming(start, end)} data-track-index="${200 + lane}">${escape(item.text)}</div>`);
    cues.push({ start, end, text: item.text });
  }
  cues.sort((a, b) => a.start - b.start);
  return { html: page(doc, width, height, duration, elements), cues, duration, frames };
}

function page(project, width, height, duration, elements) {
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>${escape(project.title)}</title>
<script src="gsap.min.js"></script>
<style>html,body{margin:0;background:#000;overflow:hidden}#main{position:relative;width:${width}px;height:${height}px;background:#000}video{position:absolute;inset:0;width:100%;height:100%}.caption{position:absolute;left:7%;right:7%;bottom:8%;text-align:center;color:#fff;white-space:pre-wrap;font:600 ${Math.round(height * 0.052)}px/1.35 'PingFang SC','Noto Sans CJK SC',sans-serif;text-shadow:0 2px 4px #000;background:rgba(0,0,0,.65);padding:8px;border-radius:6px}</style></head>
<body><style>${captionFontCss(project)}</style><div id="main" data-composition-id="main" data-width="${width}" data-height="${height}" data-duration="${seconds(duration)}">${elements.join('\n')}</div>
<script>${captionFontReady(project)}
window.__timelines=window.__timelines||{};const tl=gsap.timeline({paused:true});tl.to({}, {duration:${seconds(duration)}});window.__timelines.main=tl;</script></body></html>`;
}

export function webVtt(cues) {
  const stamp = s => {
    const ms = Math.round(s * 1000);
    return `${String(Math.floor(ms / 3600000)).padStart(2, '0')}:${String(Math.floor(ms / 60000) % 60).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
  };
  return `WEBVTT\n\n${cues.map(c => `${stamp(c.start)} --> ${stamp(c.end)}\n${escape(c.text).replace(/\r?\n\r?\n/g, '\n')}\n`).join('\n')}`;
}
