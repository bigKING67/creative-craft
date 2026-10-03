// Local speech-to-text with whisper.cpp. Customer audio never leaves the machine:
// ffmpeg extracts 16 kHz mono PCM into a private temp dir, whisper-cli transcribes it
// with a pinned, SHA-256 verified model, and the temp dir is removed afterwards.
// ASR text may contain wrong characters and timestamps are sentence-level; cut points
// derived from it must be confirmed by listening.
import * as fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { digest, ffprobeJson, run } from './project.mjs';

export const TRANSCRIPT_SCHEMA = 'creative-craft.local-transcript.v1';
export const ASR_MODEL = Object.freeze({
  name: 'ggml-large-v3-turbo',
  file: 'ggml-large-v3-turbo.bin',
  source: 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin',
  bytes: 1624555275,
  sha256: '1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69',
});
// Biases whisper toward simplified-Chinese punctuated sentences; only used for zh.
export const ZH_PROMPT = '以下是普通话的句子。';
// Retry recipe for speech buried under loud background music (see README).
export const CLEAN_FILTER = 'highpass=f=120,lowpass=f=6000,afftdn=nf=-25,dynaudnorm';
export const CLEAN_ARGS = Object.freeze(['-mc', '0', '-et', '2.8', '-nth', '0.3']);
// Audio activity = duration minus silencedetect(-35 dB, >= 0.5 s) gaps. The clean retry
// runs when activity >= 2 s and recognised coverage < 50 % of that activity.
export const ACTIVITY = Object.freeze({ noise_db: -35, min_silence_seconds: 0.5, min_active_seconds: 2, retry_ratio: 0.5 });

export const modelDir = () => process.env.CREATIVE_WHISPER_MODEL_DIR || path.join(os.homedir(), '.cache', 'whisper-cpp');
export const defaultModelPath = () => path.join(modelDir(), ASR_MODEL.file);
const whisperBin = () => process.env.CREATIVE_WHISPER || 'whisper-cli';
const ffmpegBin = () => process.env.CREATIVE_FFMPEG || 'ffmpeg';
const round = value => Math.round(value * 1000) / 1000;

// Hashing 1.6 GB takes seconds, so a verified digest is cached next to the model and
// reused only while size, inode and mtime are unchanged. Mismatch always throws.
export async function verifyModel(file, manifest = ASR_MODEL) {
  if (path.basename(file) !== manifest.file) throw new Error(`Unpinned ASR model ${path.basename(file)}; expected ${manifest.file}`);
  const stat = await fs.stat(file).catch(error => {
    if (error.code === 'ENOENT') throw Object.assign(new Error(`ASR model missing: ${file}; run npm run fetch-asr-model`), { code: 'ENOENT' });
    throw error;
  });
  if (!stat.isFile()) throw new Error(`ASR model is not a regular file: ${file}`);
  if (stat.size !== manifest.bytes) throw new Error(`ASR model SHA-256 mismatch: ${file} has ${stat.size} bytes, expected ${manifest.bytes}`);
  const marker = `${file}.sha256-verified.json`, identity = { size: stat.size, ino: stat.ino, mtimeMs: stat.mtimeMs, sha256: manifest.sha256 };
  const cached = await fs.readFile(marker, 'utf8').then(JSON.parse).catch(() => null);
  if (cached && Object.keys(identity).every(key => cached[key] === identity[key])) return manifest.sha256;
  const actual = await digest(file);
  if (actual !== manifest.sha256) throw new Error(`ASR model SHA-256 mismatch: ${file} is ${actual}, expected ${manifest.sha256}`);
  await fs.writeFile(marker, JSON.stringify(identity) + '\n').catch(() => {}); // cache is optional
  return actual;
}

export async function whisperVersion() {
  let output;
  try {
    const { stdout, stderr } = await run(whisperBin(), ['--version'], { timeout: 30000, maxBuffer: 4 * 1024 * 1024 });
    output = stdout + stderr;
  } catch (error) {
    if (error.code === 'ENOENT') throw Object.assign(new Error(`whisper-cli not found (${whisperBin()}); install whisper.cpp or set CREATIVE_WHISPER`), { code: 'ENOENT' });
    throw error;
  }
  const match = /whisper\.cpp version:\s*(\S+)/.exec(output);
  if (!match) throw new Error('Could not read whisper.cpp version');
  return match[1];
}

// Length of the union of [start, end] intervals clipped to [0, duration].
export function coverageSeconds(segments, duration = Infinity) {
  const spans = segments.map(s => [Math.max(0, s.start), Math.min(duration, s.end)]).filter(([a, b]) => b > a).sort((x, y) => x[0] - y[0]);
  let total = 0, cursor = -Infinity;
  for (const [a, b] of spans) {
    if (b <= cursor) continue;
    total += b - Math.max(a, cursor);
    cursor = b;
  }
  return round(total);
}

// Sentences overlapping [from, to] as production-plan evidence. Times are the
// sentence boundaries reported by ASR, not frame-accurate cut points.
export function toPlanEvidence(segments, from, to, method) {
  if (!(Number.isFinite(from) && Number.isFinite(to) && to > from && from >= 0)) throw new Error('toPlanEvidence needs 0 <= from < to');
  if (typeof method !== 'string' || !method.trim()) throw new Error('toPlanEvidence needs a method description');
  return segments.filter(s => s.text.trim() && s.end > from && s.start < to)
    .map(s => ({ modality: 'asr', start_seconds: s.start, end_seconds: s.end, excerpt: s.text.trim(), raw_score: null, method }));
}

// The auto rule for --clean auto, exported so the decision itself is testable.
export function needsCleanRetry(coverage, active) {
  return active >= ACTIVITY.min_active_seconds && coverage < active * ACTIVITY.retry_ratio;
}

async function activeSeconds(wav, duration) {
  const { stderr } = await run(ffmpegBin(), ['-hide_banner', '-nostats', '-i', wav, '-af',
    `silencedetect=n=${ACTIVITY.noise_db}dB:d=${ACTIVITY.min_silence_seconds}`, '-f', 'null', '-'], { timeout: 600000, maxBuffer: 64 * 1024 * 1024 });
  const silences = [];
  let start = null;
  for (const line of stderr.split('\n')) {
    const s = /silence_start:\s*(-?[\d.]+)/.exec(line), e = /silence_end:\s*([\d.]+)/.exec(line);
    if (s) start = Math.max(0, Number(s[1]));
    if (e && start !== null) { silences.push({ start, end: Number(e[1]) }); start = null; }
  }
  if (start !== null) silences.push({ start, end: duration });
  return round(Math.max(0, duration - coverageSeconds(silences, duration)));
}

async function attempt(wav, out, model, language, extraArgs, duration) {
  const args = ['-m', model, '-l', language, '-f', wav, '-oj', '-of', out, '-np', ...(language === 'zh' ? ['--prompt', ZH_PROMPT] : []), ...extraArgs];
  await run(whisperBin(), args, { timeout: Math.max(120000, duration * 20000), maxBuffer: 64 * 1024 * 1024 });
  const result = JSON.parse(await fs.readFile(`${out}.json`, 'utf8'));
  const segments = (result.transcription ?? []).map(item => ({
    start: round(item.offsets.from / 1000), end: round(Math.min(duration, item.offsets.to / 1000)), text: item.text.trim(),
  })).filter(s => s.text && s.end > s.start);
  return { segments, coverage: coverageSeconds(segments, duration) };
}

export function parseTranscribeArgs(argv) {
  const [media, output, ...rest] = argv, options = { lang: 'zh', model: undefined, clean: 'auto' };
  if (!media || !output) throw new Error('transcribe needs MEDIA and OUT.json');
  for (let i = 0; i < rest.length; i += 2) {
    const key = rest[i]?.replace(/^--/, ''), value = rest[i + 1];
    if (!['lang', 'model', 'clean'].includes(key) || !rest[i].startsWith('--') || value === undefined) throw new Error(`Bad transcribe option ${rest[i]}`);
    options[key] = value;
  }
  return { media, output, options };
}

export async function transcribe(media, output, { lang = 'zh', model = defaultModelPath(), clean = 'auto' } = {}) {
  if (!/^(auto|[a-z]{2,3})$/.test(lang)) throw new Error(`Bad language ${lang}`);
  if (!['auto', 'on', 'off'].includes(clean)) throw new Error('--clean must be auto, on or off');
  if (!output.endsWith('.json')) throw new Error('Transcript output must be a .json file');
  if (await fs.lstat(output).then(() => true, () => false)) throw new Error(`Output already exists: ${output}`);
  const modelPath = path.resolve(model);
  const modelSha = await verifyModel(modelPath);
  const binaryVersion = await whisperVersion();
  const info = await ffprobeJson(media);
  if (!info.streams.some(s => s.codec_type === 'audio')) throw new Error('Media has no audio stream');
  const duration = round(Number(info.format.duration));
  if (!(duration > 0)) throw new Error('Media duration unknown');
  const mediaSha = await digest(media);

  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), 'creative-asr-'));
  try {
    const wav = path.join(tmp, 'audio.wav');
    await run(ffmpegBin(), ['-nostdin', '-v', 'error', '-i', media, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav], { timeout: 600000 });
    const active = await activeSeconds(wav, duration);
    const attempts = [], results = [];
    const runAttempt = async cleaned => {
      let input = wav;
      if (cleaned) {
        input = path.join(tmp, 'clean.wav');
        await run(ffmpegBin(), ['-nostdin', '-v', 'error', '-i', wav, '-af', CLEAN_FILTER, '-c:a', 'pcm_s16le', input], { timeout: 600000 });
      }
      const extra = cleaned ? [...CLEAN_ARGS] : [];
      const result = await attempt(input, path.join(tmp, `attempt-${attempts.length}`), modelPath, lang, extra, duration);
      attempts.push({ params: { preprocess: cleaned ? CLEAN_FILTER : null, whisper_args: extra }, coverage_seconds: result.coverage });
      results.push(result);
    };
    let reason;
    if (clean === 'on') { await runAttempt(true); reason = 'clean forced (--clean on)'; }
    else {
      await runAttempt(false);
      const threshold = round(active * ACTIVITY.retry_ratio);
      if (clean === 'off') reason = 'plain only (--clean off)';
      else if (active < ACTIVITY.min_active_seconds) reason = `plain kept: only ${active}s of active audio (< ${ACTIVITY.min_active_seconds}s)`;
      else if (!needsCleanRetry(results[0].coverage, active)) {
        reason = `plain kept: coverage ${results[0].coverage}s >= ${threshold}s (50% of ${active}s active audio)`;
      } else {
        await runAttempt(true);
        reason = results[1].coverage > results[0].coverage
          ? `clean retry chosen: plain coverage ${results[0].coverage}s < ${threshold}s (50% of ${active}s active audio); clean covered ${results[1].coverage}s`
          : `plain kept after retry: clean coverage ${results[1].coverage}s did not exceed plain ${results[0].coverage}s`;
      }
    }
    const chosen = results.length > 1 && results[1].coverage > results[0].coverage ? 1 : 0;
    const transcript = {
      schema: TRANSCRIPT_SCHEMA,
      media: { path_basename: path.basename(media), sha256: mediaSha, duration },
      engine: { name: 'whisper.cpp', binary_version: binaryVersion, model: ASR_MODEL.name, model_sha256: modelSha },
      language: lang,
      audio_activity: { active_seconds: active, detector: `silencedetect n=${ACTIVITY.noise_db}dB d=${ACTIVITY.min_silence_seconds}` },
      attempts,
      chosen_attempt: chosen,
      choice_reason: reason,
      note: 'ASR text may contain wrong characters; timestamps are sentence-level and cut points must be confirmed by listening.',
      segments: results[chosen].segments,
    };
    await fs.writeFile(output, JSON.stringify(transcript, null, 2) + '\n', { flag: 'wx' });
    return { status: 'transcribed', output, chosen_attempt: chosen, choice_reason: reason,
      coverage_seconds: attempts[chosen].coverage_seconds, duration, segments: transcript.segments.length };
  } finally {
    await fs.rm(tmp, { recursive: true, force: true });
  }
}
