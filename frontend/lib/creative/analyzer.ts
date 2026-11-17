/** Measured browser footage evidence. No model, inferred dialogue, or semantic labels. */
import type { CaptionCue } from "../browser-rules";
import type { FrameSample, Row, SourceAnalysis } from "./types";

const MAX_FRAMES = 24;
const MEASURE_WIDTH = 96;
const MEASURE_HEIGHT = 54;
const MAX_AUDIO_BYTES = 20 * 1024 * 1024;
const MAX_AUDIO_SECONDS = 180;
const completed = new Map<string, SourceAnalysis>();

export type AnalysisProgress = (stage: string, percent: number) => void;
type Measurement = Pick<FrameSample, "change" | "motion" | "focus_x" | "focus_y" | "brightness" | "sharpness" | "focus_confidence"> & { luma: Float32Array };

function clamp(value: number, minimum = 0, maximum = 1): number {
  return Math.min(maximum, Math.max(minimum, value));
}

function aborted(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Video analysis was cancelled.", "AbortError");
}

function cleanCues(cues: CaptionCue[], duration: number): CaptionCue[] {
  if (!Array.isArray(cues) || cues.length > 10000) throw new Error("Supply at most 10,000 subtitle cues.");
  return cues.map(cue => {
    if (!Number.isFinite(cue.start) || !Number.isFinite(cue.end) || cue.start < 0 || cue.end <= cue.start || cue.end > duration + .05 || typeof cue.text !== "string" || cue.text.length > 2000) {
      throw new Error("Subtitle cues must use valid source timestamps and fit the selected video.");
    }
    return { start: cue.start, end: cue.end, text: cue.text };
  }).sort((a, b) => a.start - b.start || a.end - b.end);
}

/** Cache identity includes supplied captions; it is not a media ownership claim. */
export async function analysisFingerprint(source: Row, cues: CaptionCue[] = []): Promise<string> {
  const identity = JSON.stringify({
    version: 1, id: String(source.id || ""), filename: String(source.filename || ""),
    size: source.size_bytes ?? source.size ?? null, last_modified: source.last_modified ?? source.lastModified ?? null,
    media: source.media_info || {}, cues,
  });
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identity));
  return Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, "0")).join("");
}

/** Difference and edge centroid are low-confidence crop hints, never subject detection. */
export function measureFramePixels(rgba: Uint8ClampedArray, width: number, height: number, previous?: Float32Array): Measurement {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 3 || height < 3 || rgba.length !== width * height * 4 || previous && previous.length !== width * height) {
    throw new Error("A complete sampled frame is required for local measurement.");
  }
  const luma = new Float32Array(width * height);
  let light = 0, difference = 0;
  for (let index = 0; index < luma.length; index++) {
    const offset = index * 4;
    const value = (.2126 * rgba[offset] + .7152 * rgba[offset + 1] + .0722 * rgba[offset + 2]) / 255;
    luma[index] = value;
    light += value;
    if (previous) difference += Math.abs(value - previous[index]);
  }
  let edgeTotal = 0, focusTotal = 0, focusX = 0, focusY = 0;
  for (let y = 1; y < height - 1; y++) for (let x = 1; x < width - 1; x++) {
    const index = y * width + x;
    const edge = (Math.abs(luma[index + 1] - luma[index - 1]) + Math.abs(luma[index + width] - luma[index - width])) / 2;
    const delta = previous ? Math.abs(luma[index] - previous[index]) : 0;
    const normalizedX = x / (width - 1), normalizedY = y / (height - 1);
    const centerBias = .3 + .7 * Math.exp(-3 * ((normalizedX - .5) ** 2 + (normalizedY - .5) ** 2));
    const weight = (edge * .6 + delta * .4) * centerBias;
    edgeTotal += edge;
    focusTotal += weight;
    focusX += normalizedX * weight;
    focusY += normalizedY * weight;
  }
  const change = clamp(difference / luma.length);
  return {
    luma, brightness: clamp(light / luma.length), sharpness: clamp(edgeTotal / ((width - 2) * (height - 2))),
    change, motion: change,
    focus_x: focusTotal > .001 ? clamp(focusX / focusTotal, .15, .85) : .5,
    focus_y: focusTotal > .001 ? clamp(focusY / focusTotal, .15, .85) : .5,
    focus_confidence: "low",
  };
}

function median(values: number[]): number {
  const ordered = [...values].sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  return ordered.length ? ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2 : 0;
}

/** Candidate change times are sampled boundaries, not frame-accurate scene cuts. */
export function measuredSceneChanges(frames: Pick<FrameSample, "timestamp" | "change">[]): number[] {
  const changes = frames.slice(1).map(frame => frame.change);
  const baseline = median(changes), deviation = median(changes.map(value => Math.abs(value - baseline)));
  const threshold = Math.min(.65, Math.max(.14, baseline + Math.max(.06, deviation * 2.8)));
  return frames.slice(1).filter(frame => frame.change > threshold).map(frame => frame.timestamp);
}

function mediaEvent(video: HTMLVideoElement, event: string, signal?: AbortSignal, timeout = 15000): Promise<void> {
  aborted(signal);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => finish(new Error("The source video did not decode a sampled frame in time. Try a shorter, browser-playable MP4.")), timeout);
    const success = () => finish();
    const error = () => finish(new Error("This browser could not decode the selected source video. Use a playable H.264 MP4 or supported WebM."));
    const cancel = () => finish(new DOMException("Video analysis was cancelled.", "AbortError"));
    function finish(failure?: Error) {
      clearTimeout(timer);
      video.removeEventListener(event, success);
      video.removeEventListener("error", error);
      signal?.removeEventListener("abort", cancel);
      if (failure) reject(failure); else resolve();
    }
    video.addEventListener(event, success, { once: true });
    video.addEventListener("error", error, { once: true });
    signal?.addEventListener("abort", cancel, { once: true });
  });
}

async function seek(video: HTMLVideoElement, timestamp: number, signal?: AbortSignal): Promise<void> {
  aborted(signal);
  if (Math.abs(video.currentTime - timestamp) < .005 && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) return;
  const ready = mediaEvent(video, "seeked", signal);
  video.currentTime = timestamp;
  await ready;
  if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) await mediaEvent(video, "loadeddata", signal);
}

function localSourceUrl(value: string): string {
  const url = new URL(value, location.href);
  if (url.origin !== location.origin || !["blob:", "http:", "https:"].includes(url.protocol) || url.username || url.password) {
    throw new Error("Analyze an authorized source from this workspace. Arbitrary external media URLs are not fetched.");
  }
  return url.href;
}

async function measuredAudio(source: Row, url: string, times: number[], duration: number, signal?: AbortSignal): Promise<SourceAnalysis["audio"]> {
  if (source.media_info?.has_audio === false) return { status: "unavailable", reason: "The source metadata reports no audio track.", samples: [] };
  const bytes = Number(source.size_bytes ?? source.size ?? 0);
  if (!Number.isFinite(bytes) || bytes <= 0 || bytes > MAX_AUDIO_BYTES || duration > MAX_AUDIO_SECONDS) {
    return { status: "unavailable", reason: "Audio measurement is limited to known files up to 20 MB and three minutes to limit browser memory use.", samples: [] };
  }
  const Audio = globalThis.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Audio) return { status: "unavailable", reason: "This browser has no supported audio decoder for measurement.", samples: [] };
  let context: AudioContext | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancelDecode: (() => void) | undefined;
  try {
    aborted(signal);
    const response = await fetch(url, { credentials: "same-origin", redirect: "error", signal });
    if (!response.ok) throw new Error("The local audio source could not be read.");
    const blob = await response.blob();
    if (blob.size > MAX_AUDIO_BYTES) return { status: "unavailable", reason: "The source exceeds the local audio-analysis memory limit.", samples: [] };
    context = new Audio();
    const audio = await Promise.race([
      context.decodeAudioData(await blob.arrayBuffer()),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error("Audio decoding exceeded its analysis time limit.")), 30000); }),
      new Promise<never>((_, reject) => {
        cancelDecode = () => reject(new DOMException("Video analysis was cancelled.", "AbortError"));
        signal?.addEventListener("abort", cancelDecode, { once: true });
        if (signal?.aborted) cancelDecode();
      }),
    ]);
    aborted(signal);
    const samples = times.map(timestamp => {
      const first = Math.max(0, Math.floor((timestamp - .125) * audio.sampleRate));
      const last = Math.min(audio.length, Math.ceil((timestamp + .125) * audio.sampleRate));
      let squares = 0, count = 0;
      for (let channel = 0; channel < audio.numberOfChannels; channel++) {
        const values = audio.getChannelData(channel);
        for (let index = first; index < last; index++) { squares += values[index] ** 2; count++; }
      }
      return { timestamp, rms: count ? clamp(Math.sqrt(squares / count)) : 0 };
    });
    return { status: "measured", samples };
  } catch (failure) {
    if (signal?.aborted || failure instanceof DOMException && failure.name === "AbortError") throw failure;
    return { status: "unavailable", reason: "The browser could not decode this container's audio for analysis. No audio events or dialogue were inferred.", samples: [] };
  } finally {
    if (timer) clearTimeout(timer);
    if (cancelDecode) signal?.removeEventListener("abort", cancelDecode);
    if (context) try { await context.close(); } catch { /* No output nodes are connected. */ }
  }
}

export function clearAnalysisCache(): void { completed.clear(); }

/** Actual sampled footage, supplied cues, and optional bounded RMS measurements. */
export async function analyzeVideo(source: Row, sourceUrl: string, suppliedCues: CaptionCue[] = [], onProgress: AnalysisProgress = () => {}, signal?: AbortSignal): Promise<SourceAnalysis> {
  if (typeof document === "undefined") throw new Error("Video analysis runs in the browser.");
  if (!source?.id) throw new Error("Choose a source video from your workspace.");
  const url = localSourceUrl(sourceUrl);
  const fingerprint = await analysisFingerprint(source, suppliedCues);
  aborted(signal);
  const cached = completed.get(fingerprint);
  if (cached) { onProgress("Reusing unchanged measured footage analysis", 100); return structuredClone(cached); }
  onProgress("Reading the selected local video", 2);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.crossOrigin = "anonymous";
  try {
    const metadata = mediaEvent(video, "loadedmetadata", signal, 20000);
    video.src = url;
    video.load();
    await metadata;
    const duration = video.duration, width = video.videoWidth, height = video.videoHeight;
    if (!Number.isFinite(duration) || duration < 1 || duration > 3600 || width < 16 || height < 16 || width > 16384 || height > 16384) {
      throw new Error("Analyze a valid source between one second and one hour with supported video dimensions.");
    }
    const cues = cleanCues(suppliedCues, duration);
    const count = Math.min(MAX_FRAMES, Math.max(4, Math.ceil(duration / 3) + 1));
    const lastTime = Math.max(.02, duration - Math.min(.05, duration / 10));
    const times = Array.from({ length: count }, (_, index) => Math.min(lastTime, .02 + (lastTime - .02) * index / (count - 1)));
    const measurement = document.createElement("canvas");
    measurement.width = MEASURE_WIDTH; measurement.height = MEASURE_HEIGHT;
    const pixels = measurement.getContext("2d", { willReadFrequently: true });
    const thumbnail = document.createElement("canvas");
    const thumbnailScale = Math.min(240 / width, 240 / height, 1);
    thumbnail.width = Math.max(1, Math.round(width * thumbnailScale));
    thumbnail.height = Math.max(1, Math.round(height * thumbnailScale));
    const picture = thumbnail.getContext("2d");
    if (!pixels || !picture) throw new Error("Canvas video-frame measurement is unavailable in this browser.");
    let previous: Float32Array | undefined;
    const frames: FrameSample[] = [];
    for (const [index, timestamp] of times.entries()) {
      aborted(signal);
      await seek(video, timestamp, signal);
      pixels.drawImage(video, 0, 0, MEASURE_WIDTH, MEASURE_HEIGHT);
      const measured = measureFramePixels(pixels.getImageData(0, 0, MEASURE_WIDTH, MEASURE_HEIGHT).data, MEASURE_WIDTH, MEASURE_HEIGHT, previous);
      previous = measured.luma;
      picture.drawImage(video, 0, 0, thumbnail.width, thumbnail.height);
      const { luma: _unused, ...metrics } = measured;
      frames.push({ timestamp: Number(timestamp.toFixed(3)), thumbnail: thumbnail.toDataURL("image/jpeg", .7), ...metrics });
      onProgress(`Measuring source frame ${index + 1} of ${count}`, 8 + Math.round((index + 1) / count * 72));
    }
    const sceneChanges = measuredSceneChanges(frames);
    const warnings: string[] = [];
    const croppedWidth = Math.min(width, height * 9 / 16), croppedHeight = croppedWidth * 16 / 9;
    if (croppedWidth < 900 || croppedHeight < 1600) warnings.push(`A full-height 9:16 crop uses about ${Math.round(croppedWidth)} × ${Math.round(croppedHeight)} source pixels. A 1080 × 1920 export would upscale it; consider a lower export size or a composition that retains more of the source.`);
    if (width / height > 1.5) warnings.push("A vertical fill crop removes much of this wide source. Check gameplay UI, logos, and text manually, or choose a fit/split composition.");
    if (frames.every(frame => frame.sharpness < .01)) warnings.push("Sampled frames contain little edge detail. This may be intentional or a sign of soft footage; review the source.");
    if (frames.every(frame => frame.brightness < .06)) warnings.push("Sampled frames are very dark; confirm the source remains readable.");
    onProgress("Checking bounded local audio measurements", 84);
    const audio = await measuredAudio(source, url, times, duration, signal);
    const limitations = [
      "Local measurements are not AI understanding. No people, objects, eliminations, products, reactions, or events were recognized.",
      `Only ${frames.length} representative frames were measured. Candidate scene-change times are sampled approximations; short events between samples may be missed.`,
      "Motion is a frame-difference proxy, not optical flow or camera/subject tracking. Edge/difference centroids are low-confidence crop hints and may focus on text or background detail.",
      "No automatic speech transcription is performed. Only supplied subtitle cues can support dialogue or quotations.",
      "Audio RMS indicates measured loudness near sampled times, not the meaning of an audio event. Loud moments are not automatically interesting.",
    ];
    if (!cues.length) limitations.push("No subtitle cues were supplied. Opening text and narrative meaning require the user's input and review.");
    if (audio.status === "unavailable" && audio.reason) limitations.push(audio.reason);
    const result: SourceAnalysis = { source_id: String(source.id), fingerprint, duration, width, height, frames, scene_changes: sceneChanges, cues, limitations, warnings, method: "local_measured", analyzed_at: new Date().toISOString(), audio };
    aborted(signal);
    completed.set(fingerprint, structuredClone(result));
    if (completed.size > 12) completed.delete(completed.keys().next().value!);
    onProgress("Measured footage analysis ready for human review", 100);
    return result;
  } catch (failure) {
    if (failure instanceof DOMException && failure.name === "SecurityError") throw new Error("The browser blocked frame access for this source. Re-import the authorized video into this workspace.");
    throw failure;
  } finally {
    video.pause();
    video.removeAttribute("src");
    video.load();
  }
}
