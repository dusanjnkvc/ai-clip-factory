"""Measured local footage analysis plus explicitly uncertain local model findings.

Only locally decoded JPEGs reach the loopback Ollama provider. Sparse frames do
not establish continuous action, exact event boundaries, authorship, or claims.
Speech recognition uses CPU int8 by default and is released before vision work.
"""
from __future__ import annotations

import base64
import gc
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from ..config import settings
from . import media
from .media import ConfigurationError, PipelineError
from .ollama_provider import InferenceCancelled, OllamaProvider
from .schemas import Transcript

ANALYZER_VERSION = "local-source-v1"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SceneBoundary(Contract):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("A measured scene must have positive duration")
        return self


class MeasuredFrame(Contract):
    timestamp: float = Field(ge=0)
    frame_index: int = Field(ge=0)
    evidence_id: str
    brightness: float = Field(ge=0, le=1)
    sharpness: float = Field(ge=0)
    change: float = Field(ge=0, le=1)
    focus_x: float = Field(ge=0, le=1)
    focus_y: float = Field(ge=0, le=1)
    focus_confidence: Literal["low"] = "low"


class AudioSample(Contract):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    rms: float = Field(ge=0, le=1)


class FrameObservation(Contract):
    timestamp: float = Field(ge=0)
    observation: str = Field(min_length=1, max_length=300)
    visible_actions: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=3)
    confidence: float = Field(ge=0, le=1)
    uncertainty: str = Field(max_length=200)


class VisionBatch(Contract):
    observations: list[FrameObservation] = Field(min_length=1, max_length=4)
    game_or_topic: str = Field(default="", max_length=100)
    topic_uncertainty: str = Field(default="", max_length=160)


def vision_batch_schema(timestamps: list[float]) -> type[VisionBatch]:
    """Constrain generation to exactly the bounded source frames in this call."""
    if not 1 <= len(timestamps) <= 4 or len(set(timestamps)) != len(timestamps):
        raise ValueError("A vision batch needs one to four distinct sampled timestamps")
    if any(not math.isfinite(value) or value < 0 for value in timestamps):
        raise ValueError("Vision timestamps must be finite source times")
    observation = create_model("SampledFrameObservation", __base__=FrameObservation,
                               timestamp=(Literal[tuple(timestamps)], ...))
    return create_model("BoundedSourceVisionBatch", __base__=VisionBatch,
                        observations=(list[observation], Field(min_length=len(timestamps), max_length=len(timestamps))))


class Finding(FrameObservation):
    scene_start: float = Field(ge=0)
    scene_end: float = Field(gt=0)
    evidence_id: str
    evidence_type: Literal["sampled_source_frame"] = "sampled_source_frame"
    confidence_origin: Literal["model_estimate_unverified"] = "model_estimate_unverified"


class SourceAnalysis(Contract):
    schema_version: Literal["local-source-v1"] = ANALYZER_VERSION
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source: dict
    model: dict
    settings: dict
    scenes: list[SceneBoundary] = Field(min_length=1, max_length=2000)
    frames: list[MeasuredFrame] = Field(min_length=1, max_length=48)
    audio: list[AudioSample] = Field(default_factory=list, max_length=7200)
    transcript: Transcript
    findings: list[Finding] = Field(min_length=1, max_length=48)
    game_or_topic: str
    topic_origin: Literal["user_supplied", "local_model_unverified"]
    topic_uncertainty: str
    warnings: list[str]
    limitations: list[str]
    analyzed_at: str
    cached: bool = False

    @model_validator(mode="after")
    def source_bounds(self):
        duration = self.source.get("duration")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("Source duration must be measured and finite")
        evidence = {frame.evidence_id: frame for frame in self.frames}
        for scene in self.scenes:
            if scene.end > duration + .05:
                raise ValueError("A measured scene is outside the source")
        for frame in self.frames:
            if frame.timestamp >= duration + .05:
                raise ValueError("A sampled frame is outside the source")
        for finding in self.findings:
            frame = evidence.get(finding.evidence_id)
            if frame is None or abs(frame.timestamp - finding.timestamp) > .001:
                raise ValueError("A finding must cite a real sampled frame")
            if not finding.scene_start <= finding.timestamp < finding.scene_end + .05 or finding.scene_end > duration + .05:
                raise ValueError("A finding scene is outside its evidence")
        for item in [*self.transcript.words, *self.transcript.segments]:
            if item.end > duration + .05:
                raise ValueError("Transcription extends beyond the source")
        for sample in self.audio:
            if sample.end > duration + .05 or sample.end <= sample.start:
                raise ValueError("Audio samples must fit the source")
        return self


def _setting(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if not low <= value <= high:
        raise ConfigurationError(f"{name} must be between {low} and {high}")
    return value


def _check(cancel=None):
    cancelled = cancel.is_set() if hasattr(cancel, "is_set") else cancel() if callable(cancel) else False
    if cancelled:
        raise InferenceCancelled("Local source analysis cancelled; original media is preserved.")


def _dependencies():
    try:
        import cv2
        import numpy as np
        from scenedetect import SceneManager, ContentDetector, open_video
    except ImportError as exc:
        raise ConfigurationError("Install backend/requirements-local-ai.txt for local OpenCV and PySceneDetect analysis.") from exc
    return cv2, np, SceneManager, ContentDetector, open_video


def detect_scenes(path: Path, duration: float, cancel=None) -> list[dict]:
    """Bounded downscaled PySceneDetect scan, separate from semantic inference."""
    _, _, SceneManager, ContentDetector, open_video = _dependencies()
    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(ContentDetector(threshold=27.0, min_scene_len=15))
    finished = threading.Event()
    interruption: list[str] = []
    deadline = time.monotonic() + _setting("LOCAL_AI_SCENE_TIMEOUT_SECONDS", 600, 10, 3600)

    def watch():
        while not finished.wait(.1):
            try:
                _check(cancel)
            except InferenceCancelled:
                interruption.append("cancelled")
                manager.stop()
                return
            if time.monotonic() > deadline:
                interruption.append("timeout")
                manager.stop()
                return

    watcher = threading.Thread(target=watch, name="acf-scenes-cancel", daemon=True)
    watcher.start()
    try:
        _check(cancel)
        with open_video(str(path), backend="opencv") as video:
            manager.detect_scenes(video=video, show_progress=False)
            pairs = manager.get_scene_list(start_in_scene=True)
    finally:
        finished.set()
        watcher.join(timeout=.5)
    _check(cancel)
    if interruption:
        raise PipelineError("Local scene analysis exceeded its time limit; no partial analysis was accepted.")
    boundaries = [0.0, *[float(end.seconds) for _, end in pairs if 0 < end.seconds < duration - .03], duration]
    boundaries = sorted(set(round(value, 4) for value in boundaries))
    if len(boundaries) > 2001:
        raise PipelineError("Too many scene boundaries for one local job. Use a shorter source.")
    return [{"start": start, "end": end} for start, end in zip(boundaries, boundaries[1:]) if end > start]


def sampling_times(duration: float, scenes: list[dict], count: int) -> list[float]:
    """Cover the whole source, then add representative measured scene interiors."""
    count = min(48, max(1, count))
    uniform_count = max(1, math.ceil(count / 2))
    uniform = [duration * (index + .5) / uniform_count for index in range(uniform_count)]
    candidates = [(scene["start"] + scene["end"]) / 2 for scene in scenes]
    chosen = list(uniform)
    while len(chosen) < count and candidates:
        best = max(candidates, key=lambda value: min(abs(value - prior) for prior in chosen))
        candidates.remove(best)
        if all(abs(best - prior) > .08 for prior in chosen):
            chosen.append(best)
    for index in range(count):
        value = duration * (index + .5) / count
        if len(chosen) < count and all(abs(value - prior) > .08 for prior in chosen):
            chosen.append(value)
    return sorted(round(min(max(0, timepoint), max(0, duration - .08)), 4) for timepoint in chosen)


def sample_frames(path: Path, times: list[float], duration: float, cancel=None, max_side=None) -> tuple[list[dict], list[dict]]:
    cv2, np, *_ = _dependencies()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise PipelineError("OpenCV could not decode the local source video")
    frames, images, prior = [], [], None
    decoded_indices = set()
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if not math.isfinite(fps) or fps <= 0:
        capture.release()
        raise PipelineError("The local decoder did not supply a valid frame rate")
    try:
        for requested in times:
            _check(cancel)
            capture.set(cv2.CAP_PROP_POS_MSEC, requested * 1000)
            ok, frame = capture.read()
            if not ok:
                raise PipelineError("A representative source frame could not be decoded")
            index = max(0, round(capture.get(cv2.CAP_PROP_POS_FRAMES)) - 1)
            if index in decoded_indices:
                continue
            decoded_indices.add(index)
            timestamp = min(duration - .001, max(0, index / fps))
            height, width = frame.shape[:2]
            if max_side is not None:
                if not isinstance(max_side,int) or not 128<=max_side<=640:raise PipelineError('Bound the model sample dimensions between128 and640 pixels.')
                scale=min(1,max_side/max(width,height))
                frame=cv2.resize(frame,(max(2,round(width*scale)),max(2,round(height*scale))))
            else:
                frame = cv2.resize(frame, (min(512, width), max(2, round(height * min(512, width) / width))))
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (160, 90))
            edges = cv2.absdiff(small, cv2.GaussianBlur(small, (5, 5), 0)).astype(np.float32)
            total = float(edges.sum())
            focus_x = float((edges * np.arange(160)[None, :]).sum() / total / 159) if total else .5
            focus_y = float((edges * np.arange(90)[:, None]).sum() / total / 89) if total else .5
            change = float(np.abs(small.astype(np.float32) - prior).mean() / 255) if prior is not None else 0.0
            prior = small.astype(np.float32)
            encoded, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 72])
            if not encoded:
                raise PipelineError("The decoded source frame could not be encoded locally")
            frame_hash = hashlib.sha256(jpeg.tobytes()).hexdigest()[:16]
            record = MeasuredFrame(timestamp=round(timestamp, 4), frame_index=index, evidence_id=f"frame:{index}:{frame_hash}", brightness=float(small.mean() / 255), sharpness=float(cv2.Laplacian(gray, cv2.CV_64F).var()), change=change, focus_x=min(1, max(0, focus_x)), focus_y=min(1, max(0, focus_y))).model_dump()
            frames.append(record)
            images.append({"timestamp": record["timestamp"], "data_url": "data:image/jpeg;base64," + base64.b64encode(jpeg.tobytes()).decode("ascii")})
    finally:
        capture.release()
    if not frames:
        raise PipelineError("No source frames were decoded")
    return frames, images


def audio_rms(path: Path, duration: float, cancel=None) -> list[dict]:
    """Stream one-second PCM windows; loudness is not an event classifier."""
    import array
    args = [media.ffmpeg_binary(), "-v", "error", *media.safe_input_options(path), "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False)
    samples = []
    finished = threading.Event()
    interrupted = []
    deadline = time.monotonic() + min(900, max(60, duration * 3))

    def watch():
        while not finished.wait(.1):
            try:
                _check(cancel)
            except InferenceCancelled:
                interrupted.append("cancelled")
                process.kill()
                return
            if time.monotonic() > deadline:
                interrupted.append("timeout")
                process.kill()
                return

    watcher = threading.Thread(target=watch, name="acf-audio-cancel", daemon=True)
    watcher.start()
    try:
        while True:
            _check(cancel)
            chunk = process.stdout.read(16000)
            if not chunk:
                break
            values = array.array("h")
            values.frombytes(chunk[:len(chunk) // 2 * 2])
            if not values:
                continue
            start = len(samples)
            end = min(duration, start + len(values) / 8000)
            if end > start:
                samples.append({"start": float(start), "end": float(end), "rms": math.sqrt(sum((value / 32768) ** 2 for value in values) / len(values))})
            if len(samples) > 7200:
                raise PipelineError("Audio measurement exceeds the bounded local source length")
        process.communicate(timeout=15)
        _check(cancel)
        if interrupted:
            raise PipelineError("Source audio measurement exceeded its time limit")
        if process.returncode != 0:
            raise PipelineError("FFmpeg could not decode source audio for local measurements")
    finally:
        finished.set()
        watcher.join(timeout=.5)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)
    return samples


def _validate_transcript(raw: dict, duration: float) -> dict:
    transcript = Transcript.model_validate(raw).model_dump()
    if any(item["end"] > duration + .05 for field in ("words", "segments") for item in transcript[field]):
        raise PipelineError("The supplied speech timestamps extend beyond the source")
    return transcript


def decode_audio_pcm(source_path: str | Path, duration: float, cancel=None):
    """Decode pinned local media into bounded 16 kHz mono float32 samples.

    Faster-whisper accepts a NumPy waveform directly. Using the application's
    existing FFmpeg boundary avoids PyAV version-specific file-opening APIs and
    keeps container/protocol validation identical to the native renderer.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise ConfigurationError("Install requirements-local-ai.txt for local speech waveform processing") from exc
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 3600:
        raise PipelineError("Local speech decoding requires a measured source duration of at most one hour")
    _check(cancel)
    path = Path(source_path).resolve()
    args = [media.ffmpeg_binary(), "-v", "error", *media.safe_input_options(path), "-i", str(path), "-t", f"{duration:.6f}", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False)
    maximum_bytes = math.ceil((duration + .1) * 16000) * 4
    waveform = bytearray()
    finished = threading.Event()
    interrupted = []
    deadline = time.monotonic() + _setting("LOCAL_WHISPER_DECODE_TIMEOUT_SECONDS", 300, 10, 1800)

    def watch():
        while not finished.wait(.1):
            reason = None
            try:
                _check(cancel)
            except InferenceCancelled:
                reason = "cancelled"
            if reason is None and time.monotonic() >= deadline:
                reason = "timeout"
            if reason:
                interrupted.append(reason)
                try:
                    process.kill()
                except OSError:
                    pass
                return

    watcher = threading.Thread(target=watch, name="acf-speech-decode-cancel", daemon=True)
    watcher.start()
    try:
        while True:
            _check(cancel)
            chunk = process.stdout.read(65536)
            if not chunk:
                break
            if len(waveform) + len(chunk) > maximum_bytes:
                raise PipelineError("Decoded speech audio exceeded its measured-duration memory bound")
            waveform.extend(chunk)
        process.communicate(timeout=15)
        _check(cancel)
        if interrupted:
            raise PipelineError("Local speech audio decoding exceeded its time limit")
        if process.returncode != 0:
            raise PipelineError("FFmpeg could not decode the source speech audio")
        if not waveform or len(waveform) % 4:
            raise PipelineError("FFmpeg returned an empty or incomplete speech waveform")
        # The array owns a reference to the byte buffer without a second copy of
        # a full-hour waveform (at most about 230 MB at this sample format).
        audio = np.frombuffer(waveform, dtype="<f4")
        if not np.isfinite(audio).all():
            raise PipelineError("Source speech audio contains invalid samples")
        return audio
    finally:
        finished.set()
        watcher.join(timeout=.5)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def transcribe_local(path: Path, info: dict, cancel=None, progress=None) -> dict:
    if not info["has_audio"]:
        return Transcript(provider="no_audio", timing_source="none").model_dump()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ConfigurationError("Install requirements-local-ai.txt for local Faster-whisper transcription") from exc
    _check(cancel)
    allow_download = os.getenv("LOCAL_AI_ALLOW_MODEL_DOWNLOAD", "false").lower() in {"true", "1", "yes"}
    model = None
    try:
        if progress:
            progress("Decoding actual source speech audio with local FFmpeg", 14)
        waveform = decode_audio_pcm(path, info["duration"], cancel)
        _check(cancel)
        model = WhisperModel(os.getenv("LOCAL_WHISPER_MODEL", "base"), device="cpu", compute_type="int8", cpu_threads=_setting("LOCAL_WHISPER_CPU_THREADS", 4, 1, 16), num_workers=1, download_root=str(settings.media_root / "models" / "faster-whisper"), local_files_only=not allow_download)
        segments, details = model.transcribe(waveform, beam_size=3, word_timestamps=True, vad_filter=True, condition_on_previous_text=False)
        words, phrases = [], []
        for segment in segments:
            _check(cancel)
            phrases.append({"start": float(segment.start), "end": float(segment.end), "text": segment.text.strip()})
            for word in segment.words or []:
                words.append({"start": float(word.start), "end": float(word.end), "word": word.word.strip()})
            if progress:
                progress("Transcribing actual source speech locally", 15 + min(19, int(segment.end / info["duration"] * 19)))
        return _validate_transcript({"text": " ".join(phrase["text"] for phrase in phrases), "language": details.language, "words": words, "segments": phrases, "provider": "faster_whisper_local_cpu_int8", "timing_source": "provider_words" if words else "none"}, info["duration"])
    except (ConfigurationError, PipelineError):
        raise
    except Exception as exc:
        raise ConfigurationError("Local speech recognition is unavailable. Install/cache LOCAL_WHISPER_MODEL, or explicitly allow its free model download with LOCAL_AI_ALLOW_MODEL_DOWNLOAD=true. No substitute transcript was created.") from exc
    finally:
        if model is not None:
            try:
                model.model.unload_model(to_cpu=False)
            except Exception:
                pass  # Deleting the owning recognizer still releases native state.
        del model
        gc.collect()


class LocalSourceAnalyzer:
    def __init__(self, provider=None, cache_dir: str | Path | None = None):
        self.provider = provider or OllamaProvider()
        self.cache_dir = Path(cache_dir) if cache_dir else settings.media_root / "analysis-cache"

    def analyze(self, source_path: str | Path, transcript: dict | None = None, *, game: str = "", context: str = "", cancel=None, progress: Callable[[str, int], None] | None = None, max_frames: int | None = None) -> dict:
        progress = progress or (lambda _stage, _percent: None)
        _check(cancel)
        path = Path(source_path).resolve()
        info = media.probe_media(path)
        if info["duration"] > _setting("MAX_SOURCE_DURATION_SECONDS", 3600, 1, 7200):
            raise PipelineError("Source exceeds MAX_SOURCE_DURATION_SECONDS")
        _dependencies()
        status = self.provider.status(require_vision=True)
        if not status.get("available"):
            raise ConfigurationError(status.get("error") or "The configured local vision model is unavailable")
        model_digest = status.get("digest")
        if not model_digest:
            raise ConfigurationError("Local model identity is unavailable; analysis was not generated")
        choices = {"max_frames": _setting("LOCAL_AI_MAX_FRAMES", 12, 1, 48), "batch_size": _setting("LOCAL_AI_FRAME_BATCH_SIZE", 1, 1, 4), "whisper_model": os.getenv("LOCAL_WHISPER_MODEL", "base"), "whisper_device": "cpu", "whisper_compute": "int8", "speech_decode": "ffmpeg_mono_16000_f32le_v1", "scene_detector": "pyscenedetect_content_27", "game": game[:160], "context": context[:4000], "context_size": status.get("context_size"), "analyzer": ANALYZER_VERSION}
        if max_frames is not None:
            if isinstance(max_frames,bool) or not isinstance(max_frames,int) or not 1<=max_frames<=48:
                raise PipelineError('Frame budget must be an integer from1 to48.')
            choices['max_frames']=max_frames
        source_hash = media.sha256_file(path)
        supplied = _validate_transcript(transcript, info["duration"]) if transcript is not None else None
        identity = hashlib.sha256(json.dumps({"source": source_hash, "model_digest": model_digest, "endpoint": status.get("endpoint"), "settings": choices, "supplied_transcript": supplied}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        cache = self.cache_dir / f"{identity}.json"
        if cache.is_file():
            try:
                cached = SourceAnalysis.model_validate_json(cache.read_text(encoding="utf-8"), strict=True)
                if cached.cache_identity == identity and cached.source_sha256 == source_hash:
                    cached.cached = True
                    progress("Loaded validated local source analysis", 100)
                    return cached.model_dump()
            except (ValueError, OSError):
                pass  # Invalid cache data is recomputed, never accepted as analysis.
        progress("Measured source metadata and file identity", 5)
        scenes = detect_scenes(path, info["duration"], cancel)
        progress(f"Measured {len(scenes)} source scenes", 12)
        self.provider.unload()
        speech = supplied if supplied is not None else transcribe_local(path, info, cancel, progress)
        _check(cancel)
        progress("Measuring local source audio", 35)
        audio = audio_rms(path, info["duration"], cancel) if info["has_audio"] else []
        times = sampling_times(info["duration"], scenes, choices["max_frames"])
        frames, images = sample_frames(path, times, info["duration"], cancel)
        progress(f"Decoded {len(frames)} representative source frames", 42)
        findings, guesses, topic_notes, analysis_notes = [], [], [], []

        def interpret(batch):
            _check(cancel)
            frame_times = [image["timestamp"] for image in batch]
            excerpts = [{**segment, "text": segment["text"][:500]} for segment in speech["segments"] if any(segment["start"] <= timestamp + 2 and segment["end"] >= timestamp - 2 for timestamp in frame_times)][:4]
            schema = vision_batch_schema(frame_times)
            try:
                response = self.provider.structured(schema, "Return one brief observation for EACH supplied frame, exactly once, using its exact timestamp. Use at most 45 words in observation and 20 words in uncertainty; never produce exhaustive descriptions. Mention only visible source evidence. Describe webpage/store/menu/trailer/non-game content honestly, without assuming gameplay, wins, kills, rewards, motion, or unreadable text. Use at most three terse visible_actions, or an empty list when a still cannot establish action. Confidence is an unverified estimate. Do not invent dialogue, results or unseen events. Topic/game may be empty when uncertain.", json.dumps({"source_duration": info["duration"], "sampled_timestamps": frame_times, "user_game_hint_untrusted": choices["game"], "context_untrusted": choices["context"][:1200], "nearby_actual_transcript": excerpts}, ensure_ascii=False), batch)
                return VisionBatch.model_validate(response.model_dump())
            except PipelineError as exc:
                if len(batch) <= 1 or "token limit" not in str(exc).lower():
                    raise
                # Retry smaller REAL evidence batches, never substitute results or
                # expand the context/VRAM allowance after a truncated response.
                analysis_notes.append("A vision batch reached its token limit; the same real frames were interpreted one at a time.")
                singles = [interpret([image]) for image in batch]
                return VisionBatch(observations=[item for single in singles for item in single.observations], game_or_topic=next((single.game_or_topic for single in singles if single.game_or_topic), ""), topic_uncertainty=next((single.topic_uncertainty for single in singles if single.topic_uncertainty), ""))

        try:
            if hasattr(cancel, "is_set") and hasattr(self.provider, "cancel_event"):
                self.provider.cancel_event = cancel
            for offset in range(0, len(images), choices["batch_size"]):
                _check(cancel)
                batch = images[offset:offset + choices["batch_size"]]
                data = interpret(batch)
                observed = set()
                for observation in data.observations:
                    match = next((frame for frame in frames[offset:offset + choices["batch_size"]] if abs(frame["timestamp"] - observation.timestamp) < .001), None)
                    if match is None or match["evidence_id"] in observed:
                        raise PipelineError("Local model findings did not cite each supplied source frame exactly once")
                    observed.add(match["evidence_id"])
                    scene = next(scene for scene in scenes if scene["start"] <= match["timestamp"] < scene["end"] + .001)
                    findings.append(Finding(**{**observation.model_dump(), "timestamp": match["timestamp"]}, scene_start=scene["start"], scene_end=scene["end"], evidence_id=match["evidence_id"]).model_dump())
                if len(observed) != len(batch):
                    raise PipelineError("The local model omitted source-frame evidence; no complete analysis was generated")
                if data.game_or_topic:
                    guesses.append(data.game_or_topic)
                if data.topic_uncertainty:
                    topic_notes.append(data.topic_uncertainty)
                progress(f"Interpreted {min(offset + len(batch), len(images))} of {len(images)} real sampled frames locally", 42 + int((offset + len(batch)) / len(images) * 50))
        finally:
            self.provider.unload()
        _check(cancel)
        warnings = list(dict.fromkeys(analysis_notes))
        if not info["has_audio"]:
            warnings.append("Source has no audio stream; no speech or audio events were invented.")
        if info["height"] < 1080:
            warnings.append("Source resolution is below the target export; upscaling cannot restore detail.")
        if any(frame["sharpness"] < 30 for frame in frames):
            warnings.append("Some sampled frames have low measured edge detail; inspect the actual source.")
        result = SourceAnalysis(source_sha256=source_hash, cache_identity=identity, source={key: value for key, value in info.items() if key != "path"}, model={"name": status.get("model"), "digest": model_digest, "provider": "ollama_local"}, settings=choices, scenes=scenes, frames=frames, audio=audio, transcript=speech, findings=findings, game_or_topic=choices["game"] or (guesses[0] if guesses else "Unidentified source topic"), topic_origin="user_supplied" if choices["game"] else "local_model_unverified", topic_uncertainty="; ".join(dict.fromkeys(topic_notes)), warnings=warnings, limitations=["Visual observations are uncertain local-model interpretations of representative still frames, not verified events or continuous subject tracking.", "Scene boundaries are measured visual cuts, not semantic event start/end times.", "OpenCV seek timestamps are frame-index/fps estimates; variable-frame-rate sources may need manual timing review.", "Crop hints use edge-weighted visual centroids and may miss faces, HUD, logos, or meaningful subjects.", "Audio RMS measures loudness only. Speech recognition and model text require review against the actual video."], analyzed_at=datetime.now(timezone.utc).isoformat()).model_dump()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.cache_dir, prefix=identity + ".", suffix=".tmp", delete=False) as stream:
            json.dump(result, stream, ensure_ascii=False)
            temporary = Path(stream.name)
        os.replace(temporary, cache)
        progress("Validated and cached real local source analysis", 100)
        return result


def analyze(source_path: str | Path, transcript: dict | None = None, **options) -> dict:
    return LocalSourceAnalyzer().analyze(source_path, transcript, **options)
