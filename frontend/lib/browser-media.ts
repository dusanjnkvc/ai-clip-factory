/** Real single-thread FFmpeg WebAssembly, loaded only from this site's assets. */
import type { FFmpeg as FFmpegInstance } from "@ffmpeg/ffmpeg";
import type { BrowserRow } from "./browser-db";
import type { CaptionCue } from "./browser-rules";

let instance: Promise<FFmpegInstance> | undefined;
let currentProgress: ((value: number) => void) | undefined;
let expectedSeconds = 1;
const logs: string[] = [];

function asset(name: string): string {
  return new URL(`${process.env.NEXT_PUBLIC_BASE_PATH || ""}/ffmpeg/${name}`, location.origin).href;
}

async function withDeadline<T>(promise: Promise<T>, milliseconds: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  try {
    return await Promise.race([promise, new Promise<T>((_, reject) => { timer = setTimeout(() => reject(new Error("Browser rendering exceeded its time limit. Try a shorter clip or a smaller source file.")), milliseconds); })]);
  } finally { clearTimeout(timer!); }
}

async function ffmpeg(): Promise<FFmpegInstance> {
  if (!instance) instance = (async () => {
    if (typeof WebAssembly === "undefined" || typeof Worker === "undefined") throw new Error("This browser does not support WebAssembly workers. Use a current desktop browser.");
    // Keep FFmpeg's worker URLs native to the self-hosted ESM package.
    const { FFmpeg } = await import(/* webpackIgnore: true */ asset("index.js")) as { FFmpeg: new () => FFmpegInstance };
    const engine = new FFmpeg();
    engine.on("log", ({ message }) => { logs.push(message); if (logs.length > 50) logs.shift(); });
    engine.on("progress", ({ time }) => currentProgress?.(Math.max(0, Math.min(.98, time / 1000000 / expectedSeconds))));
    try {
      await withDeadline(engine.load({ classWorkerURL: asset("worker.js"), coreURL: asset("ffmpeg-core.js"), wasmURL: asset("ffmpeg-core.wasm") }), 120000);
      const response = await fetch(asset("NotoSans.ttf"), { credentials: "same-origin" });
      if (!response.ok) throw new Error("The local subtitle font could not be loaded.");
      await engine.writeFile("NotoSans.ttf", new Uint8Array(await response.arrayBuffer()));
      return engine;
    } catch (failure) { engine.terminate(); instance = undefined; throw new Error("The browser renderer could not load. Reload the site and try again. " + String(failure)); }
  })();
  return instance;
}

export async function inspectVideo(blob: Blob): Promise<BrowserRow> {
  const url = URL.createObjectURL(blob);
  try {
    return await new Promise((resolve, reject) => {
      const video = document.createElement("video");
      const timer = setTimeout(() => { video.src = ""; reject(new Error("The source video metadata could not be read. Use a playable MP4 or WebM.")); }, 20000);
      video.preload = "metadata"; video.muted = true;
      video.onloadedmetadata = () => {
        clearTimeout(timer);
        const duration = video.duration, width = video.videoWidth, height = video.videoHeight;
        video.src = "";
        if (!Number.isFinite(duration) || duration < 1 || duration > 3600 || width < 16 || height < 16) reject(new Error("Source videos must be playable, between 1 second and 60 minutes, with valid dimensions."));
        else resolve({ duration, width, height, probe_method: "browser_video_metadata" });
      };
      video.onerror = () => { clearTimeout(timer); video.src = ""; reject(new Error("This browser cannot read the source. Use an H.264 MP4 or a supported WebM video.")); };
      video.src = url;
    });
  } finally { URL.revokeObjectURL(url); }
}

function inputOptions(bytes: Uint8Array): string[] {
  const signature = String.fromCharCode(...bytes.slice(4, 8));
  if (["ftyp", "moov", "mdat", "wide", "free", "skip"].includes(signature)) return ["-protocol_whitelist", "file,pipe", "-format_whitelist", "mov", "-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"];
  if (bytes[0] === 0x1a && bytes[1] === 0x45 && bytes[2] === 0xdf && bytes[3] === 0xa3) return ["-protocol_whitelist", "file,pipe", "-format_whitelist", "matroska,webm", "-f", "matroska"];
  throw new Error("Upload MP4/MOV or Matroska/WebM media. Playlists and remote media references are not supported.");
}

async function probe(engine: FFmpegInstance, input: string, options: string[], output: string): Promise<BrowserRow> {
  const result = await withDeadline(engine.ffprobe(["-v", "error", ...options, "-show_streams", "-show_format", "-of", "json", "-o", output, input]), 60000);
  // core 0.12.10 leaves ret=-1 after successful ffprobe. The fresh JSON output
  // below must still exist, parse, and contain validated measured streams.
  if (result !== 0 && result !== -1) throw new Error("FFmpeg could not inspect the media stream. " + logs.slice(-7).join(" "));
  const data = await engine.readFile(output, "utf8");
  const json = JSON.parse(String(data)); const video = json.streams?.find((stream: BrowserRow) => stream.codec_type === "video");
  if (!video) throw new Error("The file has no readable video stream.");
  let width = Number(video.width), height = Number(video.height);
  const rotation = Number(video.side_data_list?.find((item: BrowserRow) => item.rotation != null)?.rotation || video.tags?.rotate || 0);
  if (Math.abs(rotation) % 180 === 90) [width, height] = [height, width];
  const duration = Number(json.format?.duration || video.duration);
  if (!Number.isFinite(duration) || duration <= 0 || width < 16 || height < 16) throw new Error("The media has invalid dimensions or duration.");
  return { width, height, duration, codec: video.codec_name, has_audio: json.streams.some((stream: BrowserRow) => stream.codec_type === "audio") };
}

function assTime(seconds: number): string {
  const hundredths = Math.max(0, Math.round(seconds * 100));
  return `${Math.floor(hundredths / 360000)}:${String(Math.floor(hundredths / 6000) % 60).padStart(2, "0")}:${String(Math.floor(hundredths / 100) % 60).padStart(2, "0")}.${String(hundredths % 100).padStart(2, "0")}`;
}
function assText(value: string): string { return value.replace(/\\/g, "\\\\").replace(/{/g, "\\{").replace(/}/g, "\\}").replace(/\r?\n/g, "\\N").replace(/[\x00-\x08\x0b-\x1f]/g, ""); }

function captionsAss(plan: BrowserRow, cues: CaptionCue[]): { text: string; count: number } {
  const size = ({ clean: 62, bold: 74, podcast: 66, gaming: 58, karaoke: 68 } as BrowserRow)[plan.subtitle_style] || 62;
  let text = `[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Caption,Noto Sans,${size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,${plan.subtitle_style === "clean" ? 0 : -1},0,0,0,100,100,0,0,1,3,1,2,75,75,260,1\nStyle: Hook,Noto Sans,70,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,8,70,70,220,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n`;
  let offset = 0, count = 0;
  if (plan.subtitles_enabled) for (const scene of plan.scenes) {
    for (const cue of cues) {
      const start = Math.max(cue.start, scene.start), end = Math.min(cue.end, scene.end);
      if (end > start) { text += `Dialogue: 0,${assTime(offset + start - scene.start)},${assTime(offset + end - scene.start)},Caption,,0,0,0,,${assText(cue.text)}\n`; count++; }
    }
    offset += scene.end - scene.start;
  }
  if (plan.show_hook && plan.hook) text += `Dialogue: 1,0:00:00.00,${assTime(Math.min(2.5, plan.scenes.reduce((total: number, scene: BrowserRow) => total + scene.end - scene.start, 0)))},Hook,,0,0,0,,${assText(plan.hook)}\n`;
  return { text, count };
}

export async function renderBrowserClip(source: Blob, plan: BrowserRow, cues: CaptionCue[], mode: string, onProgress: (stage: string, percent: number) => Promise<void>): Promise<{ blob: Blob; media_info: BrowserRow }> {
  await onProgress("Loading the local browser FFmpeg engine", 5);
  const engine = await ffmpeg();
  const prefix = "job-" + crypto.randomUUID();
  const input = `${prefix}-source`, output = `${prefix}-render.mp4`, captionFile = `${prefix}-captions.ass`, inputProbe = `${prefix}-input.json`, outputProbe = `${prefix}-output.json`;
  const files = [input, output, captionFile, inputProbe, outputProbe];
  logs.length = 0;
  try {
    const bytes = new Uint8Array(await source.arrayBuffer()); const options = inputOptions(bytes);
    await onProgress("Reading local source media", 10);
    await engine.writeFile(input, bytes);
    const info = await probe(engine, input, options, inputProbe);
    if (plan.scenes.some((scene: BrowserRow) => scene.end > info.duration + .05)) throw new Error("The selected timeline extends beyond the source video.");
    const captions = captionsAss(plan, cues);
    await engine.writeFile(captionFile, new TextEncoder().encode(captions.text));
    expectedSeconds = plan.scenes.reduce((total: number, scene: BrowserRow) => total + scene.end - scene.start, 0);
    const graph: string[] = [], concat: string[] = [];
    for (const [index, scene] of plan.scenes.entries()) {
      const cropWidth = Math.max(2, Math.floor(Math.min(info.width, info.height * 9 / 16) / scene.zoom / 2) * 2);
      const cropHeight = Math.max(2, Math.min(info.height, Math.floor(cropWidth * 16 / 9 / 2) * 2));
      const x = Math.max(0, Math.min(info.width - cropWidth, Math.round((info.width - cropWidth) * scene.crop_x)));
      const y = Math.max(0, Math.min(info.height - cropHeight, Math.round((info.height - cropHeight) * scene.crop_y)));
      graph.push(`[0:v]trim=start=${scene.start.toFixed(4)}:end=${scene.end.toFixed(4)},setpts=PTS-STARTPTS,crop=${cropWidth}:${cropHeight}:${x}:${y},scale=1080:1920:flags=bilinear,setsar=1,fps=30[v${index}]`);
      if (info.has_audio) graph.push(`[0:a]atrim=start=${scene.start.toFixed(4)}:end=${scene.end.toFixed(4)},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a${index}]`);
      else graph.push(`anullsrc=r=48000:cl=stereo:d=${(scene.end - scene.start).toFixed(4)}[a${index}]`);
      concat.push(`[v${index}][a${index}]`);
    }
    graph.push(concat.join("") + `concat=n=${plan.scenes.length}:v=1:a=1[video][audio]`);
    graph.push(`[video]ass=filename=${captionFile}:fontsdir=.[outv]`);
    graph.push("[audio]loudnorm=I=-16:TP=-1.5:LRA=11[outa]");
    let lastPercent = 20;
    currentProgress = value => { const percent = 20 + Math.floor(value * 65); if (percent > lastPercent) { lastPercent = percent; void onProgress("Encoding your local vertical clip", percent); } };
    await onProgress("Encoding your local vertical clip", 20);
    const exit = await withDeadline(engine.exec(["-hide_banner", "-v", "error", ...options, "-i", input, "-filter_complex_threads", "1", "-filter_complex", graph.join(";"), "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-preset", mode === "quality" ? "fast" : "ultrafast", "-crf", mode === "quality" ? "21" : "24", "-pix_fmt", "yuv420p", "-threads", "1", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", output], 1200000), 1260000);
    currentProgress = undefined;
    if (exit !== 0) throw new Error("FFmpeg could not encode this clip. " + logs.slice(-4).join(" "));
    await onProgress("Checking actual output dimensions and playback", 88);
    const rendered = await probe(engine, output, ["-protocol_whitelist", "file,pipe", "-f", "mov"], outputProbe);
    if (rendered.width !== 1080 || rendered.height !== 1920 || rendered.codec !== "h264" || !rendered.has_audio || Math.abs(rendered.duration - expectedSeconds) > .3) throw new Error("The rendered file failed its resolution, duration, codec, or audio check.");
    const decoded = await withDeadline(engine.exec(["-v", "error", "-protocol_whitelist", "file,pipe", "-f", "mov", "-i", output, "-f", "null", "-"], 300000), 330000);
    if (decoded !== 0) throw new Error("The rendered file failed a complete playback decode.");
    const encoded = await engine.readFile(output);
    if (!(encoded instanceof Uint8Array) || encoded.length < 1000) throw new Error("FFmpeg returned an incomplete MP4.");
    const blob = new Blob([encoded.slice().buffer as ArrayBuffer], { type: "video/mp4" });
    return { blob, media_info: { ...rendered, decode_verified: true, subtitle_synchronized: true, subtitle_timing: captions.count ? "cue" : "none", subtitle_words: 0, subtitle_phrases: captions.count, source_had_audio: info.has_audio, size_bytes: blob.size, renderer: "ffmpeg_wasm_single_thread" } };
  } catch (failure) {
    // Retain source media in IndexedDB; clear any damaged renderer state.
    engine.terminate(); instance = undefined;
    throw failure instanceof Error ? failure : new Error(String(failure));
  } finally {
    currentProgress = undefined;
    if (engine.loaded) for (const file of files) try { await engine.deleteFile(file); } catch { /* Failed files may not have been created. */ }
  }
}
