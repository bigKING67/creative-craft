// Local speech-to-text with whisper.cpp. Customer audio never leaves the machine:
// ffmpeg extracts 16 kHz mono PCM into a private temp dir, whisper-cli transcribes it
// with a pinned, SHA-256 verified model, and the temp dir is removed afterwards.
// ASR text may contain wrong characters and timestamps are sentence-level; cut points
// derived from it must be confirmed by listening.
import * as fs from 'node:fs/promises';
import { rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { digest, ffprobeJson, run } from './project.mjs';
import { mediaTool, silenceFilter, silences, unionLength } from './media-analysis.mjs';

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
const ffmpegBin = () => mediaTool('ffmpeg');
const round = value => Math.round(value * 1000) / 1000;

// Hashing 1.6 GB takes seconds, so a verified digest is cached next to the model and
// reused only while size, inode, mtime and ctime are unchanged. ctime cannot be set
// from user space, so an in-place rewrite that restores size and mtime still
// invalidates the cache. Mismatch always throws.
export async function verifyModel(file, manifest = ASR_MODEL) {
  if (path.basename(file) !== manifest.file) throw new Error(`Unpinned ASR model ${path.basename(file)}; expected ${manifest.file}`);
  const stat = await fs.stat(file).catch(error => {
    if (error.code === 'ENOENT') throw Object.assign(new Error(`ASR model missing: ${file}; run npm run fetch-asr-model`), { code: 'ENOENT' });
    throw error;
  });
  if (!stat.isFile()) throw new Error(`ASR model is not a regular file: ${file}`);
  if (stat.size !== manifest.bytes) throw new Error(`ASR model SHA-256 mismatch: ${file} has ${stat.size} bytes, expected ${manifest.bytes}`);
  const marker = `${file}.sha256-verified.json`;
  const identity = { size: stat.size, ino: stat.ino, mtimeMs: stat.mtimeMs, ctimeMs: stat.ctimeMs, sha256: manifest.sha256 };
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
export const coverageSeconds = (segments, duration = Infinity) => round(unionLength(segments.map(s => [s.start, s.end]), duration));

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

// Which attempt is kept and why. Attempt 0 is plain (or the forced clean pass
// under --clean on); attempt 1, when present, is the clean retry that
// needsCleanRetry asked for. The retry is kept only if it covers more.
export function chooseAttempt(clean, active, coverages) {
  const chosen = coverages.length > 1 && coverages[1] > coverages[0] ? 1 : 0;
  const threshold = round(active * ACTIVITY.retry_ratio), [plain, cleaned] = coverages;
  const reason = clean === 'on' ? 'clean forced (--clean on)'
    : clean === 'off' ? 'plain only (--clean off)'
      : coverages.length > 1
        ? (chosen === 1
          ? `clean retry chosen: plain coverage ${plain}s < ${threshold}s (50% of ${active}s active audio); clean covered ${cleaned}s`
          : `plain kept after retry: clean coverage ${cleaned}s did not exceed plain ${plain}s`)
        : active < ACTIVITY.min_active_seconds
          ? `plain kept: only ${active}s of active audio (< ${ACTIVITY.min_active_seconds}s)`
          : `plain kept: coverage ${plain}s >= ${threshold}s (50% of ${active}s active audio)`;
  return { chosen, reason };
}

async function activeSeconds(wav, duration, signal) {
  const { stderr } = await run(ffmpegBin(), ['-hide_banner', '-nostats', '-i', wav, '-af',
    silenceFilter(ACTIVITY.noise_db, ACTIVITY.min_silence_seconds), '-f', 'null', '-'], { timeout: 600000, maxBuffer: 64 * 1024 * 1024, signal });
  return round(Math.max(0, duration - coverageSeconds(silences(stderr, duration), duration)));
}

async function attempt(wav, out, model, language, extraArgs, duration, signal) {
  const args = ['-m', model, '-l', language, '-f', wav, '-oj', '-of', out, '-np', ...(language === 'zh' ? ['--prompt', ZH_PROMPT] : []), ...extraArgs];
  await run(whisperBin(), args, { timeout: Math.max(120000, duration * 20000), maxBuffer: 64 * 1024 * 1024, signal });
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
  // The temp dir holds extracted customer audio. On SIGINT/SIGTERM the async
  // finally below would never run (the default handler exits immediately), so
  // stop the running ffmpeg/whisper child, delete the dir synchronously and
  // exit 130/143. The handlers are removed again when transcription ends.
  const controller = new AbortController(), signal = controller.signal;
  const onSignal = name => {
    controller.abort();
    try { rmSync(tmp, { recursive: true, force: true }); } finally { process.exit(name === 'SIGINT' ? 130 : 143); }
  };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);
  try {
    const wav = path.join(tmp, 'audio.wav');
    await run(ffmpegBin(), ['-nostdin', '-v', 'error', '-i', media, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav], { timeout: 600000, signal });
    const active = await activeSeconds(wav, duration, signal);
    const attempts = [], results = [];
    const runAttempt = async cleaned => {
      let input = wav;
      if (cleaned) {
        input = path.join(tmp, 'clean.wav');
        await run(ffmpegBin(), ['-nostdin', '-v', 'error', '-i', wav, '-af', CLEAN_FILTER, '-c:a', 'pcm_s16le', input], { timeout: 600000, signal });
      }
      const extra = cleaned ? [...CLEAN_ARGS] : [];
      const result = await attempt(input, path.join(tmp, `attempt-${attempts.length}`), modelPath, lang, extra, duration, signal);
      attempts.push({ params: { preprocess: cleaned ? CLEAN_FILTER : null, whisper_args: extra }, coverage_seconds: result.coverage });
      results.push(result);
    };
    await runAttempt(clean === 'on');
    if (clean === 'auto' && needsCleanRetry(results[0].coverage, active)) await runAttempt(true);
    const { chosen, reason } = chooseAttempt(clean, active, results.map(r => r.coverage));
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
    process.off('SIGINT', onSignal);
    process.off('SIGTERM', onSignal);
    await fs.rm(tmp, { recursive: true, force: true });
  }
}
