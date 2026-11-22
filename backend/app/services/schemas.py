"""Validated contracts at the untrusted AI/media boundary."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .editor_schema import EditorState, CropBox


PLATFORMS = ("youtube", "tiktok", "instagram")
OUTPUT_PRESETS = {'portrait_1080': (1080,1920), 'portrait_720': (720,1280), 'square_1080': (1080,1080), 'landscape_1080': (1920,1080)}


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
    required_links: list[str] = Field(default_factory=list)
    game_name: str | None = None
    brand: str | None = None
    required_title: str | None = None
    required_title_phrases: list[str] = Field(default_factory=list)
    required_description_phrases: list[str] = Field(default_factory=list)
    required_on_video_text: list[str] = Field(default_factory=list)
    prohibited_platforms: list[Literal["youtube", "tiktok", "instagram"]] = Field(default_factory=list)
    resolution_requirements: list[str] = Field(default_factory=list)
    logo_requirements: list[str] = Field(default_factory=list)
    other_requirements: list[str] = Field(default_factory=list)
    prohibited_footage: list[str] = Field(default_factory=list)
    audience_restrictions: list[str] = Field(default_factory=list)
    automated_clipping_allowed: bool | None = None
    ai_generated_allowed: bool | None = None
    music_allowed: bool | None = None
    ai_voice_allowed: bool | None = None
    original_footage_required: bool | None = None
    paid_promotion_allowed: bool | None = None
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

    @model_validator(mode="after")
    def promotional_links(self):
        for value in self.required_links:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Required links must use HTTPS without credentials")
        return self


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
    crop_x_end: float | None = Field(default=None, ge=0, le=1)
    crop_y_end: float | None = Field(default=None, ge=0, le=1)
    transition: Literal["cut", "fade"] = "cut"
    effect: Literal["none", "contrast", "retro", "flash"] = "none"
    effect_intensity: float = Field(default=.5,ge=0,le=1)
    zoom_end: float | None = Field(default=None,ge=1,le=1.5)
    shake: float = Field(default=0,ge=0,le=.02)
    speed: float = Field(default=1,ge=.5,le=2)
    speed_end: float | None = Field(default=None,ge=.5,le=2)
    freeze: float = Field(default=0,ge=0,le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("Scene must have positive duration")
        return self


def expanded_scenes(scenes):
    """Four-step rate ramps keep video, audio and caption clocks identical."""
    result=[]
    for scene in scenes:
        if scene.speed_end is None or abs(scene.speed_end-scene.speed)<.001:
            result.append(scene);continue
        for i in range(4):
            start=scene.start+(scene.end-scene.start)*i/4
            end=scene.start+(scene.end-scene.start)*(i+1)/4
            data={**scene.model_dump(),'start':start,'end':end,'speed':scene.speed+(scene.speed_end-scene.speed)*(i+.5)/4,
                'speed_end':None,'freeze':scene.freeze if i==3 else 0,'transition':'cut',
                'effect':scene.effect if i==0 or scene.effect!='flash' else 'none'}
            for axis in ('crop_x','crop_y'):
                endpoint=getattr(scene,axis+'_end')
                endpoint=getattr(scene,axis) if endpoint is None else endpoint
                delta=endpoint-getattr(scene,axis)
                data[axis]=getattr(scene,axis)+delta*i/4
                data[axis+'_end']=getattr(scene,axis)+delta*(i+1)/4
            if scene.zoom_end is not None:
                data['zoom']=scene.zoom+(scene.zoom_end-scene.zoom)*i/4
                data['zoom_end']=scene.zoom+(scene.zoom_end-scene.zoom)*(i+1)/4
            result.append(Scene.model_validate(data))
    if len(result)>32:raise ValueError('Reduce rate ramps: at most32 rendered shot sections are allowed.')
    return result


def output_duration(scene):
    return (scene.end-scene.start)/scene.speed+scene.freeze


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


class SoundCue(Model):
    kind: Literal['click','soft_whoosh']
    start: float = Field(ge=0,le=600)
    volume: float = Field(default=.12,ge=0,le=.3)


class ClipPlan(Model):
    editor: EditorState | None = None
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
    generation_method: Literal["hosted_ai", "manual_local", "local_ai"] = "hosted_ai"
    score_origin: Literal["heuristic", "not_scored"] = "heuristic"
    manual_metadata: ManualMetadata | None = None
    audio_treatment: Literal["source", "mute"] = "source"
    framing: Literal["crop", "fit", "facecam"] = "crop"
    facecam: CropBox | None = None
    facecam_height: float = Field(default=.28, ge=.15, le=.45)
    output_preset: Literal['portrait_1080','portrait_720','square_1080','landscape_1080'] = 'portrait_1080'
    output_fps: Literal[30,60] = 30
    required_on_video_text: list[str] = Field(default_factory=list, max_length=6)
    audio_volume: float = Field(default=1,ge=0,le=2)
    audio_denoise: bool = False
    manual_captions: list[Segment] = Field(default_factory=list,max_length=100)
    caption_font: Literal['Arial','Noto Sans','DejaVu Sans'] = 'Arial'
    caption_color: str = Field(default='#FFFFFF',pattern='^#[0-9A-Fa-f]{6}$')
    caption_size: int | None = Field(default=None,ge=30,le=100)
    caption_margin: int = Field(default=350,ge=200,le=650)
    sound_cues: list[SoundCue] = Field(default_factory=list,max_length=6)
    text_overlays: list[Segment] = Field(default_factory=list,max_length=6)

    @model_validator(mode="after")
    def timeline(self):
        if self.framing == 'facecam' and self.facecam is None:
            raise ValueError('Facecam layout requires a crop rectangle in the original source')
        if self.end <= self.start:
            raise ValueError("Clip end must be after start")
        if self.end - self.start > 600:
            raise ValueError("A short-form clip must not exceed 10 minutes")
        for scene in self.scenes:
            if scene.start < self.start - .001 or scene.end > self.end + .001:
                raise ValueError("Scene is outside the selected source range")
        duration = sum(output_duration(s) for s in expanded_scenes(self.scenes))
        if self.editor:self.editor.check_duration(duration)
        if any(c.end>duration+.001 for c in self.manual_captions):
            raise ValueError('Manual caption cues use output seconds and must remain inside the rendered duration.')
        if any(c.end>duration+.001 for c in self.text_overlays):raise ValueError('Text overlays must remain inside the rendered timeline.')
        if any(c.start>=duration for c in self.sound_cues):raise ValueError('Sound cues must be inside the rendered output.')
        if sum(s.effect=='flash' for s in self.scenes)>2:raise ValueError('Use at most two restrained flash accents per clip.')
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
    title_candidates: list[dict] = Field(default_factory=list, max_length=5)
    generation_status: Literal['unknown','generated','manual','unavailable'] = 'unknown'


class Metadata(Model):
    youtube: PlatformMetadata
    tiktok: PlatformMetadata
    instagram: PlatformMetadata


class CandidateResponse(Model):
    clips: list[ClipPlan] = Field(min_length=1, max_length=5)
