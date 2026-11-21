"""Deterministic source-bound ranking tests; no inference or fabricated media."""
import copy
import json
import math

import pytest

from app.services.local_analysis import SourceAnalysis
from app.services.local_highlights import DEFAULT_WEIGHTS, FACTORS, rank_highlights, scoring_weights
from app.services.media import ConfigurationError, PipelineError


def source_analysis(duration=120.0, active_at=90.0, loud_at=10.0):
    times = [value for value in [10.0, 30.0, 50.0, 70.0, 90.0, 110.0] if value < duration]
    if not times:
        times = [duration / 2]
    scenes = [{"start": float(start), "end": float(min(duration, start + 20))} for start in range(0, math.ceil(duration), 20)]
    frames, findings, audio = [], [], []
    for index, timestamp in enumerate(times):
        active = abs(timestamp - active_at) < .001
        identifier = f"frame-{index}"
        scene = next(scene for scene in scenes if scene["start"] <= timestamp < scene["end"])
        frames.append({"timestamp": timestamp, "frame_index": int(timestamp * 30), "evidence_id": identifier, "brightness": .5, "sharpness": 120.0, "change": .85 if active else .02, "focus_x": .5, "focus_y": .5, "focus_confidence": "low"})
        findings.append({"timestamp": timestamp, "observation": "An arena opponent and aiming HUD are visible." if active else "A static menu panel is visible.", "visible_actions": ["Opponent visible", "Aiming HUD visible"] if active else [], "confidence": .9 if active else .6, "uncertainty": "A still image cannot establish an elimination or result.", "scene_start": scene["start"], "scene_end": scene["end"], "evidence_id": identifier, "evidence_type": "sampled_source_frame", "confidence_origin": "model_estimate_unverified"})
        audio.append({"start": timestamp - .5, "end": min(timestamp + .5, duration), "rms": .98 if timestamp == loud_at else .05})
    return SourceAnalysis(source_sha256="a" * 64, cache_identity="b" * 64, source={"duration": duration, "width": 1920, "height": 1080, "has_audio": True}, model={"name": "local-test-fixture", "digest": "controlled-fixture"}, settings={}, scenes=scenes, frames=frames, audio=audio, transcript={"text": "", "words": [], "segments": [], "provider": "controlled_fixture", "timing_source": "none"}, findings=findings, game_or_topic="Arena", topic_origin="user_supplied", topic_uncertainty="", warnings=[], limitations=["Controlled analysis fixture; no model ran."], analyzed_at="2026-11-17T12:00:00Z").model_dump()


def rules(**changes):
    return {"allowed_platforms": ["youtube"], "min_duration": 5.0, "max_duration": 30.0, "evidence": [{"field": "allowed_platforms", "quote": "YouTube", "source": "fixture"}], **changes}


def test_different_source_findings_change_the_selected_real_highlight():
    first = rank_highlights(source_analysis(active_at=90.0), rules())
    second = rank_highlights(source_analysis(active_at=30.0), rules())
    assert first["candidates"][0]["start"] <= 90 < first["candidates"][0]["end"]
    assert second["candidates"][0]["start"] <= 30 < second["candidates"][0]["end"]
    assert first["candidates"][0]["start"] != second["candidates"][0]["start"]
    assert "arena opponent" in first["candidates"][0]["observations"][0].lower()


def test_visual_evidence_beats_a_louder_static_menu_under_default_rubric():
    result = rank_highlights(source_analysis(active_at=90, loud_at=10), rules())
    best = result["candidates"][0]
    assert best["start"] <= 90 < best["end"]
    assert not best["start"] <= 10 < best["end"]
    assert best["factors"]["audio"]["score"] < 100
    assert "loudness" in best["factors"]["audio"]["explanation"].lower()


def test_gaming_creation_excludes_known_static_cards_without_filling_requested_count():
    result=rank_highlights(source_analysis(),rules(),target_duration=10,count=5,exclude_static_cards=True)
    assert len(result['candidates'])==1
    assert result['candidates'][0]['start']<=90<result['candidates'][0]['end']


def test_alternate_windows_around_one_finding_are_not_separate_moments():
    result=rank_highlights(source_analysis(),rules(),target_duration=10)
    candidates=result['candidates']
    assert len(candidates)==3
    for i,candidate in enumerate(candidates):
        assert all(not set(candidate['evidence_ids']).intersection(other['evidence_ids']) for other in candidates[i+1:])


def test_long_source_offers_three_distinct_source_ordered_bounded_windows():
    result = rank_highlights(source_analysis(), rules())
    candidates = result["candidates"]
    assert len(candidates) == 3
    for candidate in candidates:
        assert 0 <= candidate["start"] < candidate["end"] <= 120
        assert candidate["end"] - candidate["start"] == pytest.approx(20)
        assert candidate["segments"] == [{"start": candidate["start"], "end": candidate["end"]}]
        assert candidate["chronological"] is True
    for index, candidate in enumerate(candidates):
        for other in candidates[index + 1:]:
            overlap = max(0, min(candidate["end"], other["end"]) - max(candidate["start"], other["start"]))
            assert overlap / 20 <= .55


def test_short_source_does_not_create_duplicate_filler():
    result = rank_highlights(source_analysis(duration=12, active_at=10), rules(min_duration=1, max_duration=30))
    assert result["target_duration"] == 12
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["start"] == 0
    assert any("no duplicate filler" in warning for warning in result["warnings"])


def test_scores_are_explainable_finite_and_reference_actual_frame_findings():
    analysis = source_analysis()
    result = rank_highlights(analysis, rules())
    by_id = {frame["evidence_id"]: frame for frame in analysis["frames"]}
    for candidate in result["candidates"]:
        assert set(candidate["scores"]) == set(FACTORS) == set(candidate["factors"])
        assert all(math.isfinite(value) and 0 <= value <= 100 for value in candidate["scores"].values())
        assert candidate["score"] == pytest.approx(sum(candidate["scores"][key] * result["rubric"][key] for key in FACTORS), abs=.01)
        assert all(candidate["start"] <= by_id[identifier]["timestamp"] < candidate["end"] for identifier in candidate["evidence_ids"])
        assert candidate["model_uncertainty"]
    assert result["score_origin"] == "explainable_local_heuristic"
    assert result["publish_ready"] is False


def test_campaign_bounds_adjust_preference_and_impossible_minimum_is_explicit():
    result = rank_highlights(source_analysis(), rules(min_duration=25, max_duration=28), target_duration=20)
    assert result["target_duration"] == 25
    assert all(25 <= candidate["end"] - candidate["start"] <= 28 for candidate in result["candidates"])
    impossible = rank_highlights(source_analysis(duration=12), rules(min_duration=25, max_duration=28))
    assert impossible["candidates"] == [] and impossible["unavailable_reasons"]


@pytest.mark.parametrize("changes", [{"min_duration": 35, "max_duration": 20}, {"contradictions": ["Conflicting duration requirements"]}, {"automated_clipping_allowed": False}, {"ai_generated_allowed": False}, {"allowed_platforms": ["tiktok"]}])
def test_contradictions_prohibited_automation_and_disallowed_platform_cannot_be_ranked_as_eligible(changes):
    result = rank_highlights(source_analysis(), rules(**changes))
    assert result["candidates"] == []
    assert result["unavailable_reasons"] and result["publish_ready"] is False


def test_original_footage_and_unknown_campaign_semantics_stay_review_requirements():
    result = rank_highlights(source_analysis(), rules(original_footage_required=True, uncertainties=["Read source rights"]))
    assert result["candidates"]
    assert any("ownership" in message for message in result["review_requirements"])
    assert any("uncertainties" in message for message in result["review_requirements"])
    assert result["publish_ready"] is False


def test_rubric_normalization_and_environment_configuration(monkeypatch):
    supplied = {name: weight * 7 for name, weight in DEFAULT_WEIGHTS.items()}
    assert sum(scoring_weights(supplied).values()) == pytest.approx(1)
    monkeypatch.setenv("LOCAL_AI_HIGHLIGHT_WEIGHTS", json.dumps(supplied))
    assert scoring_weights() == scoring_weights(supplied)


@pytest.mark.parametrize("bad", [{"audio": 1}, {name: 0 for name in FACTORS}, {name: (1 if name == "audio" else 0) for name in FACTORS}, {**DEFAULT_WEIGHTS, "hook": float("nan")}, {**DEFAULT_WEIGHTS, "action": -1}, {**DEFAULT_WEIGHTS, "surprise": True}])
def test_bad_weights_and_audio_only_rubrics_are_rejected(bad):
    with pytest.raises(ConfigurationError):
        scoring_weights(bad)


@pytest.mark.parametrize("target", [float("nan"), float("inf"), -1, 0, True, "20"])
def test_invalid_target_durations_stop_before_selection(target):
    with pytest.raises(PipelineError):
        rank_highlights(source_analysis(), rules(), target)


def test_out_of_source_findings_duplicate_evidence_and_reversed_scenes_are_rejected():
    for mutate in [lambda value: value["findings"][0].update(timestamp=999), lambda value: value["frames"][1].update(evidence_id=value["frames"][0]["evidence_id"]), lambda value: value["scenes"].reverse()]:
        analysis = source_analysis()
        mutate(analysis)
        with pytest.raises(PipelineError):
            rank_highlights(analysis, rules())


def test_metadata_excerpt_does_not_include_words_removed_by_partial_cue_cuts():
    analysis = source_analysis(duration=12, active_at=10)
    analysis["transcript"] = {"text": "not in cut accurate words", "provider": "controlled_fixture", "timing_source": "provider_words", "words": [{"word": "accurate", "start": 1.0, "end": 2.0}, {"word": "words", "start": 10.0, "end": 11.0}], "segments": [{"start": 0.0, "end": 12.0, "text": "not in cut accurate words"}]}
    result = rank_highlights(analysis, rules(min_duration=1), target_duration=5)
    for candidate in result["candidates"]:
        assert "not in cut" not in candidate["transcript_excerpt"]


def test_ranking_is_deterministic_and_does_not_mutate_source_analysis():
    analysis = source_analysis(); before = copy.deepcopy(analysis)
    first = rank_highlights(analysis, rules())
    second = rank_highlights(analysis, rules())
    assert first == second and analysis == before
