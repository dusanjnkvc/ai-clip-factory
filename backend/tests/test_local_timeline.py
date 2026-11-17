"""Timeline assembly and evaluation boundaries using explicit model doubles."""
import copy
import json
import threading

import pytest
from pydantic import ValidationError

from app.services.local_highlights import rank_highlights
from app.services.local_timeline import (STYLE_NAMES, assemble_candidates, build_timelines,
    evaluation_schema, validate_timeline)
from app.services.media import PipelineError
from app.services.ollama_provider import InferenceCancelled
from test_local_highlights import rules, source_analysis


class EditorialProvider:
    """Exercises the evaluator contract; no real local inference is claimed."""
    def __init__(self, winner=1):
        self.winner = winner
        self.calls = []
        self.cancel_event = None

    def structured(self, schema, system, prompt, images=None):
        self.calls.append({"system": system, "prompt": prompt, "images": images})
        candidates = json.loads(prompt)["candidates"]
        return schema.model_validate({"evaluations": [{"candidate_id": candidate["id"], "score": 90.0 if index == self.winner else 45.0, "rationale": "Controlled editorial test score.", "uncertainty": "Test double; no model inference ran."} for index, candidate in enumerate(candidates)]})


def inputs(duration=120.0, **campaign):
    analysis = source_analysis(duration=duration)
    campaign_rules = rules(**campaign)
    return analysis, rank_highlights(analysis, campaign_rules), campaign_rules


def test_three_alternatives_have_distinct_real_windows_styles_and_purposeful_edits():
    analysis, ranking, campaign = inputs()
    candidates = assemble_candidates(analysis, ranking, campaign)
    assert [item["style"] for item in candidates] == list(STYLE_NAMES)
    assert len({(item["plan"]["start"], item["plan"]["end"]) for item in candidates}) == 3
    for candidate in candidates:
        plan = candidate["plan"]
        assert plan["show_hook"] and plan["hook"]
        assert plan["generation_method"] == "local_ai"
        assert sum(shot["end"] - shot["start"] for shot in plan["scenes"]) == pytest.approx(20)
        assert 0 <= plan["start"] < plan["end"] <= analysis["source"]["duration"]
        assert plan["edit_dna"]["scene_order"].startswith("Actual source order")
        assert all(shot["start"] <= shot["end"] for shot in plan["scenes"])
        assert any(identifier in plan["rationale"] for identifier in candidate["evidence_ids"])
    assert any(shot["effect"] == "contrast" for shot in candidates[0]["plan"]["scenes"])
    assert all(shot["transition"] == "fade" for shot in candidates[1]["plan"]["scenes"])


def test_shots_follow_actual_source_boundaries_without_reordering_or_repeats():
    analysis, ranking, campaign = inputs()
    for candidate in assemble_candidates(analysis, ranking, campaign):
        shots = candidate["plan"]["scenes"]
        assert all(left["end"] == right["start"] for left, right in zip(shots, shots[1:]))
        assert all(shot["start"] < shot["end"] for shot in shots)
        assert all(.3 <= shot["crop_x"] <= .7 and .35 <= shot["crop_y"] <= .65 and 1 <= shot["zoom"] <= 1.5 for shot in shots)


def test_crop_hints_stay_bounded_and_are_never_claimed_as_subject_tracking():
    analysis, ranking, campaign = inputs()
    for frame in analysis["frames"]:
        frame["focus_x"], frame["focus_y"] = 1.0, 0.0
    candidates = assemble_candidates(analysis, ranking, campaign)
    assert all(shot["crop_x"] == .7 and shot["crop_y"] == .35 for item in candidates for shot in item["plan"]["scenes"])
    assert all("tracking unverified" in item["plan"]["edit_dna"]["framing"] for item in candidates)


def test_genuine_speech_hook_is_retained_instead_of_invented_outcome():
    analysis, ranking, campaign = inputs()
    window = ranking["candidates"][0]
    analysis["transcript"] = {"text": "The menu opens here", "words": [], "segments": [{"start": window["start"] + 1, "end": window["start"] + 2, "text": "The menu opens here"}], "provider": "fixture", "timing_source": "uploaded_cues"}
    candidates = assemble_candidates(analysis, ranking, campaign)
    assert candidates[0]["plan"]["hook"] == "The menu opens here"
    assert candidates[0]["hook_origin"] == "source_transcript_excerpt"
    assert candidates[0]["plan"]["subtitles_enabled"] is True


def test_prohibited_source_music_is_muted_and_no_synthetic_audio_is_added():
    analysis, ranking, campaign = inputs(music_allowed=False)
    candidates = assemble_candidates(analysis, ranking, campaign)
    assert all(item["plan"]["audio_treatment"] == "mute" for item in candidates)
    altered = copy.deepcopy(candidates[0]["plan"]); altered["audio_treatment"] = "source"
    with pytest.raises(PipelineError, match="Mute source audio"):
        validate_timeline(altered, analysis, campaign)


def test_model_evaluation_can_choose_only_a_validated_existing_winner():
    analysis, ranking, campaign = inputs()
    provider = EditorialProvider(winner=1)
    result = build_timelines(analysis, ranking, campaign, provider=provider)
    assert result["winner_id"] == result["candidates"][1]["id"]
    assert result["winner_plan"] == result["candidates"][1]["plan"]
    assert len(provider.calls) == 1 and provider.calls[0]["images"] is None
    prompt = json.loads(provider.calls[0]["prompt"])
    assert len(prompt["candidates"]) == 3
    assert all("plan" not in item for item in prompt["candidates"])
    assert len(provider.calls[0]["prompt"]) < 10000
    assert result["publish_ready"] is False and result["review_requirements"]


def test_evaluation_schema_rejects_unknown_candidate_and_unbounded_text():
    schema = evaluation_schema(["candidate-a", "candidate-b"])
    with pytest.raises(ValidationError):
        schema.model_validate({"evaluations": [{"candidate_id": "invented", "score": 90, "rationale": "Bad", "uncertainty": "Unknown"}, {"candidate_id": "candidate-b", "score": 80, "rationale": "Other", "uncertainty": "Unknown"}]})
    with pytest.raises(ValidationError):
        schema.model_validate({"evaluations": [{"candidate_id": "candidate-a", "score": 90, "rationale": "x" * 181, "uncertainty": "Unknown"}, {"candidate_id": "candidate-b", "score": 80, "rationale": "Other", "uncertainty": "Unknown"}]})


def test_model_cannot_omit_a_candidate_by_repeating_another():
    class DuplicateProvider(EditorialProvider):
        def structured(self, schema, system, prompt, images=None):
            identifiers = [item["id"] for item in json.loads(prompt)["candidates"]]
            return schema.model_validate({"evaluations": [{"candidate_id": identifiers[0], "score": 90.0, "rationale": "Repeated", "uncertainty": "Test"} for _ in identifiers]})
    analysis, ranking, campaign = inputs()
    with pytest.raises(PipelineError, match="exactly once"):
        build_timelines(analysis, ranking, campaign, provider=DuplicateProvider())


def test_missing_model_does_not_choose_a_heuristic_fake_winner():
    class UnavailableProvider(EditorialProvider):
        def structured(self, *args, **kwargs):
            raise PipelineError("Local model unavailable")
    analysis, ranking, campaign = inputs()
    with pytest.raises(PipelineError, match="unavailable"):
        build_timelines(analysis, ranking, campaign, provider=UnavailableProvider())


def test_cancelled_job_never_calls_evaluator():
    event = threading.Event(); event.set()
    provider = EditorialProvider()
    with pytest.raises(InferenceCancelled):
        build_timelines(*inputs(), provider=provider, cancel=event)
    assert provider.calls == []


def test_short_footage_keeps_one_honest_alternative():
    analysis, ranking, campaign = inputs(duration=12, min_duration=1)
    result = build_timelines(analysis, ranking, campaign, provider=EditorialProvider(winner=0))
    assert len(result["candidates"]) == 1
    assert result["winner_plan"]["end"] <= 12


def test_wrong_source_ranking_unknown_evidence_and_changed_campaign_stop_assembly():
    analysis, ranking, campaign = inputs()
    other = copy.deepcopy(ranking); other["source_sha256"] = "c" * 64
    with pytest.raises(PipelineError, match="different source"):
        assemble_candidates(analysis, other, campaign)
    other = copy.deepcopy(ranking); other["candidates"][0]["evidence_ids"] = ["nonexistent-frame"]
    with pytest.raises(PipelineError, match="unavailable evidence"):
        assemble_candidates(analysis, other, campaign)
    with pytest.raises(PipelineError, match="prohibits"):
        assemble_candidates(analysis, ranking, {**campaign, "automated_clipping_allowed": False})


def test_cosmetic_candidate_id_changes_cannot_hide_repeated_source_footage():
    analysis, ranking, campaign = inputs()
    repeated = copy.deepcopy(ranking["candidates"][0]); repeated["id"] = "cosmetically-different-id"
    ranking["candidates"][1] = repeated
    with pytest.raises(PipelineError, match="Near-duplicate"):
        assemble_candidates(analysis, ranking, campaign)


def test_post_evaluation_validation_rejects_reversed_timeline_and_invisible_hook():
    analysis, ranking, campaign = inputs()
    plan = assemble_candidates(analysis, ranking, campaign)[0]["plan"]
    changed = copy.deepcopy(plan); changed["show_hook"] = False
    with pytest.raises(PipelineError, match="visible"):
        validate_timeline(changed, analysis, campaign)
    changed = copy.deepcopy(plan); changed["scenes"] = [{**plan["scenes"][0], "start": plan["start"] + 2, "end": plan["end"]}, {**plan["scenes"][0], "start": plan["start"], "end": plan["start"] + 1}]
    with pytest.raises(PipelineError, match="chronology"):
        validate_timeline(changed, analysis, campaign)
