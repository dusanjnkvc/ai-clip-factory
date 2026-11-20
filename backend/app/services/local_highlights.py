"""Explainable ranking of real contiguous source windows, without new inference.

These scores combine measured features and explicitly uncertain frame findings.
They do not verify an event, narrative payoff, campaign eligibility, or virality.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from statistics import mean
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .local_analysis import Contract, SourceAnalysis
from .media import ConfigurationError, PipelineError
from .schemas import CampaignRules

FACTORS = ("hook", "action", "surprise", "continuity", "clarity", "audio", "audience", "campaign")
DEFAULT_WEIGHTS = {"hook": .18, "action": .16, "surprise": .10, "continuity": .18, "clarity": .14, "audio": .08, "audience": .08, "campaign": .08}


class Factor(Contract):
    score: float = Field(ge=0, le=100)
    explanation: str
    basis: Literal["measured", "model_assisted_unverified", "deterministic_rules", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list)


class SourceWindow(Contract):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("A highlight must have positive source duration")
        return self


class RankedHighlight(SourceWindow):
    id: str
    segments: list[SourceWindow] = Field(min_length=1, max_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    observations: list[str]
    transcript_excerpt: str
    model_uncertainty: list[str]
    score: float = Field(ge=0, le=100)
    scores: dict[str, float]
    factors: dict[str, Factor]
    chronological: Literal[True] = True


class HighlightRanking(Contract):
    method: Literal["timestamp_grounded_local_ranker_v1"] = "timestamp_grounded_local_ranker_v1"
    score_origin: Literal["explainable_local_heuristic"] = "explainable_local_heuristic"
    source_sha256: str
    analysis_identity: str
    source_duration: float = Field(gt=0)
    target_duration: float = Field(gt=0)
    candidates: list[RankedHighlight] = Field(max_length=3)
    rubric: dict[str, float]
    warnings: list[str]
    unavailable_reasons: list[str]
    review_requirements: list[str]
    publish_ready: Literal[False] = False


def scoring_weights(supplied: dict[str, float] | None = None) -> dict[str, float]:
    if supplied is None and os.getenv("LOCAL_AI_HIGHLIGHT_WEIGHTS", "").strip():
        try:
            supplied = json.loads(os.environ["LOCAL_AI_HIGHLIGHT_WEIGHTS"])
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("LOCAL_AI_HIGHLIGHT_WEIGHTS must be a JSON object covering all eight factors") from exc
    chosen = DEFAULT_WEIGHTS if supplied is None else supplied
    if not isinstance(chosen, dict) or set(chosen) != set(FACTORS) or any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 for value in chosen.values()):
        raise ConfigurationError("Highlight weights must cover all eight factors with finite nonnegative numbers")
    total = sum(chosen.values())
    if total <= 0 or sum(value for name, value in chosen.items() if name != "audio") <= 0:
        raise ConfigurationError("Highlight ranking needs positive visual, narrative, or relevance weights; audio loudness alone is not meaningful evidence")
    return {name: value / total for name, value in chosen.items()}


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[\w]+", value.casefold()) if len(word) > 2 and word not in {"the", "and", "with", "this", "that", "from", "video", "source", "unidentified", "topic"}}


def _score(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _validated_analysis(raw: SourceAnalysis | dict) -> SourceAnalysis:
    try:
        analysis = SourceAnalysis.model_validate(raw.model_dump() if isinstance(raw, SourceAnalysis) else raw, strict=True)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PipelineError("Highlight ranking requires validated timestamped local source analysis") from exc
    if isinstance(analysis.source.get("duration"), bool):
        raise PipelineError("Source duration must be a real measured number")
    ids = [frame.evidence_id for frame in analysis.frames]
    if len(set(ids)) != len(ids) or any(not evidence_id for evidence_id in ids):
        raise PipelineError("Sampled frame evidence IDs must be unique and nonempty")
    if len({finding.evidence_id for finding in analysis.findings}) != len(analysis.findings):
        raise PipelineError("Frame findings must cite distinct sampled evidence")
    previous = 0.0
    for scene in analysis.scenes:
        if scene.start < previous - .05:
            raise PipelineError("Measured scenes must remain in chronological, nonoverlapping source order")
        previous = scene.end
    if any(frame.timestamp >= analysis.source["duration"] + .001 for frame in analysis.frames):
        raise PipelineError("Sampled evidence must occur before the source endpoint")
    return analysis


def _candidate_starts(analysis: SourceAnalysis, length: float) -> list[float]:
    duration = float(analysis.source["duration"])
    last = max(0.0, duration - length)
    clamp = lambda value: round(max(0.0, min(last, value)), 4)
    starts = {0.0, round(last, 4)}
    # Actual findings get priority; neither audio nor uniform slicing alone
    # establishes that a window is meaningful.
    for finding in analysis.findings:
        starts.update([clamp(finding.timestamp - min(2.5, length * .12)), clamp(finding.timestamp - length * .35)])
    for segment in analysis.transcript.segments[:120]:
        starts.add(clamp(segment.start))
    for sample in sorted(analysis.audio, key=lambda item: item.rms, reverse=True)[:12]:
        starts.add(clamp(sample.start - length * .25))
    scenes = analysis.scenes
    if len(scenes) > 100:
        scenes = [scenes[round(index * (len(scenes) - 1) / 99)] for index in range(100)]
    for scene in scenes:
        starts.update([clamp(scene.start), clamp(scene.end - length)])
    # A bounded grid makes different windows available even with sparse scenes.
    slots = min(60, max(1, math.ceil(duration / max(1.0, length / 2))))
    starts.update(clamp(last * index / slots) for index in range(slots + 1))
    return sorted(starts)


def _rank_window(analysis: SourceAnalysis, rules: dict, start: float, length: float, weights: dict, audience: str) -> RankedHighlight | None:
    end = min(float(analysis.source["duration"]), start + length)
    findings = [item for item in analysis.findings if start <= item.timestamp < end]
    frames = [item for item in analysis.frames if start <= item.timestamp < end]
    if not findings or not frames:
        return None
    evidence = list(dict.fromkeys(item.evidence_id for item in findings))
    by_id = {frame.evidence_id: frame for frame in frames}
    # No words/labels are generated: these strings are the existing local model
    # observations, carried with their explicit uncertainty and sampled evidence.
    observations = list(dict.fromkeys(item.observation for item in findings))
    confidence = mean(item.confidence for item in findings)
    change = max(frame.change for frame in frames)
    action_support = mean(min(1.0, len(item.visible_actions) / 2) * item.confidence for item in findings)
    first = [frame for frame in frames if frame.timestamp <= start + min(3.0, length)]
    opening_change = max((frame.change for frame in first), default=change * .25)
    opening_findings = [item for item in findings if item.timestamp <= start + min(3.0, length)]
    opening_confidence = mean(item.confidence for item in opening_findings) if opening_findings else confidence * .25
    phrases = [segment for segment in analysis.transcript.segments if segment.end > start and segment.start < end]
    # Do not lend metadata words that the final cut omits at a cue boundary.
    if analysis.transcript.words:
        exact_text = " ".join(word.word for word in analysis.transcript.words if word.start >= start and word.end <= end)
    else:
        exact_text = " ".join(segment.text for segment in phrases if segment.start >= start and segment.end <= end)
    opening_speech = any(segment.start < start + 3 and segment.end > start for segment in phrases)
    audio = [sample.rms for sample in analysis.audio if sample.end > start and sample.start < end]
    source_peak = max((sample.rms for sample in analysis.audio), default=0.0)
    audio_value = 100 * ((max(audio) / source_peak) if audio and source_peak > 0 else 0.0)
    boundary_cuts = sum(start < scene.start < end for scene in analysis.scenes)
    speech_cuts = sum(segment.start < start < segment.end or segment.start < end < segment.end for segment in phrases)
    clarity = 100 * mean(.75 * frame.sharpness / (frame.sharpness + 80) + .25 * max(0.0, 1 - abs(frame.brightness - .5) * 2) for frame in frames)
    desired = _tokens(audience or analysis.game_or_topic)
    actual = _tokens(" ".join(observations) + " " + exact_text + " " + " ".join(action for finding in findings for action in finding.visible_actions))
    overlap = len(desired & actual) / len(desired) if desired else 0
    audience_score = 35 + 50 * overlap if desired else 35
    factors = {
        "hook": Factor(score=_score(100 * (.45 * opening_change + .35 * opening_confidence + .20 * int(opening_speech))), explanation="First-three-second sampled change, uncertain visible evidence, and actual speech coverage; no retention prediction.", basis="model_assisted_unverified", evidence_ids=[item.evidence_id for item in opening_findings]),
        "action": Factor(score=_score(100 * (.55 * change + .45 * action_support)), explanation="Measured frame-change proxy combined with confidence-weighted visible actions. Sparse still frames do not verify continuous gameplay events.", basis="model_assisted_unverified", evidence_ids=evidence),
        "surprise": Factor(score=_score(change * 100), explanation="Largest measured visual-change proxy within this window. A visual jump does not establish narrative surprise or a result.", basis="measured", evidence_ids=[frame.evidence_id for frame in frames if frame.change == change]),
        "continuity": Factor(score=_score(100 - min(35, boundary_cuts * 4) - min(30, speech_cuts * 15)), explanation="The window retains uninterrupted source chronology; visual boundaries and clipped speech reduce the score. Semantic coherence still needs evaluation.", basis="measured", evidence_ids=evidence),
        "clarity": Factor(score=_score(clarity), explanation="Sampled edge detail and exposure estimate source readability; this does not verify HUD, logos, or subject visibility.", basis="measured", evidence_ids=list(by_id)),
        "audio": Factor(score=_score(audio_value), explanation="Actual peak RMS relative to this source. Loudness is only supporting evidence and cannot independently establish a highlight.", basis="measured" if audio else "unknown", evidence_ids=[]),
        "audience": Factor(score=_score(audience_score), explanation="Lexical overlap of supplied audience/topic with existing observations and transcript; audience appeal is unverified.", basis="model_assisted_unverified" if desired else "unknown", evidence_ids=evidence),
        "campaign": Factor(score=65 if rules.get("evidence") else 40, explanation="This source window satisfies checked numeric duration bounds. Content, branding, permissions, original footage, and campaign interpretation remain human-review tasks.", basis="deterministic_rules", evidence_ids=[]),
    }
    scores = {name: factor.score for name, factor in factors.items()}
    identifier = hashlib.sha256(f"{analysis.source_sha256}:{start:.4f}:{end:.4f}".encode()).hexdigest()[:20]
    uncertainty = list(dict.fromkeys([item.uncertainty for item in findings if item.uncertainty] + ["Sampled model observations and the ranking do not verify a complete event or coherent payoff."]))
    return RankedHighlight(id=identifier, start=start, end=end, segments=[SourceWindow(start=start, end=end)], evidence_ids=evidence, observations=observations, transcript_excerpt=exact_text, model_uncertainty=uncertainty, score=_score(sum(scores[name] * weights[name] for name in FACTORS)), scores=scores, factors=factors)


def rank_highlights(analysis: SourceAnalysis | dict, rules: dict | None = None, target_duration: float = 20, *, weights: dict[str, float] | None = None, count: int = 3, audience: str = "", platform: str = "youtube") -> dict:
    """Rank up to three different source-grounded, chronological windows."""
    measured = _validated_analysis(analysis)
    raw_rules = {} if rules is None else rules
    try:
        checked_rules = CampaignRules.model_validate(raw_rules, strict=True).model_dump()
    except (ValidationError, ValueError, TypeError) as exc:
        raise PipelineError("Highlight ranking requires valid campaign rules") from exc
    if isinstance(target_duration, bool) or not isinstance(target_duration, (int, float)) or not math.isfinite(target_duration) or target_duration <= 0:
        raise PipelineError("Target highlight duration must be a finite positive number")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 3:
        raise PipelineError("Choose one to three ranked highlight windows")
    if platform not in {"youtube", "tiktok", "instagram"}:
        raise PipelineError("Choose a supported short-video platform")
    if not isinstance(audience, str) or len(audience) > 1000:
        raise PipelineError("The supplied audience must be text of at most 1,000 characters")
    rubric = scoring_weights(weights)
    source_duration = float(measured.source["duration"])
    minimum = max(1.0, checked_rules.get("min_duration") or 1.0)
    maximum = min(600.0, source_duration, checked_rules.get("max_duration") or 600.0)
    length = max(1.0, min(maximum, max(minimum, float(target_duration))))
    unavailable = []
    if minimum > maximum + .001:
        unavailable.append("The real source and campaign bounds cannot support a valid short-video duration.")
    if checked_rules.get("contradictions"):
        unavailable.append("Resolve contradictory campaign rules before automatic scene selection.")
    if checked_rules.get("automated_clipping_allowed") is False or checked_rules.get("ai_generated_allowed") is False:
        unavailable.append("The campaign prohibits automated clipping or AI-generated edits. AUTO CREATE cannot bypass this restriction with a note.")
    if checked_rules.get("allowed_platforms") and platform not in checked_rules["allowed_platforms"]:
        unavailable.append("The selected platform is not permitted by the supplied campaign rules.")
    reviews = ["Review semantic accuracy, source rights, narrative context, crop/readability, and all campaign terms before publishing."]
    if checked_rules.get("original_footage_required") is True:
        reviews.append("Original creator footage is required; source analysis alone does not establish ownership or that the required footage is used.")
    if not checked_rules.get("allowed_platforms"):
        reviews.append("Permitted publishing platforms have not been established by a campaign brief.")
    if checked_rules.get("uncertainties"):
        reviews.append("Campaign uncertainties require evidence-backed review.")
    warnings = list(dict.fromkeys([*measured.warnings, "Ranking uses explainable heuristic proxies, not verified events, view predictions, or proof of campaign eligibility."]))
    if abs(length - target_duration) > .01:
        warnings.append("The requested duration was adjusted to the actual source and campaign bounds.")
    selected: list[RankedHighlight] = []
    if not unavailable:
        candidates = [_rank_window(measured, checked_rules, start, length, rubric, audience) for start in _candidate_starts(measured, length)]
        candidates = sorted((candidate for candidate in candidates if candidate is not None), key=lambda candidate: (-candidate.score, candidate.start, candidate.end))
        for candidate in candidates:
            if all(not set(candidate.evidence_ids).intersection(previous.evidence_ids) and
                max(0.0, min(candidate.end, previous.end) - max(candidate.start, previous.start)) / min(candidate.end - candidate.start, previous.end - previous.start) <= .55 for previous in selected):
                selected.append(candidate)
            if len(selected) == count:
                break
        if not selected:
            unavailable.append("No real source window contains timestamped frame findings for the requested duration.")
        elif len(selected) < count:
            warnings.append(f"Only {len(selected)} sufficiently different evidence-backed source windows are available; no duplicate filler was generated.")
    return HighlightRanking(source_sha256=measured.source_sha256, analysis_identity=measured.cache_identity, source_duration=source_duration, target_duration=length, candidates=selected, rubric=rubric, warnings=warnings, unavailable_reasons=unavailable, review_requirements=reviews).model_dump()
