"""Free local workflow: explicit editing choices and supplied subtitle cues.

This module performs no model inference, network request, or automatic speech
recognition. Suggested campaign fields come only from explicit labeled lines;
the original text remains the evidence and every extraction needs review.
"""

from __future__ import annotations

import copy
import math
import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from .media import PipelineError
from .pipeline import PipelineService
from .schemas import CampaignRules, ClipPlan, Metadata, PLATFORMS, Transcript


class _LocalProvider:
    def __init__(self):
        self.usage: list[dict] = []


class _PlainCaption(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "br":
            self.parts.append(" ")


def _plain_caption(text: str) -> str:
    parser = _PlainCaption()
    parser.feed(text)
    parser.close()
    return " ".join(unescape(" ".join(parser.parts)).replace("\x00", "").split())


def _cue_time(text: str) -> float:
    match = re.fullmatch(r"(?:(\d{2,}):)?(\d{2}):(\d{2})[,.](\d{3})", text.strip())
    if not match:
        raise PipelineError("Subtitle timestamps must use HH:MM:SS,mmm (SRT) or MM:SS.mmm/HH:MM:SS.mmm (VTT).")
    hours, minutes, seconds, millis = match.groups()
    if int(minutes) >= 60 or int(seconds) >= 60:
        raise PipelineError("Subtitle timestamp minutes and seconds must be below 60.")
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_subtitles(content: str, format: str = "srt", source_duration: float | None = None) -> dict:
    """Read exact cue times; never invent word-level timestamps or speech."""
    kind = format.lower().lstrip(".")
    if kind not in {"srt", "vtt"}:
        raise PipelineError("Upload an SRT or WebVTT subtitle file.")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise PipelineError("Subtitle files are limited to 2 MB.")
    if source_duration is not None and (not math.isfinite(source_duration) or source_duration <= 0):
        raise PipelineError("A valid source duration is required to validate subtitles.")
    text = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if kind == "vtt" and not text.startswith("WEBVTT"):
        raise PipelineError("A WebVTT file must begin with WEBVTT.")
    if "X-TIMESTAMP-MAP" in text:
        raise PipelineError("WebVTT timestamp maps are not supported. Export source-relative cue timestamps.")
    cues = []
    for block in re.split(r"\n[ \t]*\n", text.strip()):
        lines = block.splitlines()
        if kind == "vtt" and lines and lines[0].strip().split(" ", 1)[0] in {"WEBVTT", "NOTE", "STYLE", "REGION"}:
            continue
        time_lines = [index for index, line in enumerate(lines) if "-->" in line]
        if not time_lines:
            if any(line.strip() for line in lines):
                raise PipelineError("A subtitle cue is missing its start/end timestamp line.")
            continue
        if len(time_lines) != 1:
            raise PipelineError("Separate subtitle cues with a blank line.")
        index = time_lines[0]
        bounds = lines[index].split("-->")
        if len(bounds) != 2:
            raise PipelineError("Invalid subtitle cue timestamp line.")
        start = _cue_time(bounds[0].strip())
        end_part = bounds[1].strip().split()
        if not end_part:
            raise PipelineError("Subtitle cue end timestamp is missing.")
        end = _cue_time(end_part[0])
        if end <= start:
            raise PipelineError("Subtitle cue end must follow its start.")
        if source_duration is not None and end > source_duration + .05:
            raise PipelineError("Subtitle cues extend beyond the source video duration.")
        caption = _plain_caption(" ".join(lines[index + 1:]))
        if len(caption) > 2000:
            raise PipelineError("Each subtitle cue is limited to 2,000 visible characters.")
        if caption:
            cues.append({"start": start, "end": end, "text": caption})
        if len(cues) > 10000:
            raise PipelineError("Subtitle files are limited to 10,000 cues.")
    if not cues:
        raise PipelineError("No timed subtitle cues were found.")
    cues.sort(key=lambda cue: (cue["start"], cue["end"]))
    return Transcript(text=" ".join(cue["text"] for cue in cues), words=[], segments=cues,
                      provider="manual_subtitle_upload", timing_source="uploaded_cues").model_dump()


def _selection_text(transcript: dict, start: float, end: float) -> str:
    speech = Transcript.model_validate(transcript)
    if speech.words:
        return " ".join(word.word for word in speech.words if start <= (word.start + word.end) / 2 < end)
    # A cue partially intersecting the edit is displayed as a complete supplied
    # phrase; its words are never assigned fabricated individual timings.
    return " ".join(cue.text for cue in speech.segments if cue.end > start and cue.start < end)


def build_manual_plan(selection: dict, media_info: dict, transcript: dict, rules: dict) -> dict:
    """Validate a human-selected range, crop, and publishing text."""
    try:
        duration = float(media_info["duration"])
        start = float(selection.get("start", 0))
        end = float(selection["end"]) if selection.get("end") is not None else min(duration, start + 30)
    except (KeyError, ValueError, TypeError) as exc:
        raise PipelineError("Choose valid source start and end times.") from exc
    if not all(math.isfinite(value) for value in (duration, start, end)) or not 0 <= start < end <= duration + .001:
        raise PipelineError("Choose a positive clip range within the source video.")
    if end - start < 1 or end - start > 600:
        raise PipelineError("A manual clip must be between 1 and 600 seconds long.")
    campaign = CampaignRules.model_validate(rules.get("rules", rules))
    title = str(selection.get("title") or f"{campaign.campaign_name if campaign.campaign_name != 'Untitled campaign' else Path(str(media_info.get('filename', 'Source video'))).stem} clip").strip()
    title = title or "Selected clip"
    if len(title) > 100:
        raise PipelineError("Enter a publishing title of at most 100 characters.")
    description = str(selection.get("description") or "").strip()
    tags = selection.get("hashtags") or []
    if isinstance(tags, str):
        tags = tags.split()
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise PipelineError("Hashtags must be a list of text tags.")
    tags = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    if len(tags) > 30 or any(not re.fullmatch(r"#[\w]+", tag, re.UNICODE) for tag in tags):
        raise PipelineError("Use up to 30 hashtags beginning with # and containing letters, numbers, or underscores.")
    excerpt = _selection_text(transcript, start, end)
    subtitle_style = selection.get("subtitle_style", "clean")
    has_cues = bool(Transcript.model_validate(transcript).words or Transcript.model_validate(transcript).segments)
    raw = {
        "title": title, "start": start, "end": end,
        "hook": str(selection.get("hook") or ""),
        "rationale": "The user selected this source range and framing in free local mode; no AI analysis or ranking was performed.",
        "content_type": "general",
        "scenes": [{"start": start, "end": end, "crop_x": selection.get("crop_x", .5), "crop_y": selection.get("crop_y", .5), "zoom": selection.get("zoom", 1), "rationale": "User-selected continuous source range and crop."}],
        "subtitle_style": subtitle_style,
        "subtitles_enabled": bool(selection.get("subtitles_enabled", True)) and has_cues,
        "show_hook": bool(selection.get("show_hook", False)),
        "edit_dna": {
            "hook_structure": "User-provided opening hook" if selection.get("hook") and selection.get("show_hook") else "Original selected source opening; no added hook",
            "scene_order": "Original source order, selected by the user",
            "cut_timing": f"User selected {start:.3f}–{end:.3f} source seconds",
            "framing": "Manual normalized crop coordinates and zoom; no automatic subject tracking",
            "typography": "Chosen subtitle style; no fixed promotional layout",
            "subtitle_treatment": "Supplied subtitle cues at exact cue times; no inferred word timings" if has_cues else "No supplied captions; no automatic transcription",
            "visual_effects": "None; source footage fills the vertical crop",
            "audio_treatment": "FFmpeg audio normalization; original audio is preserved where present",
            "ending_structure": "User-selected source endpoint",
        },
        "scores": {key: 0 for key in ("hook_strength", "engagement_potential", "clarity", "standalone_context", "campaign_relevance")},
        "transcript_excerpt": excerpt,
        "semantic_notes": ["Human review is required for campaign meaning, clip context, and selected framing.", "No AI hook, engagement, or virality score was calculated."],
        "generation_method": "manual_local", "score_origin": "not_scored",
        "manual_metadata": {"title": title, "description": description, "hashtags": tags},
    }
    try:
        return ClipPlan.model_validate(raw).model_dump()
    except ValueError as exc:
        raise PipelineError("The manual clip settings are invalid: " + str(exc)[:500]) from exc


class LocalPipelineService(PipelineService):
    """Drop-in renderer/compliance service that never constructs a cloud client."""

    def __init__(self):
        self.provider = _LocalProvider()

    def analyze_campaign(self, brief: str, source_url: str | None = None, attachments: list[dict] | None = None) -> dict:
        if len(brief) > 120000:
            raise PipelineError("Campaign brief exceeds 120,000 characters.")
        sources = [{"source": "brief", "text": brief}]
        notes = ["Free local mode does not use AI to understand campaign requirements. Review every supplied rule before publication."]
        for index, attachment in enumerate(attachments or []):
            name = str(attachment.get("filename") or attachment.get("name") or f"attachment-{index + 1}")
            if attachment.get("text"):
                sources.append({"source": name, "text": str(attachment["text"])[:80000]})
                continue
            if not attachment.get("path"):
                continue
            path = Path(attachment["path"])
            if not path.is_file() or path.stat().st_size > 15 * 1024 * 1024:
                raise PipelineError("Campaign attachments must exist and be smaller than 15 MB.")
            if path.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(path))
                    if len(reader.pages) > 100:
                        raise PipelineError("Campaign PDFs are limited to 100 pages.")
                    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
                except PipelineError:
                    raise
                except Exception as exc:
                    raise PipelineError("Unable to read this campaign PDF.") from exc
                if extracted.strip():
                    sources.append({"source": name, "text": extracted[:80000]})
                else:
                    notes.append(f"{name} has no extractable text. Paste its requirements; local mode does not perform OCR.")
            else:
                notes.append(f"Read {name} and enter its rules manually. Local mode does not interpret screenshots.")
        data = CampaignRules(uncertainties=notes).model_dump()
        evidence = []
        seen: dict[str, object] = {}

        def set_field(field, value, source, line):
            if field in seen and seen[field] != value:
                data["contradictions"].append(f"Conflicting labeled values for {field}; review the source.")
                return
            data[field] = value
            seen[field] = value
            evidence.append({"field": field, "quote": line, "source": source, "verified_quote": True, "extraction_method": "labeled_text"})

        for source in sources:
            for raw_line in source["text"].splitlines():
                line = raw_line.strip()
                for label, field in [("Automated clipping", "automated_clipping_allowed"), ("AI generated videos", "ai_generated_allowed"), ("Music", "music_allowed"), ("AI voice", "ai_voice_allowed"), ("Paid promotion", "paid_promotion_allowed")]:
                    restriction = re.fullmatch(re.escape(label) + r"\s*:\s*(allowed|permitted|yes|prohibited|not allowed|no)\.?", line, re.IGNORECASE)
                    if restriction:
                        set_field(field, restriction[1].casefold() in {"allowed", "permitted", "yes"}, source["source"], line)
                original = re.fullmatch(r"original (?:creator )?footage\s*:\s*(required|yes|not required|no)\.?", line, re.IGNORECASE)
                if original:
                    set_field("original_footage_required", original[1].casefold() in {"required", "yes"}, source["source"], line)
                if re.fullmatch(r"no automated clipping[.!]?", line, re.IGNORECASE):
                    set_field("automated_clipping_allowed", False, source["source"], line)
                if re.fullmatch(r"no (?:fully )?AI[- ]generated videos[.!]?", line, re.IGNORECASE):
                    set_field("ai_generated_allowed", False, source["source"], line)
                required_link = re.fullmatch(r"required links?\s*:\s*(.+)", line, re.IGNORECASE)
                if required_link:
                    set_field("required_links", required_link[1].split(), source["source"], line)
                match = re.fullmatch(r"(?:allowed\s+|permitted\s+)?platforms?\s*:\s*(.+)", line, re.IGNORECASE)
                if match:
                    values = re.split(r"\s*[,;/|]\s*", match[1].strip().rstrip("."))
                    mapping = {"youtube": "youtube", "youtube shorts": "youtube", "shorts": "youtube", "tiktok": "tiktok", "instagram": "instagram", "instagram reels": "instagram", "reels": "instagram"}
                    if values and all(value.casefold() in mapping for value in values):
                        set_field("allowed_platforms", list(dict.fromkeys(mapping[v.casefold()] for v in values)), source["source"], line)
                match = re.fullmatch(r"(?:required\s+)?hashtags?\s*:\s*((?:#[\w]+[ ,]*)+)", line, re.IGNORECASE)
                if match:
                    set_field("required_hashtags", list(dict.fromkeys(re.findall(r"#[\w]+", match[1]))), source["source"], line)
                match = re.fullmatch(r"(?:clip\s+)?duration\s*:\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?)\.?", line, re.IGNORECASE)
                if match:
                    minimum, maximum = map(float, match.groups())
                    if 0 <= minimum <= 3600 and 0 < maximum <= 3600:
                        set_field("min_duration", minimum, source["source"], line)
                        set_field("max_duration", maximum, source["source"], line)
                match = re.fullmatch(r"(minimum|maximum)\s+(?:clip\s+)?duration\s*:\s*(\d+(?:\.\d+)?)\s*(?:s|seconds?)\.?", line, re.IGNORECASE)
                if match:
                    field = "min_duration" if match[1].casefold() == "minimum" else "max_duration"
                    value = float(match[2])
                    if (field == "min_duration" and 0 <= value <= 3600) or (field == "max_duration" and 0 < value <= 3600):
                        set_field(field, value, source["source"], line)
                match = re.fullmatch(r"draft\s+(?:pre[- ]?)?approval\s*:\s*(required|not required|yes|no)\.?", line, re.IGNORECASE)
                if match:
                    set_field("draft_approval_required", match[1].casefold() in {"required", "yes"}, source["source"], line)
        if data["min_duration"] is not None and data["max_duration"] is not None and data["min_duration"] > data["max_duration"]:
            data["contradictions"].append("Minimum duration exceeds maximum duration.")
        data["evidence"] = evidence
        data = CampaignRules.model_validate(data).model_dump()
        return {"rules": data, "evidence": evidence, "review_required": True, "source_url": source_url,
                "usage": [], "analysis_method": "local_labeled_text", "ai_used": False}

    def transcribe(self, source_path: str | Path, cache_path: str | Path | None = None) -> dict:
        return Transcript(provider="manual_required", timing_source="none").model_dump()

    def plan_clips(self, transcript: dict, rules: dict, media_info: dict, count: int = 1, mode: str = "fast", previous: list[dict] | None = None) -> list[dict]:
        raise PipelineError("Free local mode requires manual clip ranges. Choose the source start/end times; no AI moment selection is performed.")

    def build_manual_plan(self, selection: dict, media_info: dict, transcript: dict, rules: dict) -> dict:
        return build_manual_plan(selection, media_info, transcript, rules)

    def generate_metadata(self, plan: dict, rules: dict) -> dict:
        clip = ClipPlan.model_validate(plan)
        campaign = CampaignRules.model_validate(rules.get("rules", rules))
        manual = clip.manual_metadata
        title = (manual.title if manual and manual.title else clip.title)[:100]
        description = manual.description if manual and manual.description else clip.transcript_excerpt
        tags = list(dict.fromkeys((manual.hashtags if manual else []) + campaign.required_hashtags))
        required = campaign.required_mentions + campaign.required_disclosures + campaign.required_links
        text = description.strip()
        for value in required:
            if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.IGNORECASE):
                text = (text + "\n\n" + value).strip()
        # These are editable deterministic packages, not three AI alternatives or
        # a performance recommendation. Preserve identical user choices per slot.
        variant = {"title": title, "description": text, "caption": text,
                   "hashtags": tags, "keywords": [], "opening_hook": clip.hook,
                   "call_to_action": "", "score": 0,
                   "reasoning": "User-supplied metadata formatted locally with required campaign text. Not AI generated, optimized, or scored."}
        data = {platform: {"variants": [copy.deepcopy(variant) for _ in range(3)], "recommended_index": 0} for platform in PLATFORMS}
        try:
            return Metadata.model_validate(data).model_dump()
        except ValueError as exc:
            raise PipelineError("The supplied metadata and mandatory campaign text exceed platform limits. Shorten the description or review the required text.") from exc
