import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { run } from '../project.mjs';
import { ASR_MODEL, TRANSCRIPT_SCHEMA, coverageSeconds, defaultModelPath, needsCleanRetry, parseTranscribeArgs, toPlanEvidence,
  transcribe, verifyModel, whisperVersion } from '../asr.mjs';

// Only synthesized audio is used here; customer media must never be copied into tests.
async function directory(t) {
  const root = await fs.mkdtemp(path.join(await fs.realpath(os.tmpdir()), 'asr-test-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  return root;
}
// Returns a skip reason when the local engine cannot run, otherwise null.
async function engineUnavailable() {
  try { await whisperVersion(); } catch (error) { return `whisper-cli unavailable: ${error.message}`; }
  try { await verifyModel(defaultModelPath()); } catch (error) {
    if (error.code === 'ENOENT') return `ASR model missing at ${defaultModelPath()} (npm run fetch-asr-model)`;
    throw error; // a present but mismatched model is a real failure
  }
  return null;
}
const ffmpeg = (...args) => run(process.env.CREATIVE_FFMPEG || 'ffmpeg', ['-nostdin', '-v', 'error', ...args], { timeout: 60000 });

test('model digest mismatch is rejected, a verified digest is cached and invalidated on change', async t => {
  const dir = await directory(t), file = path.join(dir, 'tiny.bin');
  await fs.writeFile(file, 'hello');
  const good = { file: 'tiny.bin', bytes: 5, sha256: createHash('sha256').update('hello').digest('hex') };
  await assert.rejects(verifyModel(file, { ...good, sha256: '0'.repeat(64) }), /SHA-256 mismatch/);
  await assert.rejects(verifyModel(file, { ...good, bytes: 6 }), /SHA-256 mismatch.*5 bytes/);
  await assert.rejects(verifyModel(path.join(dir, 'other.bin'), good), /Unpinned ASR model/);
  await assert.rejects(verifyModel(path.join(dir, 'missing', 'tiny.bin'), good), { code: 'ENOENT' });
  assert.equal(await verifyModel(file, good), good.sha256);
  assert.ok(JSON.parse(await fs.readFile(`${file}.sha256-verified.json`, 'utf8')).sha256 === good.sha256);
  await fs.writeFile(file, 'jello'); // same size, new content: cache must not vouch for it
  await assert.rejects(verifyModel(file, good), /SHA-256 mismatch/);
});

test('transcribe refuses a mismatched model before touching media or whisper', async t => {
  const dir = await directory(t), model = path.join(dir, ASR_MODEL.file);
  await fs.writeFile(model, 'not a model');
  await assert.rejects(transcribe(path.join(dir, 'absent.wav'), path.join(dir, 'out.json'), { model }), /SHA-256 mismatch/);
  await assert.rejects(fs.access(path.join(dir, 'out.json')));
});

test('coverage merges overlapping sentences and clips to media duration', () => {
  assert.equal(coverageSeconds([{ start: 0, end: 2 }, { start: 1, end: 3 }, { start: 5, end: 9 }], 8), 6);
  assert.equal(coverageSeconds([]), 0);
});

test('toPlanEvidence returns production-plan asr evidence for overlapping sentences', () => {
  const segments = [{ start: 0, end: 2.3, text: '叫啦 叫啦' }, { start: 2.3, end: 5.2, text: ' 已经买了的姐妹们 ' }, { start: 5.2, end: 7.56, text: '对不起了' }];
  assert.deepEqual(toPlanEvidence(segments, 2, 5, 'whisper.cpp large-v3-turbo, clean retry'), [
    { modality: 'asr', start_seconds: 0, end_seconds: 2.3, excerpt: '叫啦 叫啦', raw_score: null, method: 'whisper.cpp large-v3-turbo, clean retry' },
    { modality: 'asr', start_seconds: 2.3, end_seconds: 5.2, excerpt: '已经买了的姐妹们', raw_score: null, method: 'whisper.cpp large-v3-turbo, clean retry' },
  ]);
  assert.deepEqual(toPlanEvidence(segments, 8, 9, 'm'), []);
  assert.throws(() => toPlanEvidence(segments, 3, 3, 'm'), /from < to/);
  assert.throws(() => toPlanEvidence(segments, 0, 1, ''), /method/);
});

test('clean retry triggers only when coverage is under half of a sustained active signal', () => {
  assert.equal(needsCleanRetry(2.28, 26.842), true); // measured: heavy-BGM livestream clip, plain pass
  assert.equal(needsCleanRetry(26.84, 26.842), false);
  assert.equal(needsCleanRetry(1.0, 1.9), false); // too little activity to judge
  assert.equal(needsCleanRetry(0, 0), false);
  assert.equal(needsCleanRetry(3, 6), false);
  assert.equal(needsCleanRetry(2.99, 6), true);
});

test('CLI option parsing', () => {
  assert.deepEqual(parseTranscribeArgs(['a.mp4', 'o.json', '--clean', 'off', '--lang', 'en']),
    { media: 'a.mp4', output: 'o.json', options: { lang: 'en', model: undefined, clean: 'off' } });
  assert.throws(() => parseTranscribeArgs(['a.mp4']), /MEDIA and OUT/);
  assert.throws(() => parseTranscribeArgs(['a.mp4', 'o.json', '--speed', '2']), /Bad transcribe option/);
  assert.throws(() => parseTranscribeArgs(['a.mp4', 'o.json', '--clean']), /Bad transcribe option/);
});

test('speech-free audio produces a well-formed transcript; --clean on records the retry recipe', async t => {
  const reason = await engineUnavailable();
  if (reason) return t.skip(reason);
  const dir = await directory(t), silence = path.join(dir, 'silence.wav'), tone = path.join(dir, 'tone.wav');
  const scratch = path.join(dir, 'tmp'), previousTmp = process.env.TMPDIR;
  await fs.mkdir(scratch);
  process.env.TMPDIR = scratch; // observe that the extracted wav directory is cleaned up
  t.after(() => { if (previousTmp === undefined) delete process.env.TMPDIR; else process.env.TMPDIR = previousTmp; });
  await ffmpeg('-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '6', silence);
  await ffmpeg('-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-af', 'volume=0.3', '-t', '6', tone);

  const quiet = await transcribe(silence, path.join(dir, 'silence.json'), {});
  const doc = JSON.parse(await fs.readFile(path.join(dir, 'silence.json'), 'utf8'));
  assert.equal(doc.schema, TRANSCRIPT_SCHEMA);
  assert.deepEqual(Object.keys(doc.media), ['path_basename', 'sha256', 'duration']);
  assert.equal(doc.media.path_basename, 'silence.wav');
  assert.match(doc.media.sha256, /^[0-9a-f]{64}$/);
  assert.ok(Math.abs(doc.media.duration - 6) < 0.05);
  assert.equal(doc.engine.name, 'whisper.cpp');
  assert.equal(doc.engine.model_sha256, ASR_MODEL.sha256);
  assert.match(doc.engine.binary_version, /^\d+\.\d+/);
  assert.equal(doc.language, 'zh');
  assert.equal(doc.audio_activity.active_seconds, 0);
  assert.equal(doc.attempts.length, 1, 'silent audio must not trigger the clean retry');
  assert.equal(quiet.chosen_attempt, 0);
  assert.ok(Array.isArray(doc.segments));
  for (const s of doc.segments) assert.ok(s.start >= 0 && s.end > s.start && s.end <= doc.media.duration && s.text);
  await assert.rejects(transcribe(silence, path.join(dir, 'silence.json'), {}), /already exists/);

  // A steady tone is energetic but speech-free; whisper may hallucinate text over it,
  // so only the forced clean attempt's recorded parameters are asserted.
  const forced = await transcribe(tone, path.join(dir, 'tone.json'), { clean: 'on' });
  const toneDoc = JSON.parse(await fs.readFile(path.join(dir, 'tone.json'), 'utf8'));
  assert.ok(toneDoc.audio_activity.active_seconds > 5);
  assert.equal(toneDoc.attempts.length, 1);
  assert.equal(forced.chosen_attempt, 0);
  assert.equal(toneDoc.attempts[0].params.preprocess, 'highpass=f=120,lowpass=f=6000,afftdn=nf=-25,dynaudnorm');
  assert.deepEqual(toneDoc.attempts[0].params.whisper_args, ['-mc', '0', '-et', '2.8', '-nth', '0.3']);
  assert.deepEqual(await fs.readdir(scratch), []);
});

test('synthesized Mandarin speech is transcribed with the expected words', async t => {
  const reason = await engineUnavailable();
  if (reason) return t.skip(reason);
  if (process.platform !== 'darwin') return t.skip('macOS say is required for speech synthesis');
  const dir = await directory(t), aiff = path.join(dir, 'speech.aiff'), out = path.join(dir, 'speech.json');
  try { await run('say', ['-v', 'Tingting', '-o', aiff, '今天测试本地转写']); }
  catch (error) { return t.skip(`say -v Tingting unavailable: ${error.message}`); }
  const result = await transcribe(aiff, out, { clean: 'auto' });
  const doc = JSON.parse(await fs.readFile(out, 'utf8'));
  const text = doc.segments.map(s => s.text).join('');
  assert.match(text, /测试/);
  assert.match(text, /转写|转鞋|转谢/);
  assert.equal(result.chosen_attempt, doc.chosen_attempt);
  const evidence = toPlanEvidence(doc.segments, 0, doc.media.duration, 'whisper.cpp large-v3-turbo');
  assert.ok(evidence.length >= 1 && evidence.every(e => e.modality === 'asr' && e.raw_score === null));
});
