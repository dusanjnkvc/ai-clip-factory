"""Real media measurements; semantic responses below are controlled test doubles.

These tests never claim that a local model interpreted gameplay. Real Ollama
and representative authorized gaming acceptance are separate integration runs.
"""
import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services import media
from app.services.local_analysis import (LocalSourceAnalyzer, SourceAnalysis, VisionBatch,
    audio_rms, decode_audio_pcm, detect_scenes, sample_frames, sampling_times, transcribe_local, vision_batch_schema)
from app.services.media import ConfigurationError, PipelineError
from app.services.ollama_provider import InferenceCancelled


class MeasuredColorProvider:
    """Deterministic color observer testing provenance, not semantic inference."""
    def __init__(self, digest="local-test-digest"):
        self.digest = digest
        self.calls = []
        self.unloads = 0
        self.cancel_event = None

    def status(self, require_vision=False):
        return {"available": True, "model": "test-vision", "digest": self.digest, "endpoint": "http://127.0.0.1:11434", "context_size": 4096}

    def unload(self):
        self.unloads += 1

    def structured(self, schema, system, prompt, images):
        import base64
        import cv2
        import numpy as np
        self.calls.append(images)
        observations = []
        for image in images:
            frame = cv2.imdecode(np.frombuffer(base64.b64decode(image["data_url"].split(",", 1)[1]), dtype=np.uint8), cv2.IMREAD_COLOR)
            mean = frame.mean(axis=(0, 1))
            color = "red" if mean[2] > mean[0] else "blue"
            observations.append({"timestamp": image["timestamp"], "observation": f"Controlled test observer measured a {color} frame.", "visible_actions": [], "confidence": .5, "uncertainty": "Test double; no semantic model ran."})
        return schema.model_validate({"observations": observations, "game_or_topic": "Generated color fixture", "topic_uncertainty": "This is not gameplay analysis."})


def test_vision_generation_schema_bounds_exact_count_timestamps_and_verbosity():
    schema = vision_batch_schema([.25, 1.5])
    contract = schema.model_json_schema()
    observations = contract["properties"]["observations"]
    assert observations["minItems"] == observations["maxItems"] == 2
    item = contract["$defs"]["SampledFrameObservation"]["properties"]
    assert item["timestamp"]["enum"] == [.25, 1.5]
    assert item["observation"]["maxLength"] == 300
    assert item["uncertainty"]["maxLength"] == 200
    assert item["visible_actions"]["maxItems"] == 3
    assert item["visible_actions"]["items"]["maxLength"] == 120
    record = {"timestamp": .25, "observation": "A visible source frame.", "visible_actions": [], "confidence": .5, "uncertainty": "Still frame only."}
    with pytest.raises(ValidationError):
        schema.model_validate({"observations": [record]})
    with pytest.raises(ValidationError):
        schema.model_validate({"observations": [record, {**record, "timestamp": 999}]})
    with pytest.raises(ValidationError):
        schema.model_validate({"observations": [record, {**record, "timestamp": 1.5, "observation": "x" * 301}]})


@pytest.fixture
def two_scene_video(tmp_path):
    pytest.importorskip("cv2")
    pytest.importorskip("scenedetect")
    output = tmp_path / "two-scenes.mp4"
    media.run_media([media.ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "color=c=red:size=320x180:rate=30:duration=1", "-f", "lavfi", "-i", "color=c=blue:size=320x180:rate=30:duration=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[out]", "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)])
    return output


@pytest.fixture
def analyzer(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_AI_MAX_FRAMES", "4")
    monkeypatch.setenv("LOCAL_AI_FRAME_BATCH_SIZE", "2")
    return LocalSourceAnalyzer(MeasuredColorProvider(), tmp_path / "cache")


def test_real_scene_boundaries_follow_actual_color_cut(two_scene_video):
    scenes = detect_scenes(two_scene_video, 2)
    assert len(scenes) == 2
    assert scenes[0]["start"] == 0
    assert scenes[0]["end"] == pytest.approx(1, abs=.05)
    assert scenes[1]["end"] == 2


def test_real_frames_carry_distinct_pixels_and_bounded_source_evidence(two_scene_video):
    frames, images = sample_frames(two_scene_video, [.3, 1.3], 2)
    assert len(frames) == len(images) == 2
    assert frames[1]["change"] > .1
    assert frames[0]["brightness"] > frames[1]["brightness"]
    assert len({frame["evidence_id"] for frame in frames}) == 2
    assert all(0 <= frame["timestamp"] < 2 for frame in frames)
    assert all(image["data_url"].startswith("data:image/jpeg;base64,") for image in images)


def test_sampling_covers_source_and_stays_bounded():
    scenes = [{"start": 0, "end": 20}, {"start": 20, "end": 100}]
    times = sampling_times(100, scenes, 12)
    assert len(times) == 12 and times == sorted(times)
    assert times[0] < 10 and times[-1] > 90
    assert all(0 <= value < 100 for value in times)


def test_analysis_uses_real_measurements_no_audio_and_traceable_model_evidence(two_scene_video, analyzer):
    result = analyzer.analyze(two_scene_video)
    assert result["source"]["duration"] == pytest.approx(2, abs=.05)
    assert result["transcript"]["provider"] == "no_audio"
    assert result["transcript"]["words"] == result["audio"] == []
    assert len(result["scenes"]) == 2
    assert len(result["findings"]) == len(result["frames"]) == 4
    assert any("red frame" in finding["observation"] for finding in result["findings"])
    assert any("blue frame" in finding["observation"] for finding in result["findings"])
    for finding in result["findings"]:
        assert finding["confidence_origin"] == "model_estimate_unverified"
        assert finding["scene_start"] <= finding["timestamp"] < finding["scene_end"]
    assert analyzer.provider.unloads == 2
    assert all(len(batch) <= 2 for batch in analyzer.provider.calls)


def test_cache_uses_actual_source_model_settings_and_supplied_transcript(two_scene_video, analyzer):
    original = analyzer.analyze(two_scene_video)
    analyzer.provider.calls.clear()
    cached = analyzer.analyze(two_scene_video)
    assert cached["cached"] and not analyzer.provider.calls
    assert cached["cache_identity"] == original["cache_identity"]
    changed = analyzer.analyze(two_scene_video, game="A user-provided topic")
    assert changed["cache_identity"] != original["cache_identity"]
    assert changed["topic_origin"] == "user_supplied"
    analyzer.provider.digest = "different-installed-weights"
    assert analyzer.analyze(two_scene_video)["cache_identity"] != original["cache_identity"]


def test_corrupt_cache_is_recomputed_and_never_presented_as_inference(two_scene_video, analyzer):
    result = analyzer.analyze(two_scene_video)
    cache = analyzer.cache_dir / (result["cache_identity"] + ".json")
    data = json.loads(cache.read_text(encoding="utf-8"))
    data["findings"][0]["timestamp"] = 999
    cache.write_text(json.dumps(data), encoding="utf-8")
    analyzer.provider.calls.clear()
    replacement = analyzer.analyze(two_scene_video)
    assert not replacement["cached"] and analyzer.provider.calls
    assert replacement["findings"][0]["timestamp"] < 2


def test_missing_model_or_dependency_has_no_fallback(two_scene_video, analyzer, monkeypatch):
    monkeypatch.setattr(analyzer.provider, "status", lambda **_: {"available": False, "error": "Missing local weights"})
    with pytest.raises(ConfigurationError, match="Missing local weights"):
        analyzer.analyze(two_scene_video)
    assert not analyzer.provider.calls


def test_model_cannot_invent_timestamps_or_omit_frame_evidence(two_scene_video, analyzer, monkeypatch):
    def unsupported(schema, *_):
        # Deliberately bypass provider schema validation to test the analyzer's
        # independent source-evidence check as a second boundary.
        return VisionBatch.model_validate({"observations": [{"timestamp": 999, "observation": "Unsupported event", "visible_actions": [], "confidence": .9, "uncertainty": ""}]})
    monkeypatch.setattr(analyzer.provider, "structured", unsupported)
    with pytest.raises(PipelineError, match="cite each supplied source frame"):
        analyzer.analyze(two_scene_video)
    assert not list(analyzer.cache_dir.glob("*.json"))


def test_token_limited_batch_retries_same_real_frames_individually(two_scene_video, analyzer, monkeypatch):
    original = analyzer.provider.structured
    attempts = []
    def limited(schema, system, prompt, images):
        attempts.append(len(images))
        if len(images) > 1:
            raise PipelineError("Local model output reached its token limit.")
        return original(schema, system, prompt, images)
    monkeypatch.setattr(analyzer.provider, "structured", limited)
    result = analyzer.analyze(two_scene_video)
    assert attempts == [2, 1, 1, 2, 1, 1]
    assert len(result["findings"]) == len(result["frames"]) == 4
    assert all(len(batch) == 1 for batch in analyzer.provider.calls)
    assert any("one at a time" in warning for warning in result["warnings"])


def test_single_frame_token_failure_stops_without_substitute_analysis(two_scene_video, analyzer, monkeypatch):
    def limited(*_):
        raise PipelineError("Local model output reached its token limit.")
    monkeypatch.setattr(analyzer.provider, "structured", limited)
    with pytest.raises(PipelineError, match="token limit"):
        analyzer.analyze(two_scene_video)
    assert not list(analyzer.cache_dir.glob("*.json"))


def test_cancellation_preserves_source_without_caching_partial_results(two_scene_video, analyzer):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InferenceCancelled):
        analyzer.analyze(two_scene_video, cancel=cancel)
    assert two_scene_video.is_file()
    assert not analyzer.provider.calls
    assert not list(analyzer.cache_dir.glob("*.json"))


def test_uploaded_cues_preserve_exact_timing_and_reject_out_of_source_speech(two_scene_video, analyzer):
    cues = {"provider": "manual_subtitle_upload", "timing_source": "uploaded_cues", "text": "Supplied line", "segments": [{"start": .2, "end": .7, "text": "Supplied line"}], "words": []}
    result = analyzer.analyze(two_scene_video, cues)
    assert result["transcript"]["segments"] == cues["segments"]
    assert result["transcript"]["words"] == []
    cues["segments"][0]["end"] = 5
    with pytest.raises(PipelineError, match="beyond the source"):
        analyzer.analyze(two_scene_video, cues)


def test_actual_ffmpeg_audio_rms_is_not_an_invented_event(tmp_path):
    source = tmp_path / "sound.mp4"
    media.run_media([media.ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "color=c=green:size=160x90:rate=12", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
    samples = audio_rms(source, 2)
    assert len(samples) == 2
    assert all(.03 < sample["rms"] < .15 for sample in samples)
    assert samples[0]["start"] == 0 and samples[-1]["end"] == 2


def test_faster_whisper_uses_cpu_int8_no_download_and_real_returned_timestamps(monkeypatch, tmp_path):
    faster_whisper = pytest.importorskip("faster_whisper")
    np = pytest.importorskip("numpy")
    source = tmp_path / "actual-source-audio.mp4"
    media.run_media([media.ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "color=c=green:size=160x90:rate=12", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=8000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
    calls = {}
    class Model:
        def __init__(self, name, **options):
            calls.update(name=name, **options)
            self.model = SimpleNamespace(unload_model=lambda **_: calls.update(unloaded=True))
        def transcribe(self, audio, **options):
            assert isinstance(audio, np.ndarray) and audio.dtype == np.float32
            assert audio.ndim == 1 and abs(len(audio) - 32000) < 1600
            assert np.isfinite(audio).all() and float(np.std(audio)) > .03
            calls["actual_waveform_received"] = True
            calls["transcribe"] = options
            word = SimpleNamespace(start=.2, end=.7, word="Actual")
            segment = SimpleNamespace(start=.2, end=.7, text="Actual", words=[word])
            return iter([segment]), SimpleNamespace(language="en")
    monkeypatch.setattr(faster_whisper, "WhisperModel", Model)
    monkeypatch.delenv("LOCAL_AI_ALLOW_MODEL_DOWNLOAD", raising=False)
    result = transcribe_local(source, {"has_audio": True, "duration": 2})
    assert calls["device"] == "cpu" and calls["compute_type"] == "int8"
    assert calls["num_workers"] == 1 and calls["local_files_only"] is True
    assert calls["transcribe"]["word_timestamps"] and calls["unloaded"] and calls["actual_waveform_received"]
    assert result["words"] == [{"word": "Actual", "start": .2, "end": .7}]
    assert result["provider"] == "faster_whisper_local_cpu_int8"


def test_speech_decoder_uses_actual_mono_16khz_float32_waveform(tmp_path):
    np = pytest.importorskip("numpy")
    source = tmp_path / "stereo-source.mp4"
    media.run_media([media.ffmpeg_binary(), "-v", "error", "-f", "lavfi", "-i", "color=c=blue:size=160x90:rate=12", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-ac", "2", "-c:a", "aac", "-shortest", str(source)])
    audio = decode_audio_pcm(source, 1)
    assert audio.ndim == 1 and audio.dtype == np.float32
    assert abs(len(audio) - 16000) < 160
    assert .03 < float(np.sqrt(np.mean(audio ** 2))) < .15


def test_speech_decoder_rejects_unbounded_source_and_honors_cancellation(tmp_path):
    pytest.importorskip("numpy")
    with pytest.raises(PipelineError, match="at most one hour"):
        decode_audio_pcm(tmp_path / "unused.mp4", 3601)
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(InferenceCancelled):
        decode_audio_pcm(tmp_path / "unused.mp4", 2, cancelled)
