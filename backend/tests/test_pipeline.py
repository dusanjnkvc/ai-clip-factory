"""Unit contracts plus a real FFmpeg encode/decode test.

The cloud-call unit doubles below test validation, not cloud integration readiness.
The FFmpeg fixture is generated here and has no third-party media rights.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services import ConfigurationError, PipelineError, PipelineService
from app.services.compliance import check_compliance
from app.services.media import ffmpeg_binary, probe_media, render_clip, run_media, safe_input_options, timeline_words, write_subtitles
from app.services.pipeline import near_duplicate
from app.services.provider import CloudProvider
from app.services.schemas import CampaignRules, ClipPlan, Metadata, Scores, Transcript


def sample_plan():
    return {
        "title": "A precise demonstration", "start": .2, "end": 2.0,
        "hook": "Watch the change", "rationale": "The selected action shows a self-contained transition.",
        "content_type": "general", "scenes": [
            {"start": .2, "end": 1.0, "crop_x": .45, "crop_y": .5, "zoom": 1, "rationale": "Track the action"},
            {"start": 1.0, "end": 2.0, "crop_x": .65, "crop_y": .5, "zoom": 1.1, "rationale": "Reveal the conclusion"},
        ],
        "subtitle_style": "karaoke", "subtitles_enabled": True, "show_hook": False,
        "edit_dna": {"hook_structure": "Immediate action", "scene_order": "Setup then reveal", "cut_timing": "At source action change", "framing": "Action centered", "typography": "Readable contextual captions", "subtitle_treatment": "Word-level highlighting", "visual_effects": "None needed", "audio_treatment": "Normalize source audio", "ending_structure": "Resolve the action"},
        "scores": {"hook_strength": 80, "engagement_potential": 70, "clarity": 90, "standalone_context": 85, "campaign_relevance": 60},
        "transcript_excerpt": "See the change now",
    }


def sample_transcript():
    return {"text": "See the change now", "words": [
        {"word": "See", "start": .25, "end": .5},
        {"word": "the", "start": .55, "end": .8},
        {"word": "change", "start": 1.1, "end": 1.5},
        {"word": "now", "start": 1.55, "end": 1.9},
    ], "provider": "manual_test_fixture"}


def sample_metadata():
    variant = {"title": "See this change", "description": "See the change. #ad @brand Paid partnership", "caption": "See the change. #ad @brand Paid partnership", "hashtags": ["#ad"], "keywords": ["change"], "opening_hook": "See the change", "call_to_action": "", "score": 80, "reasoning": "Accurate to the clip"}
    return {platform: {"variants": [copy.deepcopy(variant) for _ in range(3)], "recommended_index": 0} for platform in ("youtube", "tiktok", "instagram")}


def sample_rules():
    return {"campaign_name": "Test campaign", "allowed_platforms": ["youtube"], "min_duration": 1, "max_duration": 10, "draft_approval_required": False, "required_hashtags": ["#ad"], "required_mentions": ["@brand"], "required_disclosures": ["Paid partnership"], "evidence": [{"field": "allowed_platforms", "quote": "YouTube only", "source": "brief"}], "uncertainties": [], "contradictions": []}


def rendered_info():
    return {"duration": 1.8, "width": 1080, "height": 1920, "has_audio": True, "codec": "h264", "decode_verified": True, "subtitle_synchronized": True}


def rights():
    return {"authorized": True, "confirmed": True, "attestation": "I created the test fixture"}


class StubProvider:
    """Validation-only test double; never selected by application code."""
    def __init__(self, result):
        self.result = result
        self.usage = []

    def structured(self, schema, system, prompt, images=None):
        return schema.model_validate(self.result)


def test_cloud_configuration_is_required(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="not configured"):
        CloudProvider().require_configured()


def test_provider_rejects_insecure_remote_endpoint(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://untrusted.example/v1")
    with pytest.raises(ConfigurationError, match="HTTPS"):
        CloudProvider().require_configured()


def test_campaign_extraction_retains_evidence_and_unknowns():
    data = {"campaign_name": "Sample", "allowed_platforms": ["youtube"], "required_hashtags": ["#Launch"], "max_duration": 30, "evidence": [{"field": "allowed_platforms", "quote": "YouTube only", "source": "brief"}, {"field": "required_hashtags", "quote": "#Launch", "source": "brief"}, {"field": "max_duration", "quote": "30 seconds", "source": "brief"}]}
    result = PipelineService(StubProvider(data)).analyze_campaign("YouTube only. Maximum 30 seconds. Include #Launch.")
    assert result["rules"]["max_duration"] == 30
    assert result["evidence"][0]["verified_quote"] is True
    assert result["rules"]["draft_approval_required"] is None
    assert result["review_required"] is True


def test_campaign_extraction_flags_fabricated_quote():
    data = {"allowed_platforms": ["tiktok"], "draft_approval_required": False, "evidence": [{"field": "allowed_platforms", "quote": "TikTok only", "source": "brief"}]}
    result = PipelineService(StubProvider(data)).analyze_campaign("Only authorized clips are accepted.")
    assert result["evidence"][0]["verified_quote"] is False
    assert result["review_required"] is True


def test_url_is_reference_not_scraped():
    with pytest.raises(PipelineError, match="URL alone"):
        PipelineService().analyze_campaign("", "https://example.com/campaign")


def test_invalid_scene_and_nonfinite_coordinates_rejected():
    plan = sample_plan()
    plan["scenes"][0]["crop_x"] = float("nan")
    with pytest.raises(ValidationError):
        ClipPlan.model_validate(plan)
    plan = sample_plan()
    plan["scenes"][0]["end"] = 9
    with pytest.raises(ValidationError, match="outside"):
        ClipPlan.model_validate(plan)


def test_scoring_is_weighted_and_labeled_heuristic():
    scores = Scores.model_validate(sample_plan()["scores"])
    assert scores.weighted() == 78.25
    assert scores.weighted({"hook_strength": 1, "engagement_potential": 0, "clarity": 0, "standalone_context": 0, "campaign_relevance": 0}) == 80
    with pytest.raises(ValueError):
        scores.weighted({"clarity": -1})


def test_clip_selection_excludes_duplicate_scene_ranges(monkeypatch):
    monkeypatch.setenv("AI_VISION_ENABLED", "false")
    plan, duplicate = sample_plan(), sample_plan()
    duplicate["subtitle_style"] = "bold"  # Cosmetic changes are not uniqueness.
    service = PipelineService(StubProvider({"clips": [plan, duplicate]}))
    result = service.plan_clips(sample_transcript(), sample_rules(), {"duration": 3, "width": 640, "height": 360}, count=2)
    assert len(result) == 1
    assert result[0]["score_is_heuristic"] is True
    assert result[0]["transcript_excerpt"] == "See the change now"


def test_duplicate_detection_requires_substantive_difference():
    left, right = sample_plan(), sample_plan()
    right["edit_dna"]["typography"] = "A different font"
    assert near_duplicate(left, right)
    right["start"], right["end"] = 15, 20
    right["scenes"] = [{"start": 15, "end": 20}]
    right["transcript_excerpt"] = "An entirely different event happened later"
    assert not near_duplicate(left, right)


def test_subtitle_timeline_maps_reordered_scene_times(tmp_path):
    plan = sample_plan()
    plan["scenes"].reverse()
    plan = ClipPlan.model_validate(plan)
    words = timeline_words(plan, Transcript.model_validate(sample_transcript()))
    assert words[0]["word"] == "change"
    assert words[0]["start"] == pytest.approx(.1)
    assert words[2]["word"] == "See"
    assert words[2]["start"] == pytest.approx(1.05)
    path = tmp_path / "captions.ass"
    info = write_subtitles(plan, Transcript.model_validate(sample_transcript()), path)
    assert info["synchronized"] is True
    assert "\\kf" in path.read_text(encoding="utf-8")


def test_subtitle_untrusted_text_cannot_inject_ass_tags(tmp_path):
    transcript = sample_transcript()
    transcript["words"][0]["word"] = r"{\p1}malicious"
    path = tmp_path / "captions.ass"
    write_subtitles(ClipPlan.model_validate(sample_plan()), Transcript.model_validate(transcript), path)
    assert r"{\p1}" not in path.read_text(encoding="utf-8")


def test_word_crossing_cut_boundary_is_not_duplicated():
    transcript = {"words": [{"word": "boundary", "start": .9, "end": 1.1}]}
    words = timeline_words(ClipPlan.model_validate(sample_plan()), Transcript.model_validate(transcript))
    assert len(words) == 1


def test_punctuation_only_evidence_is_not_verified():
    data = {"allowed_platforms": ["youtube"], "evidence": [{"field": "allowed_platforms", "quote": "!!!", "source": "brief"}]}
    result = PipelineService(StubProvider(data)).analyze_campaign("YouTube only.")
    assert result["evidence"][0]["verified_quote"] is False


def test_metadata_corrects_required_text_for_all_variants():
    metadata = sample_metadata()
    for platform in metadata.values():
        for variant in platform["variants"]:
            variant.update({"description": "A truthful description", "caption": "An accurate caption", "hashtags": []})
    data = PipelineService(StubProvider(metadata)).generate_metadata(sample_plan(), sample_rules())
    for platform in data.values():
        for variant in platform["variants"]:
            assert "#ad" in variant["hashtags"]
            assert "@brand" in variant["caption"]
            assert "Paid partnership" in variant["description"]


def test_compliance_deterministic_pass_and_blocking_failures():
    result = check_compliance(sample_plan(), sample_metadata(), sample_rules(), rights(), rendered_info())
    assert result["status"] == "PASS"
    assert result["publish_ready"] is True
    media = rendered_info()
    media["duration"] = 30
    result = check_compliance(sample_plan(), sample_metadata(), sample_rules(), rights(), media)
    assert result["status"] == "FAIL"
    assert any(c["rule"] == "duration" and c["blocking"] for c in result["checks"])


def test_hashtag_substring_does_not_satisfy_campaign_rule():
    metadata = sample_metadata()
    for variant in metadata["youtube"]["variants"]:
        variant.update({"description": "#advertisement @brand Paid partnership", "caption": "#advertisement @brand Paid partnership", "hashtags": ["#advertisement"]})
    result = check_compliance(sample_plan(), metadata, sample_rules(), rights(), rendered_info())
    assert result["status"] == "FAIL"


def test_semantic_rules_require_identified_review_evidence():
    rules = sample_rules()
    rules["prohibited_content"] = ["No misleading claims"]
    result = check_compliance(sample_plan(), sample_metadata(), rules, rights(), rendered_info())
    assert result["status"] == "REVIEW_REQUIRED"
    result = check_compliance(sample_plan(), sample_metadata(), rules, rights(), rendered_info(), semantic_evidence={"content_restrictions": {"confirmed": True, "note": "I reviewed the actual clip", "reviewed_by": "reviewer-1", "reviewed_at": "2026-11-15T12:00:00Z"}})
    assert result["status"] == "PASS"
    # Review cannot bypass a measurable failure.
    info = rendered_info()
    info["width"] = 720
    result = check_compliance(sample_plan(), sample_metadata(), rules, rights(), info, semantic_evidence={"video_format": {"confirmed": True, "note": "Override", "reviewed_by": "reviewer-1", "reviewed_at": "2026-11-15T12:00:00Z"}})
    assert result["status"] == "FAIL"


def test_missing_rights_and_draft_approval_block_publication():
    rules = sample_rules()
    rules["draft_approval_required"] = True
    result = check_compliance(sample_plan(), sample_metadata(), rules, {}, rendered_info())
    assert result["status"] == "FAIL"
    result = check_compliance(sample_plan(), sample_metadata(), rules, rights(), rendered_info())
    assert result["status"] == "REVIEW_REQUIRED"
    result = check_compliance(sample_plan(), sample_metadata(), rules, rights(), rendered_info(), draft_approved=True)
    assert result["status"] == "PASS"


@pytest.mark.integration
def test_real_ffmpeg_vertical_clip_is_playable_with_synchronized_subtitles(tmp_path):
    source = tmp_path / "authorized-generated-fixture.mp4"
    run_media([ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2.2", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2.2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
    output = tmp_path / "clip.mp4"
    result = render_clip(source, sample_plan(), sample_transcript(), output)
    assert output.is_file() and output.stat().st_size > 10000
    assert result["width"] == 1080 and result["height"] == 1920
    assert result["duration"] == pytest.approx(1.8, abs=.1)
    assert result["has_audio"] and result["decode_verified"]
    assert result["subtitle_words"] == 4 and result["subtitle_synchronized"]
    assert Path(result["subtitles_path"]).is_file()
    assert source.is_file()
    # Independently decode the actual output, not an expected/mock artifact.
    run_media([ffmpeg_binary(), "-v", "error", "-i", str(output), "-f", "null", "-"])


@pytest.mark.integration
def test_transcript_cache_reuses_validated_words_after_real_audio_extraction(tmp_path):
    class TranscriptionContractDouble:
        base_url = "https://provider.invalid/v1"
        transcription_model = "timestamp-test-model"
        usage = []
        calls = 0

        def require_configured(self):
            pass

        def transcribe_audio(self, path):
            # Actual FFmpeg audio preparation happened; only the paid network
            # boundary is replaced for this contract test.
            assert Path(path).stat().st_size > 100
            self.calls += 1
            return {"text": "Test words", "language": "en", "words": [{"word": "Test", "start": .1, "end": .3}, {"word": "words", "start": .35, "end": .7}]}

    source = tmp_path / "transcription-fixture.mp4"
    run_media([ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=navy:size=160x90:duration=1", "-f", "lavfi", "-i", "sine=frequency=700:duration=1", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(source)])
    provider = TranscriptionContractDouble()
    service = PipelineService(provider)
    cache = tmp_path / "transcript.json"
    first = service.transcribe(source, cache)
    assert first["words"][0]["word"] == "Test"
    assert provider.calls == 1
    second = service.transcribe(source, cache)
    assert second["cached"] is True and provider.calls == 1
    cache.write_text("corrupted cache", encoding="utf-8")
    service.transcribe(source, cache)
    assert provider.calls == 2


def test_render_preserves_original_and_rejects_source_overwrite(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"original bytes")
    with pytest.raises(PipelineError, match="never overwrite"):
        render_clip(source, sample_plan(), sample_transcript(), source)
    assert source.read_bytes() == b"original bytes"


@pytest.mark.parametrize("payload", [
    b"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nhttp://127.0.0.1:9/internal-secret\n",
    b"<?xml version='1.0'?><MPD><BaseURL>http://169.254.169.254/latest/meta-data/</BaseURL></MPD>",
    b"ffconcat version 1.0\nfile '/etc/passwd'\n",
    b"v=0\no=- 0 0 IN IP4 127.0.0.1\ns=Untrusted\nc=IN IP4 127.0.0.1\n",
])
def test_disguised_playlists_rejected_before_any_subprocess_or_network(tmp_path, monkeypatch, payload):
    source = tmp_path / "disguised-upload.mp4"
    source.write_bytes(payload)

    def forbidden_process(*args, **kwargs):
        pytest.fail("Untrusted playlist must be rejected before FFmpeg or ffprobe starts")

    monkeypatch.setattr("app.services.media.subprocess.run", forbidden_process)
    with pytest.raises(PipelineError, match="playlists and remote references"):
        probe_media(source)


def test_iso_bmff_input_pins_demuxer_protocols_and_disables_external_tracks(tmp_path):
    source = tmp_path / "content-not-extension.bin"
    source.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp42")
    options = safe_input_options(source)
    assert options[options.index("-protocol_whitelist") + 1] == "file,pipe"
    assert options[options.index("-format_whitelist") + 1] == "mov"
    assert options[options.index("-f") + 1] == "mov"
    assert options[options.index("-enable_drefs") + 1] == "0"
    assert options[options.index("-use_absolute_path") + 1] == "0"


@pytest.mark.integration
def test_actual_matroska_input_works_with_restricted_demuxer(tmp_path):
    source = tmp_path / "authorized-generated-fixture.mkv"
    run_media([ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1", "-c:v", "libx264", "-preset", "ultrafast", "-f", "matroska", str(source)])
    options = safe_input_options(source)
    assert options[options.index("-f") + 1] == "matroska"
    info = probe_media(source)
    assert info["width"] == 320 and info["height"] == 180
    assert info["duration"] == pytest.approx(1, abs=.05)
