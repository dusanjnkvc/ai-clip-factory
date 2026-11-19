"""Conservative compliance checks. Unknown semantic facts never become PASS."""

from __future__ import annotations

import re
from typing import Any

from .schemas import CampaignRules, ClipPlan, Metadata, PLATFORMS


def check_compliance(
    plan: dict, metadata: dict, rules: dict, rights: dict | bool,
    render_info: dict, draft_approved: bool = False,
    semantic_evidence: dict | None = None,
) -> dict:
    rules = rules.get("rules", rules)
    campaign = CampaignRules.model_validate(rules)
    clip = ClipPlan.model_validate(plan)
    meta = Metadata.model_validate(metadata)
    checks: list[dict[str, Any]] = []
    semantic_evidence = semantic_evidence or {}

    def add(rule: str, status: str, detail: str, *, evidence: Any = None):
        checks.append({"rule": rule, "status": status, "detail": detail, "blocking": status != "PASS", "evidence": evidence})

    def semantic(rule: str, detail: str):
        evidence = semantic_evidence.get(rule)
        if isinstance(evidence, dict) and evidence.get("confirmed") is True and str(evidence.get("note", "")).strip() and evidence.get("reviewed_by") and evidence.get("reviewed_at"):
            add(rule, "PASS", "Confirmed by an identified human reviewer: " + str(evidence["note"])[:2000], evidence=evidence)
        else:
            add(rule, "REVIEW_REQUIRED", detail)

    authorized = rights is True or isinstance(rights, dict) and rights.get("authorized") is True and rights.get("confirmed") is True and bool(str(rights.get("attestation", "")).strip())
    add("source_rights", "PASS" if authorized else "FAIL", "User rights attestation recorded; this is not independent legal verification." if authorized else "A source-rights attestation is required before publication.", evidence=rights if isinstance(rights, dict) else None)

    duration = render_info.get("duration")
    if duration is None:
        add("duration", "REVIEW_REQUIRED", "The rendered video has not been probed.")
    elif campaign.min_duration is not None and duration < campaign.min_duration - .05:
        add("duration", "FAIL", f"{duration:.2f}s is shorter than the campaign minimum {campaign.min_duration:.2f}s.")
    elif campaign.max_duration is not None and duration > campaign.max_duration + .05:
        add("duration", "FAIL", f"{duration:.2f}s exceeds the campaign maximum {campaign.max_duration:.2f}s.")
    else:
        add("duration", "PASS", f"Rendered duration is {duration:.2f}s; no supplied duration bound is violated.")
    valid_media = render_info.get("width") == 1080 and render_info.get("height") == 1920 and render_info.get("has_audio") is True and render_info.get("decode_verified") is True and render_info.get("codec") in {"h264", "avc1"}
    add("video_format", "PASS" if valid_media else "FAIL", "Decoded 1080 × 1920 H.264 video with audio." if valid_media else "A verified playable 1080 × 1920 H.264 render with audio is required.")
    if clip.subtitles_enabled and clip.transcript_excerpt.strip():
        timing = "Supplied subtitle cue timestamps are mapped through the editing timeline; word alignment was not inferred." if render_info.get("subtitle_timing") == "cue" else "Subtitles use provider word timestamps mapped through the editing timeline."
        add("subtitle_sync", "PASS" if render_info.get("subtitle_synchronized") is True else "FAIL", timing if render_info.get("subtitle_synchronized") else "Speech was selected but synchronized subtitles were not verified.")

    if campaign.allowed_platforms:
        add("platforms", "PASS", "Campaign permits: " + ", ".join(campaign.allowed_platforms))
    else:
        semantic("platforms", "The campaign does not establish permitted publishing platforms. Correct the campaign rules or record reviewer evidence.")
    for platform in campaign.allowed_platforms or PLATFORMS:
        platform_meta = getattr(meta, platform)
        chosen = platform_meta.variants[platform_meta.recommended_index]
        text = " ".join([chosen.title, chosen.description, chosen.caption, " ".join(chosen.hashtags)])
        missing = []
        for value in campaign.required_hashtags + campaign.required_mentions:
            # Require a whole token: #ad must not be satisfied by #advertisement.
            if not re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text, re.IGNORECASE):
                missing.append(value)
        for value in campaign.required_disclosures + campaign.required_links:
            if value.casefold() not in text.casefold():
                missing.append(value)
        add(f"metadata_{platform}", "FAIL" if missing else "PASS", "Missing required campaign text: " + ", ".join(missing) if missing else "The recommended metadata includes all supplied required tags, mentions, and disclosure text.")
        from .campaign_requirements import ordered_hashtags
        tags = ordered_hashtags(campaign.required_hashtags, [])
        order_ok = chosen.hashtags[:len(tags)] == tags
        for value in (chosen.description, chosen.caption):
            embedded = re.findall(r'(?<!\w)#[\w]+', value)
            if embedded and tags and embedded[:len(tags)] != tags:
                order_ok = False
        add(f'hashtag_order_{platform}', 'PASS' if order_ok else 'FAIL', 'Mandatory hashtags must retain exact spelling/order before optional hashtags.')
        wording_ok = (not campaign.required_title or chosen.title == campaign.required_title) and all(p in chosen.title for p in campaign.required_title_phrases) and all(p in chosen.description for p in campaign.required_description_phrases)
        add(f'wording_{platform}', 'PASS' if wording_ok else 'FAIL', 'Required title and description wording must be preserved exactly.')
        if platform in campaign.prohibited_platforms:
            add(f'prohibited_platform_{platform}', 'FAIL', 'This publishing platform is prohibited by the campaign.')

    if campaign.required_on_video_text:
        semantic('on_video_text', 'Verify exact visible wording and readability in the rendered video: ' + '; '.join(campaign.required_on_video_text))
    exact=[]
    for requirement in campaign.resolution_requirements:
        dimensions=re.fullmatch(r'\s*(\d{2,5})\s*[x×]\s*(\d{2,5})\s*',requirement)
        if dimensions:
            valid=(render_info.get('width'),render_info.get('height'))==tuple(map(int,dimensions.groups()))
            add('campaign_resolution','PASS' if valid else 'FAIL','Required output resolution: '+requirement)
        else:exact.append(requirement)
    if exact:semantic('resolution_requirements','Review the actual format against: '+'; '.join(exact))
    for field in ('logo_requirements', 'other_requirements'):
        if getattr(campaign, field):
            semantic(field, 'Verify the original requirement against the actual output: ' + '; '.join(getattr(campaign, field)))

    if campaign.required_branding:
        semantic("branding", "Verify the required branding in the actual rendered video: " + "; ".join(campaign.required_branding))
    if campaign.prohibited_content:
        semantic("content_restrictions", "Review the video against prohibited content: " + "; ".join(campaign.prohibited_content))
    if campaign.audio_restrictions:
        semantic("audio_restrictions", "Review music/audio rights and restrictions: " + "; ".join(campaign.audio_restrictions))
    if campaign.permitted_source_material:
        semantic("source_material", "Confirm this source matches campaign-permitted material: " + "; ".join(campaign.permitted_source_material))
    if campaign.automated_clipping_allowed is False or campaign.ai_generated_allowed is False:
        semantic("manual_editing", "The campaign restricts automation. An automatically generated clip does not establish eligibility.")
    if campaign.original_footage_required:
        semantic("original_footage", "Confirm that required original creator footage and ownership evidence are present in the actual video.")
    if campaign.music_allowed is False:
        semantic("music_restrictions", "Verify that the retained source audio contains no prohibited music.")
    if campaign.ai_voice_allowed is False:
        semantic("ai_voice_restrictions", "No synthetic voice is added by this workflow. Verify the original source audio also meets the rule.")
    if campaign.paid_promotion_allowed is False:
        semantic("paid_promotion", "Review the proposed use, promotion and disclosures against the original terms.")
    for field in ("prohibited_footage", "audience_restrictions"):
        if getattr(campaign, field):
            semantic(field, "Review the actual video against: " + "; ".join(getattr(campaign, field)))
    if any(re.search(r"on.?screen|spoken|verbal|audio", text, re.IGNORECASE) for text in campaign.required_disclosures):
        semantic("disclosures", "The campaign requires a disclosure delivery method that cannot be verified by metadata text alone.")
    if campaign.draft_approval_required is True:
        add("draft_approval", "PASS" if draft_approved else "REVIEW_REQUIRED", "Draft approval was confirmed and recorded." if draft_approved else "Campaign draft approval must be confirmed before publishing.")
    elif campaign.draft_approval_required is None:
        semantic("approval_requirement", "The brief does not establish whether draft pre-approval is required.")
    else:
        add("draft_approval", "PASS", "The reviewed campaign rules explicitly state that draft pre-approval is not required.")
    if campaign.uncertainties:
        semantic("campaign_uncertainties", "Unresolved campaign rules: " + "; ".join(campaign.uncertainties))
    if campaign.contradictions:
        add("campaign_contradictions", "FAIL", "Correct contradictory campaign rules before approval: " + "; ".join(campaign.contradictions))
    if campaign.submission_deadline:
        from .campaign_requirements import deadline_state
        state=deadline_state(campaign.submission_deadline)
        if state=='review':semantic('submission_deadline','Verify the deadline and timezone: '+campaign.submission_deadline)
        else:add('submission_deadline','FAIL' if state=='expired' else 'PASS','Campaign deadline: '+campaign.submission_deadline)
    if not campaign.evidence:
        semantic("campaign_evidence", "No source evidence is stored for these campaign rules. Review the original brief and correct/evidence the rules.")
    if clip.generation_method == "local_ai":
        semantic("creative_context", "Review model interpretations, source context, hook, framing and metadata against the actual final video. Local inference does not independently verify those claims.")
    status = "FAIL" if any(c["status"] == "FAIL" for c in checks) else "REVIEW_REQUIRED" if any(c["status"] == "REVIEW_REQUIRED" for c in checks) else "PASS"
    return {"status": status, "publish_ready": status == "PASS", "checks": checks, "rules_snapshot": campaign.model_dump(), "semantic_evidence": semantic_evidence}
