"""Source-ordered local edit assembly and bounded model evaluation.

The model evaluates compact evidence-backed alternatives. It cannot introduce
timestamps, new events, footage, dialogue, effects, or an unvalidated winner.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, ValidationError, create_model

from .local_analysis import Contract, SourceAnalysis
from .local_highlights import FACTORS, HighlightRanking, _validated_analysis, scoring_weights
from .media import PipelineError
from .ollama_provider import InferenceCancelled, OllamaProvider
from .schemas import CampaignRules, ClipPlan

STYLE_NAMES = ("High-Energy Gaming", "Cinematic Storytelling", "Suspense and Payoff")


class Evaluation(Contract):
    candidate_id: str
    score: float = Field(ge=0, le=100)
    rationale: str = Field(min_length=1, max_length=180)
    uncertainty: str = Field(min_length=1, max_length=180)


class EvaluationBatch(Contract):
    evaluations: list[Evaluation] = Field(min_length=1, max_length=3)


def evaluation_schema(candidate_ids: list[str]) -> type[EvaluationBatch]:
    if not 1 <= len(candidate_ids) <= 3 or len(set(candidate_ids)) != len(candidate_ids):
        raise PipelineError("Timeline evaluation needs one to three distinct eligible candidate IDs")
    bounded = create_model("EligibleTimelineEvaluation", __base__=Evaluation, candidate_id=(Literal[tuple(candidate_ids)], ...))
    return create_model("BoundedTimelineEvaluations", __base__=EvaluationBatch, evaluations=(list[bounded], Field(min_length=len(candidate_ids), max_length=len(candidate_ids))))


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InferenceCancelled("Automatic timeline creation was cancelled; source media is preserved")


def _short_literal(value: str, maximum=90) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= maximum:
        return cleaned
    return cleaned[:maximum - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def _hook(analysis: SourceAnalysis, start: float, end: float) -> tuple[str, str]:
    # An exact supplied speech phrase has stronger provenance than a model's
    # description, but both still need context review before publication.
    phrases = [segment.text for segment in analysis.transcript.segments if segment.start >= start and segment.end <= end and segment.text.strip()]
    if phrases:
        return _short_literal(phrases[0]), "source_transcript_excerpt"
    findings = [item for item in analysis.findings if start <= item.timestamp < end]
    if not findings:
        raise PipelineError("A timeline hook must have source evidence")
    first = min(findings, key=lambda item: item.timestamp)
    return _short_literal(first.observation), "local_frame_observation_unverified"


def _boundaries(analysis: SourceAnalysis, start: float, end: float, style: str, intensity: str) -> list[float]:
    preferred = 7.0 if style == "Cinematic Storytelling" else 4.5 if style == "Suspense and Payoff" else 3.5
    preferred *= {"gentle": 1.4, "balanced": 1.0, "energetic": .8}[intensity]
    maximum_shots = min(10, max(1, round((end - start) / preferred)))
    genuine = [scene.start for scene in analysis.scenes if start + .65 < scene.start < end - .65]
    if not genuine:
        genuine = [frame.timestamp for frame in analysis.frames if start + 1.2 < frame.timestamp < end - 1.2 and frame.change >= .12]
    # Select measured boundaries nearest even pacing goals, without inventing a
    # semantic event or changing the order of the actual source.
    selected = []
    for index in range(1, maximum_shots):
        target = start + (end - start) * index / maximum_shots
        available = [value for value in genuine if value not in selected and all(abs(value - chosen) >= .65 for chosen in [start, end, *selected])]
        if available:
            selected.append(min(available, key=lambda value: abs(value - target)))
    return [start, *sorted(selected), end]


def _validate_ranking(analysis: SourceAnalysis, raw: dict) -> HighlightRanking:
    try:
        ranking = HighlightRanking.model_validate(raw, strict=True)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PipelineError("Automatic editing requires a validated local highlight ranking") from exc
    if ranking.source_sha256 != analysis.source_sha256 or ranking.analysis_identity != analysis.cache_identity or abs(ranking.source_duration - analysis.source["duration"]) > .05:
        raise PipelineError("The highlight ranking belongs to a different source or analysis settings")
    if ranking.unavailable_reasons or not ranking.candidates:
        raise PipelineError("Automatic scene selection is unavailable: " + "; ".join(ranking.unavailable_reasons or ["No eligible source windows"]))
    scoring_weights(ranking.rubric)
    evidence = {item.evidence_id: item.timestamp for item in analysis.findings}
    seen = set()
    windows = []
    for candidate in ranking.candidates:
        if candidate.id in seen or candidate.start < 0 or candidate.end > analysis.source["duration"] + .001:
            raise PipelineError("Duplicate or out-of-source highlight candidates cannot become edit plans")
        if not candidate.chronological or candidate.segments[0].start != candidate.start or candidate.segments[0].end != candidate.end:
            raise PipelineError("A highlight must preserve its actual continuous source range")
        if any(identifier not in evidence or not candidate.start <= evidence[identifier] < candidate.end for identifier in candidate.evidence_ids):
            raise PipelineError("A highlight cites unavailable evidence or evidence outside its source range")
        if set(candidate.scores) != set(FACTORS) or set(candidate.factors) != set(FACTORS):
            raise PipelineError("A highlight must retain all eight explainable scoring factors")
        if any(max(0.0, min(candidate.end, previous.end) - max(candidate.start, previous.start)) / min(candidate.end - candidate.start, previous.end - previous.start) > .55 for previous in windows):
            raise PipelineError("Near-duplicate source windows cannot become separate candidate edits")
        seen.add(candidate.id)
        windows.append(candidate)
    return ranking


def validate_timeline(plan: dict | ClipPlan, analysis: SourceAnalysis | dict, rules: dict | None = None) -> ClipPlan:
    """The deterministic boundary is checked both before and after evaluation."""
    measured = _validated_analysis(analysis)
    try:
        proposed = ClipPlan.model_validate(plan.model_dump() if isinstance(plan, ClipPlan) else plan, strict=True, extra="forbid")
        checked = CampaignRules.model_validate({} if rules is None else rules, strict=True).model_dump()
    except (ValidationError, ValueError, TypeError) as exc:
        raise PipelineError("The automatic timeline failed strict plan or campaign validation") from exc
    if checked.get("automated_clipping_allowed") is False or checked.get("ai_generated_allowed") is False:
        raise PipelineError("This campaign prohibits automatic clipping or AI-generated edits")
    if checked.get("contradictions"):
        raise PipelineError("Resolve contradictory campaign rules before automatic editing")
    if proposed.end > measured.source["duration"] + .001:
        raise PipelineError("An automatic timeline extends beyond the real source")
    if not proposed.show_hook or not proposed.hook.strip():
        raise PipelineError("An automatic edit requires a visible source-grounded opening text hook")
    last = proposed.start
    duration = 0.0
    for shot in proposed.scenes:
        if shot.start < last - .001:
            raise PipelineError("Automatic edits must preserve source chronology without repeated footage")
        last = shot.end
        duration += shot.end - shot.start
    if checked.get("min_duration") is not None and duration < checked["min_duration"] - .05 or checked.get("max_duration") is not None and duration > checked["max_duration"] + .05:
        raise PipelineError("The automatic timeline violates campaign duration bounds")
    if checked.get("music_allowed") is False and proposed.audio_treatment != "mute":
        raise PipelineError("Mute source audio when the campaign prohibits music; no automatic music absence is inferred")
    return proposed


def assemble_candidates(analysis: SourceAnalysis | dict, ranking: dict, rules: dict | None = None, *, intensity: str = "balanced") -> list[dict]:
    measured = _validated_analysis(analysis)
    if intensity not in {"gentle", "balanced", "energetic"}:
        raise PipelineError("Choose gentle, balanced, or energetic edit intensity")
    checked = CampaignRules.model_validate({} if rules is None else rules, strict=True).model_dump()
    ranked = _validate_ranking(measured, ranking)
    candidates = []
    for index, highlight in enumerate(ranked.candidates):
        style = STYLE_NAMES[index]
        boundaries = _boundaries(measured, highlight.start, highlight.end, style, intensity)
        scenes = []
        for number, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            nearby = [frame for frame in measured.frames if start <= frame.timestamp < end]
            if not nearby:
                nearby = [min(measured.frames, key=lambda frame: abs(frame.timestamp - (start + end) / 2))]
            first, last = nearby[0], nearby[-1]
            # Hints are deliberately restrained. An uncertain edge centroid is
            # not subject/HUD tracking; keep corrections bounded and explicit.
            x = min(.7, max(.3, first.focus_x))
            y = min(.65, max(.35, first.focus_y))
            zoom = 1.03 if style == "High-Energy Gaming" and intensity != "gentle" else 1.0
            scenes.append({"start": start, "end": end, "crop_x": x, "crop_y": y, "zoom": zoom, "crop_x_end": min(.7, max(.3, last.focus_x)), "crop_y_end": min(.65, max(.35, last.focus_y)), "transition": "fade" if style == "Cinematic Storytelling" else "cut", "effect": "contrast" if style == "High-Energy Gaming" else "none", "rationale": f"Chronological source shot {number + 1}; real source boundaries and low-confidence framing hints. Evidence: " + ", ".join(frame.evidence_id for frame in nearby)})
        hook, hook_origin = _hook(measured, highlight.start, highlight.end)
        audio = "mute" if checked.get("music_allowed") is False else "source"
        scores = highlight.scores
        identity = hashlib.sha256(f"{highlight.id}:{style}:{intensity}".encode()).hexdigest()[:20]
        plan = {
            "title": _short_literal(measured.game_or_topic, 70) + " · " + style,
            "start": highlight.start, "end": highlight.end, "hook": hook, "show_hook": True,
            "rationale": f"{style}: a measured, source-ordered {highlight.end - highlight.start:.1f}-second window. Cuts follow real scene boundaries or sampled visual changes; no event or result is invented. Evidence: " + ", ".join(highlight.evidence_ids),
            "content_type": "general", "scenes": scenes, "subtitle_style": "gaming" if style == "High-Energy Gaming" else "clean", "subtitles_enabled": bool(measured.transcript.words or measured.transcript.segments),
            "audio_treatment": audio,
            "edit_dna": {"hook_structure": f"Visible source-supported opening text ({hook_origin})", "scene_order": "Actual source order; no chronology reversal or repeated footage", "cut_timing": "; ".join(f"{shot['start']:.3f}–{shot['end']:.3f}" for shot in scenes), "framing": "Restrained edge-centroid crop motion; subject/HUD tracking unverified", "typography": "Readable native ASS opening hook and source-timed captions", "subtitle_treatment": "Actual local transcription word times or supplied cue intervals", "visual_effects": "Source contrast with measured cuts" if style == "High-Energy Gaming" else "Short shot fades" if style == "Cinematic Storytelling" else "Chronological measured cuts; no manufactured payoff", "audio_treatment": "Mute original audio" if audio == "mute" else "Normalize original source audio; no added music or synthetic voice", "ending_structure": "Preserve the genuine final source beat; semantic payoff is unverified"},
            "scores": {"hook_strength": scores["hook"], "engagement_potential": scores["action"], "clarity": scores["clarity"], "standalone_context": scores["continuity"], "campaign_relevance": scores["campaign"]},
            "transcript_excerpt": highlight.transcript_excerpt, "semantic_notes": [*highlight.model_uncertainty, *ranked.review_requirements, "A local model will compare candidate summaries; its evaluation does not establish semantic truth or campaign approval."], "generation_method": "local_ai", "score_origin": "heuristic",
        }
        validated = validate_timeline(plan, measured, checked)
        candidates.append({"id": identity, "style": style, "plan": validated.model_dump(), "evidence_ids": list(highlight.evidence_ids), "source_window_id": highlight.id, "rank_score": highlight.score, "hook_origin": hook_origin, "review_requirements": list(ranked.review_requirements)})
    return candidates


def build_timelines(analysis: SourceAnalysis | dict, ranking: dict, rules: dict | None = None, *, provider=None, intensity: str = "balanced", cancel=None) -> dict:
    measured = _validated_analysis(analysis)
    _check_cancel(cancel)
    candidates = assemble_candidates(measured, ranking, rules, intensity=intensity)
    evaluator = provider or OllamaProvider(cancel_event=cancel)
    if cancel is not None and hasattr(evaluator, "cancel_event"):
        evaluator.cancel_event = cancel
    compact = []
    for candidate in candidates:
        plan = candidate["plan"]
        cited = [item for item in measured.findings if item.evidence_id in candidate["evidence_ids"]]
        compact.append({"id": candidate["id"], "style": candidate["style"], "range": [plan["start"], plan["end"]], "shots": [[shot["start"], shot["end"]] for shot in plan["scenes"]], "hook": plan["hook"], "hook_origin": candidate["hook_origin"], "source_observations": [{"timestamp": item.timestamp, "observation": _short_literal(item.observation, 180), "uncertainty": _short_literal(item.uncertainty, 100)} for item in cited[:2]], "actual_speech_excerpt": _short_literal(plan["transcript_excerpt"], 300), "heuristic_score": candidate["rank_score"]})
    response = evaluator.structured(evaluation_schema([candidate["id"] for candidate in candidates]), "Evaluate ONLY the supplied candidate edits against their actual source evidence. Give exactly one assessment per allowed candidate ID. Prefer truthful readable hooks, continuity, useful source action, and supported context. A sparse frame does not establish a kill, win, reaction, product claim, or payoff. Do not reward invented claims or predict views. Scores are uncertain editorial heuristics, not campaign approval. Keep each rationale and uncertainty under 20 words.", json.dumps({"source_topic_untrusted": measured.game_or_topic, "topic_uncertainty": measured.topic_uncertainty, "candidates": compact, "campaign_semantics": "Require human review; numeric/automation boundaries were validated separately."}, ensure_ascii=False))
    _check_cancel(cancel)
    try:
        evaluated = evaluation_schema([candidate["id"] for candidate in candidates]).model_validate(response.model_dump(), strict=True)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PipelineError("Local model timeline evaluation failed its eligible-candidate boundary") from exc
    by_id = {item.candidate_id: item for item in evaluated.evaluations}
    if len(by_id) != len(candidates) or set(by_id) != {candidate["id"] for candidate in candidates}:
        raise PipelineError("Local model evaluation must cover each eligible timeline exactly once")
    # Winner selection cannot access an invented model timeline or unknown ID.
    winner = max(candidates, key=lambda candidate: (by_id[candidate["id"]].score, candidate["rank_score"], -candidate["plan"]["start"]))
    winner_plan = validate_timeline(winner["plan"], measured, rules).model_dump()
    return {"winner_plan": winner_plan, "winner_id": winner["id"], "candidates": candidates, "evaluations": evaluated.model_dump()["evaluations"], "selection_method": "bounded_local_model_evaluation_with_deterministic_preflight", "review_requirements": winner["review_requirements"], "publish_ready": False}
