"""No-cost local contracts and real rendering using user-supplied cue fixtures."""

from pathlib import Path

import pytest

from app.services.local import LocalPipelineService, build_manual_plan, parse_subtitles
from app.services.media import ConfigurationError, PipelineError, ffmpeg_binary, render_clip, run_media, timeline_cues, write_subtitles
from app.services.provider import CloudProvider, free_mode_enabled
from app.services.schemas import ClipPlan, Transcript


def rules():
    return {"campaign_name": "User campaign", "allowed_platforms": ["youtube"],
            "required_hashtags": ["#campaign"], "required_mentions": ["@brand"],
            "required_disclosures": ["Paid partnership"], "draft_approval_required": False,
            "evidence": [{"field": "allowed_platforms", "quote": "Platforms: YouTube", "source": "brief"}]}


def test_default_free_guard_blocks_even_a_configured_api_key_before_http(monkeypatch):
    monkeypatch.delenv("FREE_MODE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-must-never-be-used")

    def no_network(*args, **kwargs):
        pytest.fail("Free mode must stop before constructing a network client")

    monkeypatch.setattr("app.services.provider.httpx.Client", no_network)
    assert free_mode_enabled() is True
    with pytest.raises(ConfigurationError, match="requests are disabled"):
        CloudProvider()._request("/chat/completions", json={})


@pytest.mark.parametrize("value", ["", "TRUE", "1", "typo", " true "])
def test_free_guard_fails_closed_for_unknown_or_enabled_values(monkeypatch, value):
    monkeypatch.setenv("FREE_MODE", value)
    assert free_mode_enabled() is True


def test_cloud_opt_in_still_requires_real_credentials(monkeypatch):
    monkeypatch.setenv("FREE_MODE", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="not configured"):
        CloudProvider().require_configured()


def test_local_campaign_fields_are_explicit_evidenced_and_always_reviewed(monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Local campaign preparation must not use a network client")
    monkeypatch.setattr("app.services.provider.httpx.Client", no_network)
    result = LocalPipelineService().analyze_campaign("Platforms: YouTube, TikTok\nDuration: 10–30 seconds\nRequired hashtags: #launch #demo\nDraft approval: not required")
    assert result["rules"]["allowed_platforms"] == ["youtube", "tiktok"]
    assert result["rules"]["min_duration"] == 10
    assert result["rules"]["max_duration"] == 30
    assert result["rules"]["required_hashtags"] == ["#launch", "#demo"]
    assert result["rules"]["draft_approval_required"] is False
    assert result["review_required"] is True and result["ai_used"] is False
    assert all(item["quote"] in "Platforms: YouTube, TikTok\nDuration: 10–30 seconds\nRequired hashtags: #launch #demo\nDraft approval: not required" for item in result["evidence"])
    assert result["usage"] == []


def test_local_does_not_turn_negative_or_ambiguous_mentions_into_permission():
    result = LocalPipelineService().analyze_campaign("Do not publish to TikTok. YouTube examples are attached. Do not use #ad. There are no listed approval rules.")
    assert result["rules"]["allowed_platforms"] == []
    assert result["rules"]["required_hashtags"] == []
    assert result["rules"]["draft_approval_required"] is None
    assert result["review_required"] is True


def test_conflicting_labeled_duration_is_not_silently_overridden():
    result = LocalPipelineService().analyze_campaign("Maximum duration: 30 seconds\nMaximum duration: 45 seconds")
    assert result["rules"]["max_duration"] == 30
    assert result["rules"]["contradictions"]


def test_srt_preserves_cue_times_without_inventing_words():
    result = parse_subtitles("1\n00:00:00,100 --> 00:00:00,800\n<i>User supplied</i> captions.\n\n2\n00:00:01,000 --> 00:00:01,900\nSecond cue.\n", "srt", 2)
    assert result["words"] == []
    assert result["segments"] == [{"start": .1, "end": .8, "text": "User supplied captions."}, {"start": 1, "end": 1.9, "text": "Second cue."}]
    assert result["timing_source"] == "uploaded_cues"
    assert result["provider"] == "manual_subtitle_upload"


def test_vtt_accepts_short_timestamps_identifiers_and_cue_settings():
    result = parse_subtitles("WEBVTT\n\nNOTE local fixture\nnot speech recognition\n\ncue-a\n00:00.100 --> 00:01.900 align:start\n<c.emphasis>Exact</c> cue.\n", "vtt", 2)
    assert result["segments"][0] == {"start": .1, "end": 1.9, "text": "Exact cue."}
    assert result["words"] == []


@pytest.mark.parametrize("content,kind", [
    ("1\n00:00:01,000 --> 00:00:00,500\nInvalid", "srt"),
    ("1\n00:00:00,000 --> 00:00:03,000\nOut of bounds", "srt"),
    ("1\n00:70:00,000 --> 00:71:00,000\nInvalid minutes", "srt"),
    ("text without timings", "srt"),
    ("00:00.000 --> 00:01.000\nMissing header", "vtt"),
    ("WEBVTT\nX-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0\n\n00:00.000 --> 00:01.000\nMapped", "vtt"),
])
def test_invalid_or_source_misaligned_captions_are_rejected(content, kind):
    with pytest.raises(PipelineError):
        parse_subtitles(content, kind, 2)


def test_manual_plan_records_actual_choices_and_no_ai_score():
    transcript = parse_subtitles("1\n00:00:01,000 --> 00:00:04,000\nSupplied source words", source_duration=10)
    plan = build_manual_plan({"start": 2, "end": 5, "crop_x": .8, "crop_y": .25, "zoom": 1.1,
                              "title": "My exact title", "description": "My factual description", "hashtags": ["#owned"]},
                             {"duration": 10, "filename": "owned.mp4"}, transcript, rules())
    assert plan["generation_method"] == "manual_local"
    assert plan["score_origin"] == "not_scored"
    assert set(plan["scores"].values()) == {0}
    assert plan["scenes"][0]["crop_x"] == .8
    assert plan["manual_metadata"]["description"] == "My factual description"
    assert plan["transcript_excerpt"] == "Supplied source words"
    assert "no AI analysis" in plan["rationale"]


@pytest.mark.parametrize("selection", [{"start": -1, "end": 2}, {"start": 2, "end": 2}, {"start": 0, "end": 11}, {"start": 0, "end": .5}, {"start": 0, "end": 2, "crop_x": 2}, {"start": float("nan"), "end": 2}])
def test_manual_timeline_is_validated_before_render(selection):
    with pytest.raises(PipelineError):
        build_manual_plan(selection, {"duration": 10}, {}, rules())


def test_free_transcription_does_not_claim_or_generate_speech(monkeypatch):
    monkeypatch.setattr("app.services.provider.httpx.Client", lambda *a, **k: pytest.fail("No network"))
    transcript = LocalPipelineService().transcribe("not-even-opened.mp4")
    assert transcript["text"] == "" and transcript["words"] == [] and transcript["segments"] == []
    assert transcript["provider"] == "manual_required"
    assert transcript["timing_source"] == "none"


def test_manual_metadata_preserves_user_text_and_required_campaign_text():
    service = LocalPipelineService()
    plan = build_manual_plan({"end": 2, "title": "My exact title", "description": "User-authored description.", "hashtags": ["#owned"]}, {"duration": 2}, {}, rules())
    metadata = service.generate_metadata(plan, rules())
    for platform in metadata.values():
        chosen = platform["variants"][platform["recommended_index"]]
        assert chosen["title"] == "My exact title"
        assert chosen["description"] == "#campaign @brand\n\nUser-authored description.\n\nPaid partnership"
        assert chosen["hashtags"] == ["#campaign", "#owned"]
        assert chosen["score"] == 0
        assert "Not AI generated" in chosen["reasoning"]


def test_cue_mapping_clips_and_reorders_intervals_without_word_interpolation(tmp_path):
    transcript = parse_subtitles("1\n00:00:00,000 --> 00:00:02,000\nFirst phrase\n\n2\n00:00:03,000 --> 00:00:05,000\nSecond phrase", source_duration=5)
    plan = build_manual_plan({"end": 5, "subtitle_style": "karaoke"}, {"duration": 5}, transcript, rules())
    plan["scenes"] = [{"start": 3.5, "end": 5}, {"start": 1, "end": 2}]
    validated = ClipPlan.model_validate(plan)
    cues = timeline_cues(validated, Transcript.model_validate(transcript))
    assert cues == [{"text": "Second phrase", "start": 0, "end": 1.5}, {"text": "First phrase", "start": 1.5, "end": 2.5}]
    path = tmp_path / "captions.ass"
    result = write_subtitles(validated, Transcript.model_validate(transcript), path)
    assert result["timing"] == "cue" and result["words"] == 0 and result["synchronized"] is True
    assert "\\kf" not in path.read_text(encoding="utf-8")


@pytest.mark.integration
def test_free_local_flow_renders_playable_clip_with_exact_uploaded_cue_times(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        pytest.fail("Free local render must never contact a cloud provider")
    monkeypatch.setattr("app.services.provider.httpx.Client", no_network)
    source = tmp_path / "authorized-local-test-source.mp4"
    run_media([ffmpeg_binary(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=15:duration=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
    transcript = parse_subtitles("1\n00:00:00,200 --> 00:00:01,500\nUploaded caption fixture\n", source_duration=2)
    service = LocalPipelineService()
    plan = service.build_manual_plan({"start": 0, "end": 2, "title": "Local render test"}, {"duration": 2}, transcript, rules())
    output = tmp_path / "local-clip.mp4"
    result = service.process_clip(source, plan, transcript, rules(), {"authorized": True, "confirmed": True, "attestation": "Generated test signals owned by this test."}, output)
    assert output.is_file() and output.stat().st_size > 10000
    assert result["render"]["decode_verified"] is True
    assert result["render"]["width"] == 1080 and result["render"]["height"] == 1920
    assert result["render"]["subtitle_words"] == 0
    assert result["render"]["subtitle_timing"] == "cue"
    captions = Path(result["render"]["subtitles_path"]).read_text(encoding="utf-8")
    assert "0:00:00.20,0:00:01.50" in captions
    assert "Uploaded caption fixture" in captions and "\\kf" not in captions
    assert result["usage"] == []
    assert result["compliance"]["status"] == "PASS"
    assert any("cue timestamps" in c["detail"] for c in result["compliance"]["checks"] if c["rule"] == "subtitle_sync")
    run_media([ffmpeg_binary(), "-v", "error", "-i", str(output), "-f", "null", "-"])
