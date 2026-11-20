"""FFmpeg rendering with an entirely validated, numeric timeline.

No user/AI text is ever interpolated into an FFmpeg expression or shell command.
Text is written as escaped ASS data. Every subprocess uses argv and shell=False.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from .schemas import ClipPlan, Transcript,expanded_scenes,output_duration,OUTPUT_PRESETS


class PipelineError(RuntimeError):
    pass


class ConfigurationError(PipelineError):
    pass


def ffmpeg_binary() -> str:
    configured = os.getenv("FFMPEG_BINARY")
    if configured:
        return configured
    installed = shutil.which("ffmpeg")
    if installed:
        return installed
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise ConfigurationError("FFmpeg is unavailable. Install FFmpeg or set FFMPEG_BINARY.") from exc


_encoder_cache={}


def encoding_args(mode='fast'):
    selected=os.getenv('LOCAL_AI_ENCODER','auto')
    if selected not in {'auto','libx264','h264_nvenc'}:
        raise ConfigurationError('LOCAL_AI_ENCODER must be auto, libx264 or h264_nvenc.')
    binary=ffmpeg_binary()
    if selected!='libx264' and binary not in _encoder_cache:
        with tempfile.TemporaryDirectory(prefix='acf-encoder-') as directory:
            try:
                run_media([binary,'-v','error','-f','lavfi','-i','color=c=black:s=320x180:r=10','-t','.2',
                    '-c:v','h264_nvenc','-pix_fmt','yuv420p',str(Path(directory)/'probe.mp4')],timeout=15)
                _encoder_cache[binary]=True
            except PipelineError:
                _encoder_cache[binary]=False
    if selected!='libx264' and _encoder_cache.get(binary):
        return ['-c:v','h264_nvenc','-preset','p4','-cq','23' if mode=='fast' else '20','-b:v','0']
    return ['-c:v','libx264','-preset','veryfast' if mode=='fast' else 'medium','-crf','22' if mode=='fast' else '19']


def run_media(args: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, timeout=timeout, shell=False)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Media executable is unavailable: {Path(args[0]).name}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("Media operation exceeded the configured timeout") from exc
    if result.returncode != 0:
        # No input data, credentials, or complete argv are exposed in API errors.
        detail = result.stderr[-2400:].strip()
        raise PipelineError(f"FFmpeg could not process the media: {detail}")
    return result


def safe_input_options(source_path: str | Path) -> list[str]:
    """Pin the demuxer before parsing an untrusted upload.

    File extensions and Content-Type do not establish the container. Explicit
    magic checks reject HLS/DASH/concat/image playlists before a media process is
    spawned. A forced demuxer and protocol whitelist are defense in depth, and
    MOV external tracks are disabled to prevent nested local-file references.
    """
    path = Path(source_path).resolve()
    if not path.is_file():
        raise PipelineError("Source media does not exist")
    with path.open("rb") as stream:
        header = stream.read(64)
    options = ["-protocol_whitelist", "file,pipe"]
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return options + ["-format_whitelist", "matroska,webm", "-f", "matroska"]
    if len(header) >= 12 and header[4:8] in {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}:
        return options + ["-format_whitelist", "mov", "-f", "mov", "-enable_drefs", "0", "-use_absolute_path", "0"]
    raise PipelineError("Unsupported media container. Upload an MP4/MOV or Matroska/WebM video; playlists and remote references are not accepted.")


def probe_media(source_path: str | Path) -> dict:
    path = Path(source_path).resolve()
    if not path.is_file():
        raise PipelineError("Source media does not exist")
    input_options = safe_input_options(path)
    probe = os.getenv("FFPROBE_BINARY") or shutil.which("ffprobe")
    if probe:
        result = run_media([probe, "-v", "error", *input_options, "-show_streams", "-show_format", "-of", "json", str(path)], timeout=60)
        try:
            info = json.loads(result.stdout)
            streams = info.get("streams", [])
            video = next(s for s in streams if s.get("codec_type") == "video")
            rotation = int(video.get("tags", {}).get("rotate", 0))
            for data in video.get("side_data_list", []):
                if "rotation" in data:
                    rotation = int(data["rotation"])
            width, height = int(video["width"]), int(video["height"])
            if abs(rotation) % 180 == 90:
                width, height = height, width
            duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
            audio = any(s.get("codec_type") == "audio" for s in streams)
            codec = video.get("codec_name")
            rate=video.get('avg_frame_rate') or video.get('r_frame_rate') or '0/1'
            try:fps=float(Fraction(rate))
            except (ValueError,ZeroDivisionError):fps=None
            audio_stream=next((s for s in streams if s.get('codec_type')=='audio'),{})
            audio_codec=audio_stream.get('codec_name')
        except (KeyError, StopIteration, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise PipelineError("The file does not contain a valid timed video stream") from exc
    else:
        # imageio-ffmpeg supplies FFmpeg without ffprobe on portable Windows.
        # Its header parser is sufficient for rendering and is verified by decode.
        try:
            result = subprocess.run([ffmpeg_binary(), "-hide_banner", *input_options, "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PipelineError("Unable to inspect source media") from exc
        header = result.stderr
        duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", header)
        video_match = re.search(r"Stream[^\n]*Video:\s*([^,]+),[^\n]*?\b(\d{2,5})x(\d{2,5})\b", header)
        if not duration_match or not video_match:
            raise PipelineError("A valid video duration and dimensions are required")
        hours, minutes, seconds = map(float, duration_match.groups())
        duration = hours * 3600 + minutes * 60 + seconds
        width, height = int(video_match.group(2)), int(video_match.group(3))
        if re.search(r"rotation of (?:-?90|270)\.", header):
            width, height = height, width
        audio = bool(re.search(r"Stream[^\n]*Audio:", header))
        codec = video_match.group(1).split(" ")[0]
        rate=re.search(r'(\d+(?:\.\d+)?) fps',header)
        fps=float(rate[1]) if rate else None
        audio_match=re.search(r'Audio:\s*([\w]+)',header)
        audio_codec=audio_match[1] if audio_match else None
    if not math.isfinite(duration) or duration <= 0 or width < 16 or height < 16 or width > 16384 or height > 16384:
        raise PipelineError("Invalid video dimensions or duration")
    return {"path": str(path), "duration": duration, "width": width, "height": height, "has_audio": audio, "codec": codec, "size_bytes": path.stat().st_size,
        'fps':fps if fps is not None and math.isfinite(fps) and fps>0 else None,'audio_codec':audio_codec}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_audio(source_path: str | Path, output_path: Path, start: float = 0, duration: float | None = None) -> Path:
    args = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), *safe_input_options(source_path), "-i", str(Path(source_path).resolve())]
    if duration is not None:
        args += ["-t", str(duration)]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k", str(output_path.resolve())]
    run_media(args)
    return output_path


def sample_frames(source_path: str | Path, duration: float, count: int = 4) -> list[dict]:
    """Small JPEGs sent only to the configured hosted vision model."""
    import base64
    result = []
    with tempfile.TemporaryDirectory(prefix="acf-frames-") as temp:
        for index in range(count):
            timestamp = min(max(duration * (index + .5) / count, 0), max(0, duration - .1))
            frame = Path(temp) / f"frame-{index}.jpg"
            run_media([ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}", *safe_input_options(source_path), "-i", str(Path(source_path).resolve()), "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "5", str(frame)], timeout=60)
            if frame.is_file():
                result.append({"timestamp": round(timestamp, 3), "data_url": "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii")})
    return result


def scene_events(source_path: str | Path, *, limit: int = 100) -> list[float]:
    """FFmpeg scene-change measurements, rather than fabricated visual events."""
    result = run_media([ffmpeg_binary(), "-hide_banner", "-loglevel", "info", *safe_input_options(source_path), "-i", str(Path(source_path).resolve()), "-an", "-vf", "scale=320:-2,select=gt(scene\\,0.32),showinfo", "-frames:v", str(limit), "-f", "null", "-"], timeout=180)
    return [float(value) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr)][:limit]


def _ass_escape(text: str) -> str:
    # Prevent ASS override tags and line/control injections from model/user text.
    return str(text).replace("\\", "＼").replace("{", "(").replace("}", ")").replace("\r", " ").replace("\n", " ").replace("\x00", "").strip()


def _ass_time(value: float) -> str:
    centiseconds = max(0, round(value * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{fraction:02d}"


def timeline_words(plan: ClipPlan, transcript: Transcript) -> list[dict]:
    """Map source timestamps across reordered/cut scenes into output time."""
    words = []
    offset = 0.0
    for scene in expanded_scenes(plan.scenes):
        for word_index,word in enumerate(transcript.words):
            # Assign a boundary-spanning word to one scene. Intersection alone
            # would repeat it when adjacent scenes cut through the same word.
            if word.end>scene.start and word.start<scene.end:
                start = offset + (max(word.start, scene.start) - scene.start)/scene.speed
                end = offset + (min(word.end, scene.end) - scene.start)/scene.speed
                if end > start and word.word.strip():
                    if words and words[-1].get('_source_word')==word_index and abs(words[-1]['end']-start)<.002:
                        words[-1]['end']=end
                    else:words.append({"word": word.word, "start": start, "end": end,'_source_word':word_index})
        offset += output_duration(scene)
    for word in words:word.pop('_source_word',None)
    return words


def timeline_cues(plan: ClipPlan, transcript: Transcript) -> list[dict]:
    """Map supplied phrase cue intervals without estimating any word timings."""
    cues = []
    offset = 0.0
    for scene in expanded_scenes(plan.scenes):
        for cue in transcript.segments:
            intersection_start = max(cue.start, scene.start)
            intersection_end = min(cue.end, scene.end)
            if intersection_end > intersection_start and cue.text.strip():
                start = offset + (intersection_start - scene.start)/scene.speed
                end = offset + (intersection_end - scene.start)/scene.speed
                if cues and cues[-1]["text"] == cue.text and abs(cues[-1]["end"] - start) < .001:
                    cues[-1]["end"] = end
                else:
                    cues.append({"text": cue.text, "start": start, "end": end})
        offset += output_duration(scene)
    return cues


def write_subtitles(plan: ClipPlan, transcript: Transcript, output: Path) -> dict:
    style = plan.subtitle_style
    # The lower safe area leaves platform UI and the central subject visible.
    font_size = {"clean": 62, "bold": 74, "podcast": 66, "gaming": 58, "karaoke": 68}[style]
    outline = 3 if style == "clean" else 4
    bold = 0 if style == "clean" else -1
    if plan.caption_size is not None:font_size=plan.caption_size
    canvas_w,canvas_h=OUTPUT_PRESETS[plan.output_preset]
    # ASS scales the established portrait typography proportionally to each canvas.
    scale=min(canvas_w/1080,canvas_h/1920)
    font_size=round(font_size*scale)
    color='&H00'+plan.caption_color[5:7]+plan.caption_color[3:5]+plan.caption_color[1:3]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_w}
PlayResY: {canvas_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{plan.caption_font},{font_size},{color},&H0057EAFF,&H00202020,&H90000000,{bold},0,0,0,100,100,0,0,1,{outline},1,2,100,100,{round(plan.caption_margin*scale)},1
Style: Hook,Arial,{round(72*scale)},&H00FFFFFF,&H00FFFFFF,&H00202020,&H90000000,-1,0,0,0,100,100,0,0,1,4,1,8,60,60,{round(240*scale)},1
Style: Required,Arial,{round(44*scale)},&H00FFFFFF,&H00FFFFFF,&H00202020,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,8,60,60,{round(460*scale)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    words = timeline_words(plan, transcript) if plan.subtitles_enabled else []
    cues = timeline_cues(plan, transcript) if plan.subtitles_enabled and not words else []
    if plan.manual_captions and plan.subtitles_enabled:
        words=[];cues=[c.model_dump() for c in plan.manual_captions]
    # Small phrase groups retain context; \kf provides synchronized word fill.
    group = []
    groups = []
    for word in words:
        if group and (len(group) >= 5 or len(" ".join(w["word"] for w in group)) > 34 or word["start"] - group[-1]["end"] > .65):
            groups.append(group)
            group = []
        group.append(word)
    if group:
        groups.append(group)
    for group in groups:
        start, end = group[0]["start"], group[-1]["end"]
        parts = []
        for index, word in enumerate(group):
            next_start = group[index + 1]["start"] if index + 1 < len(group) else end
            duration = max(.01, next_start - word["start"])
            parts.append("{\\kf" + str(round(duration * 100)) + "}" + _ass_escape(word["word"]))
        events.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,," + " ".join(parts))
    for cue in cues:
        # SRT/VTT offers phrase times, not aligned words. Keep each supplied
        # phrase visible over its exact interval, including in karaoke style.
        events.append(f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},Default,,0,0,0,,{_ass_escape(cue['text'])}")
    duration = sum(output_duration(s) for s in expanded_scenes(plan.scenes))
    if plan.show_hook and plan.hook:
        events.append(f"Dialogue: 1,0:00:00.00,{_ass_time(min(2.5, duration))},Hook,,0,0,0,,{_ass_escape(plan.hook)}")
    if plan.required_on_video_text:
        text=' · '.join(plan.required_on_video_text)
        if len(text)>350:
            raise PipelineError('Mandatory on-video text exceeds a readable overlay. Review campaign placement manually.')
        events.append(f"Dialogue: 2,0:00:00.00,{_ass_time(duration)},Required,,0,0,0,,{_ass_escape(text)}")
    output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return {"words": len(words), "phrases": len(groups) + len(cues), "synchronized": bool(words or cues),
            "timing": "word" if words else "cue" if cues else "none", "path": str(output)}


def render_clip(source_path: str | Path, raw_plan: dict, raw_transcript: dict, output_path: str | Path, mode: str = "fast") -> dict:
    plan = ClipPlan.model_validate(raw_plan)
    transcript = Transcript.model_validate(raw_transcript)
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    if output == source:
        raise PipelineError("Rendering must never overwrite original source media")
    info = probe_media(source)
    canvas_w,canvas_h=OUTPUT_PRESETS[plan.output_preset]
    output_fps=min(60,max(1,info.get('fps') or 30))
    if any(scene.end > info["duration"] + .05 for scene in plan.scenes):
        raise PipelineError("Editing timeline exceeds the source video duration")
    if mode not in {"fast", "quality"}:
        raise PipelineError("Unknown rendering mode")
    output.parent.mkdir(parents=True, exist_ok=True)
    captions_output = output.with_suffix(".ass")
    with tempfile.TemporaryDirectory(prefix="acf-render-", dir=output.parent) as temp:
        work = Path(temp)
        subtitle_info = write_subtitles(plan, transcript, work / "captions.ass")
        graph = []
        concat = []
        shots=expanded_scenes(plan.scenes)
        for index, scene in enumerate(shots):
            width, height = info["width"], info["height"]
            base_zoom=min(scene.zoom,scene.zoom_end or scene.zoom)
            crop_w = min(width, height * canvas_w / canvas_h) / base_zoom
            crop_h = crop_w * canvas_h / canvas_w
            crop_w = max(2, int(crop_w) // 2 * 2)
            crop_h = max(2, min(height, int(crop_h) // 2 * 2))
            crop_x = max(0, min(width - crop_w, int((width - crop_w) * scene.crop_x)))
            crop_y = max(0, min(height - crop_h, int((height - crop_h) * scene.crop_y)))
            duration = output_duration(scene)
            x_end = scene.crop_x if scene.crop_x_end is None else scene.crop_x_end
            y_end = scene.crop_y if scene.crop_y_end is None else scene.crop_y_end
            x = f"'(in_w-out_w)*max(0,min(1,{scene.crop_x:.6f}+({x_end-scene.crop_x:.6f})*min(t/{duration:.6f},1)+{scene.shake:.6f}*sin(43*t)))'"
            y = f"'(in_h-out_h)*max(0,min(1,{scene.crop_y:.6f}+({y_end-scene.crop_y:.6f})*min(t/{duration:.6f},1)+{scene.shake*.5:.6f}*cos(37*t)))'"
            effects = []
            intensity=scene.effect_intensity
            if scene.effect == "contrast": effects.append(f"eq=contrast={1+.12*intensity:.4f}:saturation={1+.14*intensity:.4f}")
            elif scene.effect == "retro": effects.extend([f"eq=contrast={1+.2*intensity:.4f}:saturation={1-.56*intensity:.4f}",f"noise=alls={4*intensity:.4f}:allf=t"])
            elif scene.effect == 'flash':effects.append(f"eq=brightness='if(lt(t,0.07),{.18*intensity:.4f},0)':eval=frame")
            if scene.zoom_end is not None and abs(scene.zoom_end-scene.zoom)>.001 and plan.framing=='crop':
                count=max(1,duration*output_fps)
                z=f'{scene.zoom/base_zoom:.6f}+{(scene.zoom_end-scene.zoom)/base_zoom:.6f}*min(on/{count:.4f},1)'
                effects.append(f"zoompan=z='{z}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={canvas_w}x{canvas_h}:fps={output_fps:.6f}")
            if scene.transition == "fade" and duration > .5:
                fade = min(.14, duration/5)
                effects.extend([f"fade=t=in:st=0:d={fade:.4f}", f"fade=t=out:st={duration-fade:.4f}:d={fade:.4f}"])
            polish = "," + ",".join(effects) if effects else ""
            clock=f'setpts=(PTS-STARTPTS)/{scene.speed:.6f}'
            if scene.freeze:polish+=f',tpad=stop_mode=clone:stop_duration={scene.freeze:.4f}'
            if plan.framing=='fit':
                graph.append(f"[0:v]trim=start={scene.start:.4f}:end={scene.end:.4f},{clock},split=2[fg{index}][bg{index}]")
                graph.append(f"[bg{index}]scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=increase,crop={canvas_w}:{canvas_h},boxblur=24:2[blur{index}]")
                graph.append(f"[fg{index}]scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease[fit{index}]")
                graph.append(f"[blur{index}][fit{index}]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={output_fps:.6f}{polish}[v{index}]")
            else:
                graph.append(f"[0:v]trim=start={scene.start:.4f}:end={scene.end:.4f},{clock},crop={crop_w}:{crop_h}:{x}:{y},scale={canvas_w}:{canvas_h}:flags=bicubic,setsar=1,fps={output_fps:.6f}{polish}[v{index}]")
            if info["has_audio"] and plan.audio_treatment != "mute":
                padding=f',apad=pad_dur={scene.freeze:.4f}' if scene.freeze else ''
                graph.append(f"[0:a]atrim=start={scene.start:.4f}:end={scene.end:.4f},asetpts=PTS-STARTPTS,atempo={scene.speed:.6f},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo{padding},atrim=duration={duration:.6f}[a{index}]")
            else:
                graph.append(f"anullsrc=r=48000:cl=stereo:d={duration:.4f}[a{index}]")
            concat.extend([f"[v{index}]", f"[a{index}]"])
        graph.append("".join(concat) + f"concat=n={len(shots)}:v=1:a=1[video][audio]")
        graph.append("[video]ass=filename=captions.ass[outv]")
        treatment=("loudnorm=I=-16:TP=-1.5:LRA=11" if info["has_audio"] and plan.audio_treatment != "mute" else "anull")
        if plan.audio_denoise: treatment+=',afftdn=nf=-25'
        treatment+=f',volume={plan.audio_volume:.4f},alimiter=limit=0.95'
        args_inputs=[]
        mix=['[audio]']
        if plan.sound_cues:
            from .sound_cues import write_cue
            for i,cue in enumerate(plan.sound_cues):
                cue_path=work/f'cue-{i}.wav';write_cue(cue.kind,cue_path)
                args_inputs.extend(['-i',str(cue_path)])
                delay=round(cue.start*1000)
                graph.append(f'[{i+1}:a]volume={cue.volume:.4f},adelay={delay}|{delay}[cue{i}]')
                mix.append(f'[cue{i}]')
            graph.append(''.join(mix)+f'amix=inputs={len(mix)}:duration=first:normalize=0[mixed]')
        graph.append(('[mixed]' if plan.sound_cues else '[audio]')+treatment+'[outa]')
        temporary_video = work / "render.mp4"
        encoder=encoding_args(mode)
        prefix=[ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", *safe_input_options(source), "-i", str(source),*args_inputs, "-filter_complex_threads", "2", "-filter_complex", ";".join(graph), "-map", "[outv]", "-map", "[outa]"]
        suffix=["-pix_fmt", "yuv420p", "-threads", "2", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", str(temporary_video)]
        timeout=max(600,int(sum(output_duration(s) for s in shots)*30))
        try:
            run_media(prefix+encoder+suffix,cwd=work,timeout=timeout)
        except PipelineError:
            if 'h264_nvenc' not in encoder:raise
            encoder=['-c:v','libx264','-preset','veryfast','-crf','22']
            run_media(prefix+encoder+suffix,cwd=work,timeout=timeout)
        rendered = probe_media(temporary_video)
        expected_duration = sum(output_duration(s) for s in shots)
        if rendered["width"] != canvas_w or rendered["height"] != canvas_h or abs(rendered["duration"] - expected_duration) > .3 or not rendered["has_audio"]:
            raise PipelineError("Rendered video failed dimension, duration, or audio validation")
        # A complete decode catches truncated/invalid files before exposing them.
        run_media([ffmpeg_binary(), "-v", "error", *safe_input_options(temporary_video), "-i", str(temporary_video), "-f", "null", "-"], timeout=max(120, int(expected_duration * 5)))
        shutil.copyfile(work / "captions.ass", captions_output)
        os.replace(temporary_video, output)
    rendered['source_aspect_ratio']=info['width']/info['height']
    rendered.update({"path": str(output), "subtitles_path": str(captions_output), "subtitle_words": subtitle_info["words"], "subtitle_synchronized": subtitle_info["synchronized"], "subtitle_timing": subtitle_info["timing"], "subtitle_phrases": subtitle_info["phrases"], "source_had_audio": info["has_audio"], "sha256": sha256_file(output), "decode_verified": True,'encoder':encoder[1]})
    return rendered
