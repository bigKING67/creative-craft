import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withRenderLock } from '../render.mjs';

const tick = ms => new Promise(resolve => setTimeout(resolve, ms));

test('renders in one process run one at a time, in call order', async () => {
  const events = [];
  const job = (name, ms) => withRenderLock(async () => { events.push(`start ${name}`); await tick(ms); events.push(`end ${name}`); return name; });
  assert.deepEqual(await Promise.all([job('a', 30), job('b', 5), job('c', 1)]), ['a', 'b', 'c']);
  assert.deepEqual(events, ['start a', 'end a', 'start b', 'end b', 'start c', 'end c']);
});

test('a failing render does not block later renders', async () => {
  await assert.rejects(withRenderLock(async () => { throw new Error('boom'); }), /boom/);
  assert.equal(await withRenderLock(async () => 'next'), 'next');
});
