"""First-clip-first building blocks used by the durable backend worker."""

from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from . import compliance, media
from .media import ConfigurationError, PipelineError
from .provider import CloudProvider
from .schemas import CampaignRules, CandidateResponse, ClipPlan, Metadata, Transcript, Word


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def near_duplicate(left: dict, right: dict) -> bool:
    """Scene/time overlap and actual words matter; font/color changes do not."""
    left_scenes = left.get("scenes") or [{"start": left["start"], "end": left["end"]}]
    right_scenes = right.get("scenes") or [{"start": right["start"], "end": right["end"]}]
    overlap = sum(max(0, min(a["end"], b["end"]) - max(a["start"], b["start"])) for a in left_scenes for b in right_scenes)
    shortest = min(sum(a["end"]-a["start"] for a in left_scenes), sum(b["end"]-b["start"] for b in right_scenes))
    overlap_ratio = min(1, overlap / max(.01, shortest))
    left_text, right_text = _normalized(left.get("transcript_excerpt", "")), _normalized(right.get("transcript_excerpt", ""))
    similarity = difflib.SequenceMatcher(None, left_text, right_text, autojunk=False).ratio() if left_text and right_text else 0
    return overlap_ratio > .65 or similarity > .86 and overlap_ratio > .2 or len(left_text) > 50 and similarity > .95


def _document_content(attachments: list[dict] | None) -> tuple[list[dict], list[dict]]:
    documents, images = [], []
    for index, attachment in enumerate(attachments or []):
        source = str(attachment.get("name") or attachment.get("filename") or f"attachment-{index+1}")
        if attachment.get("text"):
            documents.append({"source": source, "text": str(attachment["text"])[:80000]})
            continue
        if not attachment.get("path"):
            continue
        path = Path(attachment["path"])
        if not path.is_file() or path.stat().st_size > 15 * 1024 * 1024:
            raise PipelineError("Campaign attachments must exist and be smaller than 15 MB")
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                if len(reader.pages) > 100:
                    raise PipelineError("Campaign PDFs are limited to 100 pages")
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                if not text.strip():
                    raise PipelineError("The PDF has no extractable text. Upload page screenshots or paste its requirements for cloud vision analysis.")
                documents.append({"source": source, "text": text[:80000]})
            except ImportError as exc:
                raise ConfigurationError("Install pypdf to extract campaign PDFs") from exc
            except PipelineError:
                raise
            except Exception as exc:
                raise PipelineError("Unable to read this campaign PDF") from exc
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[suffix]
            image_bytes = path.read_bytes()
            signatures = image_bytes.startswith(b"\x89PNG\r\n\x1a\n") or image_bytes.startswith(b"\xff\xd8\xff") or image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP"
            if not signatures:
                raise PipelineError("Campaign image signature is invalid")
            images.append({"data_url": f"data:{mime};base64," + base64.b64encode(image_bytes).decode("ascii"), "source": source})
            documents.append({"source": source, "text": "[Image provided for cloud vision. Quotes from this image require human verification.]"})
        elif suffix in {".txt", ".md"}:
            documents.append({"source": source, "text": path.read_text(encoding="utf-8")[:80000]})
        else:
            raise PipelineError("Unsupported campaign attachment. Use a PDF, PNG, JPEG, WebP, or text file.")
    return documents, images


class PipelineService:
    def __init__(self, provider: CloudProvider | None = None):
        self.provider = provider or CloudProvider()

    @property
    def usage(self) -> list[dict]:
        return self.provider.usage

    def probe_media(self, source_path: str | Path) -> dict:
        return media.probe_media(source_path)

    def analyze_campaign(self, brief: str, source_url: str | None = None, attachments: list[dict] | None = None) -> dict:
        if len(brief) > 120000:
            raise PipelineError("Campaign brief exceeds 120,000 characters")
        documents, images = _document_content(attachments)
        if not brief.strip() and not documents:
            raise PipelineError("Paste campaign requirements or attach a campaign brief. A URL alone is not fetched or scraped.")
        sources = [{"source": "brief", "text": brief}] + documents
        prompt = json.dumps({"source_url_reference_only": source_url, "sources": sources}, ensure_ascii=False)
        rules = self.provider.structured(CampaignRules,
            "Extract campaign requirements with exact source evidence. Never invent facts or assume an API exists. Unknown scalars are null; unknown lists are empty. Use only explicitly stated platforms. 'Shorts' means youtube, 'Reels' means instagram. Campaign type must be unknown unless evidenced. Include an evidence item for every nonempty rule, identifying source and an exact quote. If sources disagree, preserve contradictions and flag review. Distinguish submission_window_minutes after publication from an absolute submission_deadline. Do not infer draft_approval_required=false from silence. Required disclosures contain the exact publishable phrase, not paraphrased instructions. Put unclear delivery methods in uncertainties. Screenshot evidence must be flagged for human confirmation. A source URL is only a reference, never proof of content or usage rights.", prompt, images)
        data = rules.model_dump()
        verified_evidence = []
        source_map = {source["source"]: source["text"] for source in sources}
        for evidence in data["evidence"]:
            source_text = source_map.get(evidence["source"], "")
            if _normalized(evidence["quote"]) and _normalized(evidence["quote"]) in _normalized(source_text):
                verified_evidence.append({**evidence, "verified_quote": True})
            else:
                # OCR/vision quotations are retained, but cannot silently become verified.
                verified_evidence.append({**evidence, "verified_quote": False})
                data["uncertainties"].append(f"Verify source evidence for {evidence['field']} from {evidence['source']}.")
        if images:
            data["uncertainties"].append("Confirm requirements extracted from screenshots against the original campaign.")
        for field, value in data.items():
            if field in {"evidence", "uncertainties", "contradictions", "campaign_name"} or value is None or value == [] or value == "unknown":
                continue
            if not any(e["field"] == field for e in verified_evidence):
                data["uncertainties"].append(f"No source evidence was provided for {field}.")
        if not data["allowed_platforms"]:
            data["uncertainties"].append("Permitted platforms are not established.")
        if data["draft_approval_required"] is None:
            data["uncertainties"].append("Draft approval requirements are not established.")
        if data["min_duration"] is not None and data["max_duration"] is not None and data["min_duration"] > data["max_duration"]:
            data["contradictions"].append("Minimum duration exceeds maximum duration.")
        data["uncertainties"] = list(dict.fromkeys(data["uncertainties"]))
        data["evidence"] = verified_evidence
        return {"rules": data, "evidence": verified_evidence, "review_required": bool(data["uncertainties"] or data["contradictions"]), "source_url": source_url, "usage": self.usage}

    def transcribe(self, source_path: str | Path, cache_path: str | Path | None = None) -> dict:
        info = media.probe_media(source_path)
        maximum = int(os.getenv("MAX_SOURCE_DURATION_SECONDS", "7200"))
        if info["duration"] > maximum:
            raise PipelineError(f"Source duration exceeds the configured {maximum}-second job limit")
        if not info["has_audio"]:
            return Transcript(provider="no_audio").model_dump()
        source_hash = media.sha256_file(source_path)
        cache = Path(cache_path) if cache_path else Path(source_path).with_suffix(".transcript.json")
        identity = hashlib.sha256((source_hash + self.provider.base_url + self.provider.transcription_model).encode()).hexdigest()
        if cache.is_file():
            try:
                cached = json.loads(cache.read_text(encoding="utf-8"))
                if cached.get("identity") == identity:
                    transcript = Transcript.model_validate(cached["transcript"]).model_dump()
                    transcript["cached"] = True
                    return transcript
            except (ValueError, KeyError, OSError):
                pass
        self.provider.require_configured()
        text_parts, words, segments = [], [], []
        language = None
        chunk_seconds = 600
        with tempfile.TemporaryDirectory(prefix="acf-transcribe-") as temp:
            for index, start in enumerate(range(0, int(info["duration"] + .999), chunk_seconds)):
                chunk = media.extract_audio(source_path, Path(temp) / f"audio-{index}.mp3", start=start, duration=min(chunk_seconds, info["duration"] - start))
                response = self.provider.transcribe_audio(chunk)
                text_parts.append(str(response.get("text", "")))
                language = response.get("language", language)
                for word in response.get("words", []):
                    item = Word.model_validate({"word": word["word"], "start": float(word["start"]) + start, "end": float(word["end"]) + start})
                    if item.end > info["duration"] + .2:
                        raise PipelineError("Transcription contains timestamps beyond the source duration")
                    words.append(item.model_dump())
                for segment in response.get("segments", []):
                    segments.append({"start": float(segment["start"]) + start, "end": float(segment["end"]) + start, "text": str(segment.get("text", ""))})
        words.sort(key=lambda word: (word["start"], word["end"]))
        transcript = Transcript.model_validate({"text": " ".join(text_parts).strip(), "language": language, "words": words, "segments": segments, "provider": "cloud"}).model_dump()
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(cache.suffix + ".tmp")
        temporary.write_text(json.dumps({"identity": identity, "transcript": transcript}, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, cache)
        return transcript

    def plan_clips(self, transcript: dict, rules: dict, media_info: dict, count: int = 3, mode: str = "fast", previous: list[dict] | None = None) -> list[dict]:
        if mode not in {"fast", "quality"} or not 1 <= count <= 5:
            raise PipelineError("Choose fast/quality mode and between one and five clips")
        duration = float(media_info["duration"])
        if duration > int(os.getenv("MAX_SOURCE_DURATION_SECONDS", "7200")):
            raise PipelineError("Source video exceeds the configured duration limit")
        campaign = CampaignRules.model_validate(rules.get("rules", rules))
        speech = Transcript.model_validate(transcript)
        images, scenes = [], []
        source_path = media_info.get("path")
        if source_path:
            # Measured scene transitions complement speech rather than decorating it.
            if mode == "quality":
                scenes = media.scene_events(source_path)
            if os.getenv("AI_VISION_ENABLED", "true").lower() == "true":
                images = media.sample_frames(source_path, duration, count=4 if mode == "fast" else 8)
        prompt = json.dumps({"mode": mode, "requested_clips": count, "source": {k: v for k, v in media_info.items() if k != "path"}, "transcript": speech.model_dump(), "campaign_rules": campaign.model_dump(), "measured_scene_cuts_seconds": scenes, "previous_clips_to_avoid": previous or []}, ensure_ascii=False)
        result = self.provider.structured(CandidateResponse,
            "You are a skilled short-form editor, not a template generator. Select the strongest standalone moments FIRST and create one distinct content-driven timeline/Edit DNA for each. Return fewer clips if the source lacks distinct material. Scenes use absolute SOURCE seconds and can be reordered only without misleading meaning. Keep scenes within start/end and the source duration. Each scene includes normalized crop_x/crop_y (0 left/top, .5 center, 1 right/bottom) and modest zoom based on the visible subject. Do not claim face/motion tracking from unseen frames. Gameplay fills the frame and keeps action clear; avoid obstructive overlays. Podcast cuts preserve context and speakers. Promotional clips follow a natural hook/demonstration/conclusion, never a permanent ad banner. Avoid unrelated stock footage, repetitive intros, random transitions, and artificial color/font uniqueness. Subtitles only when useful, spoken content should generally have them. show_hook=true only when it materially helps; hook lasts 2.5 seconds. Respect evidenced campaign duration bounds using sum(scene.end-scene.start), not just the source range. Score hook_strength/engagement_potential/clarity/standalone_context/campaign_relevance as heuristic 0–100 evaluations, not viral predictions. Include complete Edit DNA: hook_structure,scene_order,cut_timing,framing,typography,subtitle_treatment,visual_effects,audio_treatment,ending_structure. Do not assert branding/content/audio compliance; list semantic_notes for human review. No guessed speech, no context fabrication.", prompt, images)
        accepted = []
        for candidate in sorted(result.clips, key=lambda clip: clip.scores.weighted(), reverse=True):
            if any(scene.end > duration + .05 for scene in candidate.scenes):
                raise PipelineError("AI editing plan selected timestamps outside the source")
            data = candidate.model_dump()
            # Actual selected words, not an AI paraphrase, drive metadata and dedup.
            data["transcript_excerpt"] = " ".join(word["word"] for word in media.timeline_words(candidate, speech))
            data["score"] = candidate.scores.weighted(rules.get("scoring_weights"))
            data["score_is_heuristic"] = True
            data["visual_analysis"] = "sampled_cloud_vision" if images else "transcript_only"
            data["measured_scene_cuts"] = scenes
            if not any(near_duplicate(data, old) for old in accepted + (previous or [])):
                accepted.append(data)
            if len(accepted) == count:
                break
        if not accepted:
            raise PipelineError("The source did not provide a distinct valid candidate. Try a different source or adjust the reviewed duration rules.")
        return accepted

    def generate_metadata(self, plan: dict, rules: dict) -> dict:
        clip = ClipPlan.model_validate(plan)
        campaign = CampaignRules.model_validate(rules.get("rules", rules))
        result = self.provider.structured(Metadata,
            "Create three truthful, distinct publishing metadata combinations per platform and recommend the strongest compliant variant by index. Use only this clip's actual selected speech, visible-content rationale, and campaign evidence. YouTube: searchable title <=100 chars and concise description. TikTok: natural engaging caption/keywords. Instagram: natural caption and relevant call to action. Include required campaign tags, mentions, and disclosure phrases exactly. Avoid unsupported trending claims, misleading clickbait, fabricated quotations, unsupported product promises, and irrelevant tags. Each variant must include title, description, caption, hashtags, keywords, opening_hook, call_to_action, score(0–100 heuristic),reasoning. Campaign rules override optimization. No guaranteed virality or payout claims.", json.dumps({"clip": clip.model_dump(), "campaign": campaign.model_dump()}, ensure_ascii=False))
        data = result.model_dump()
        # Automatically correct objectively fixable required text omissions in all variants.
        required_tags = list(dict.fromkeys(campaign.required_hashtags))
        required_text = campaign.required_mentions + campaign.required_disclosures + campaign.required_links
        for platform in data.values():
            for variant in platform["variants"]:
                variant["hashtags"] = list(dict.fromkeys(variant["hashtags"] + required_tags))
                for field in ("caption", "description"):
                    missing = [text for text in required_text + required_tags if not re.search(r"(?<!\w)" + re.escape(text) + r"(?!\w)", variant[field], re.IGNORECASE)]
                    if missing:
                        variant[field] = (variant[field].rstrip() + "\n\n" + " ".join(missing)).strip()
                from .campaign_requirements import enforce_metadata
                variant.update(enforce_metadata(variant, campaign))
        # Validate again after corrections; oversize mandatory text must be reviewed, not truncated.
        try:
            return Metadata.model_validate(data).model_dump()
        except ValueError as exc:
            raise PipelineError("Required campaign text exceeds platform metadata limits. Review the campaign requirements.") from exc

    def render_clip(self, source_path: str | Path, plan: dict, transcript: dict, output_path: str | Path, mode: str = "fast") -> dict:
        return media.render_clip(source_path, plan, transcript, output_path, mode)

    def check_compliance(self, plan: dict, metadata: dict, rules: dict, rights: dict | bool, render_info: dict, draft_approved: bool = False, semantic_evidence: dict | None = None) -> dict:
        return compliance.check_compliance(plan, metadata, rules, rights, render_info, draft_approved, semantic_evidence)

    def process_clip(self, source_path: str | Path, plan: dict, transcript: dict, rules: dict, rights: dict | bool, output_path: str | Path, mode: str = "fast", draft_approved: bool = False) -> dict:
        # The backend runs this PER CLIP; one completion never waits on a batch.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            metadata_future = pool.submit(self.generate_metadata, plan, rules)
            rendered = self.render_clip(source_path, plan, transcript, output_path, mode)
            metadata = metadata_future.result()
        return {"plan": plan, "metadata": metadata, "render": rendered, "compliance": self.check_compliance(plan, metadata, rules, rights, rendered, draft_approved), "usage": self.usage}
