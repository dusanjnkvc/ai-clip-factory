"""Validated contracts at the untrusted AI/media boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PLATFORMS = ("youtube", "tiktok", "instagram")


class Model(BaseModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class Evidence(Model):
    field: str
    quote: str
    source: str = "brief"


class CampaignRules(Model):
    campaign_name: str = "Untitled campaign"
    campaign_type: Literal["cpm", "flat_fee", "retainer", "shared_pool", "draft_preapproval", "unknown"] = "unknown"
    allowed_platforms: list[Literal["youtube", "tiktok", "instagram"]] = Field(default_factory=list)
    min_duration: float | None = Field(default=None, ge=0, le=3600)
    max_duration: float | None = Field(default=None, gt=0, le=3600)
    required_hashtags: list[str] = Field(default_factory=list)
    required_mentions: list[str] = Field(default_factory=list)
    required_disclosures: list[str] = Field(default_factory=list)
    required_branding: list[str] = Field(default_factory=list)
    permitted_source_material: list[str] = Field(default_factory=list)
    prohibited_content: list[str] = Field(default_factory=list)
    audio_restrictions: list[str] = Field(default_factory=list)
    minimum_views: int | None = Field(default=None, ge=0)
    reward_per_1000: float | None = Field(default=None, ge=0)
    flat_fee: float | None = Field(default=None, ge=0)
    maximum_payout: float | None = Field(default=None, ge=0)
    currency: str | None = None
    draft_approval_required: bool | None = None
    submission_deadline: str | None = None
    submission_window_minutes: int | None = Field(default=None, ge=1, le=10080)
    submission_instructions: str | None = None
    submission_url: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class Word(Model):
    word: str = Field(max_length=200)
    start: float = Field(ge=0)
    end: float = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start:
            raise ValueError("Word end precedes its start")
        return self


class Segment(Model):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = ""

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Subtitle cue end must follow its start")
        return self


class Transcript(Model):
    text: str = ""
    language: str | None = None
    words: list[Word] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    provider: str = "cloud"
    timing_source: Literal["provider_words", "uploaded_cues", "none"] | None = None


class Scene(Model):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    crop_x: float = Field(default=0.5, ge=0, le=1)
    crop_y: float = Field(default=0.5, ge=0, le=1)
    zoom: float = Field(default=1, ge=1, le=1.5)
    rationale: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Scene must have positive duration")
        return self


class Scores(Model):
    hook_strength: float = Field(ge=0, le=100)
    engagement_potential: float = Field(ge=0, le=100)
    clarity: float = Field(ge=0, le=100)
    standalone_context: float = Field(ge=0, le=100)
    campaign_relevance: float = Field(ge=0, le=100)

    def weighted(self, weights: dict[str, float] | None = None) -> float:
        chosen = weights or {
            "hook_strength": .30, "engagement_potential": .25,
            "clarity": .20, "standalone_context": .15, "campaign_relevance": .10,
        }
        if set(chosen) != set(self.model_dump()) or any(v < 0 for v in chosen.values()) or sum(chosen.values()) <= 0:
            raise ValueError("Scoring weights must cover all five factors and have a positive sum")
        return round(sum(getattr(self, key) * value for key, value in chosen.items()) / sum(chosen.values()), 2)


class EditDNA(Model):
    hook_structure: str
    scene_order: str
    cut_timing: str
    framing: str
    typography: str
    subtitle_treatment: str
    visual_effects: str
    audio_treatment: str
    ending_structure: str


class ManualMetadata(Model):
    title: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=30)


class ClipPlan(Model):
    title: str = Field(min_length=1, max_length=160)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    hook: str = Field(default="", max_length=250)
    rationale: str = Field(min_length=1, max_length=3000)
    content_type: Literal["gaming", "podcast", "promotion", "general"] = "general"
    scenes: list[Scene] = Field(min_length=1, max_length=20)
    subtitle_style: Literal["clean", "bold", "podcast", "gaming", "karaoke"] = "clean"
    subtitles_enabled: bool = True
    show_hook: bool = False
    edit_dna: EditDNA
    scores: Scores
    transcript_excerpt: str = ""
    semantic_notes: list[str] = Field(default_factory=list)
    generation_method: Literal["hosted_ai", "manual_local"] = "hosted_ai"
    score_origin: Literal["heuristic", "not_scored"] = "heuristic"
    manual_metadata: ManualMetadata | None = None

    @model_validator(mode="after")
    def timeline(self):
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        if self.end - self.start > 600:
            raise ValueError("A short-form clip must not exceed 10 minutes")
        for scene in self.scenes:
            if scene.start < self.start - .001 or scene.end > self.end + .001:
                raise ValueError("Scene is outside the selected source range")
        duration = sum(s.end - s.start for s in self.scenes)
        if not 1 <= duration <= 600:
            raise ValueError("Rendered timeline must be between one second and ten minutes")
        return self


class MetadataVariant(Model):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    caption: str = Field(default="", max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    opening_hook: str = Field(default="", max_length=250)
    call_to_action: str = Field(default="", max_length=300)
    thumbnail_text: str | None = None
    score: float = Field(ge=0, le=100)
    reasoning: str = ""


class PlatformMetadata(Model):
    variants: list[MetadataVariant] = Field(min_length=3, max_length=3)
    recommended_index: int = Field(ge=0, le=2)


class Metadata(Model):
    youtube: PlatformMetadata
    tiktok: PlatformMetadata
    instagram: PlatformMetadata


class CandidateResponse(Model):
    clips: list[ClipPlan] = Field(min_length=1, max_length=5)
