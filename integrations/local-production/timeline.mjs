// Pure EditDocument v2 timeline math shared by validation, font binding,
// composition and QA. No I/O and no imports, so every layer can depend on it.
export const isV2 = doc => Array.isArray(doc?.items);
export const round9 = value => Math.round(value * 1e9) / 1e9;
// P2 speed: output frames play `speed` seconds of source per output second.
export const speedOf = item => item.speed ?? 1;
export const sourceSeconds = (item, fps) => item.frames / fps * speedOf(item);

// Linked captions store source time only. Their output window is the
// intersection of the link range with the media item's current source window,
// mapped through the item's speed to its output position. Null when nothing is visible.
export function captionWindow(doc, caption, byId = new Map(doc.items.map(i => [i.id, i]))) {
  const fps = doc.canvas.fps;
  if (!caption.link) return { start: caption.start_frame / fps, end: (caption.start_frame + caption.frames) / fps };
  const media = byId.get(caption.link.item_id);
  if (!media || media.kind !== 'media') return null;
  const sourceIn = media.source_in_seconds, speed = speedOf(media);
  const from = Math.max(caption.link.source_from, sourceIn), to = Math.min(caption.link.source_to, sourceIn + sourceSeconds(media, fps));
  if (to <= from) return null;
  const output = source => media.start_frame / fps + (source - sourceIn) / speed;
  return { start: output(from), end: output(to) };
}

// Visible captions in document order with their resolved output seconds.
export function resolveCaptions(doc) {
  const byId = new Map(doc.items.map(i => [i.id, i]));
  return doc.items.filter(i => i.kind === 'caption').flatMap(item => {
    const window = captionWindow(doc, item, byId);
    return window ? [{ item, ...window }] : [];
  });
}

// Output length = furthest end of any media/graphic item or free (unlinked) caption.
export function outputFrames(doc) {
  return doc.items.reduce((max, i) => i.kind === 'media' || !i.link ? Math.max(max, i.start_frame + i.frames) : max, 0);
}

export const trackOf = (doc, item) => doc.tracks.find(t => t.id === item.track_id);

// Media that the renderer must emit as sound (video items with audio, audio items).
export function audibleItems(doc) {
  const assets = new Map(doc.assets.map(a => [a.id, a]));
  return doc.items.filter(i => i.kind === 'media' && i.volume > 0 && assets.get(i.asset_id)?.audio);
}
