"""Native campaign restrictions must survive local extraction and validation."""
import pytest
from pydantic import ValidationError

from app.services.local import LocalPipelineService, build_manual_plan
from app.services.schemas import CampaignRules
from app.services.compliance import check_compliance


def test_explicit_local_restrictions_retain_source_evidence_and_conflicts():
    parsed = LocalPipelineService().analyze_campaign(
        "No automated clipping\nAutomated clipping: allowed\nAI voice: prohibited\n"
        "Original creator footage: required\nRequired link: https://example.com/campaign")
    rules = parsed["rules"]
    assert rules["automated_clipping_allowed"] is False
    assert rules["ai_voice_allowed"] is False
    assert rules["original_footage_required"] is True
    assert rules["required_links"] == ["https://example.com/campaign"]
    assert rules["contradictions"]
    assert any(item["quote"] == "No automated clipping" for item in rules["evidence"])


def test_native_campaign_schema_retains_restrictions_and_rejects_unsafe_links():
    rules = CampaignRules.model_validate({"music_allowed": False, "ai_generated_allowed": False,
                                         "prohibited_footage": ["Unlicensed stock"],
                                         "audience_restrictions": ["Adults"]}).model_dump()
    assert rules["music_allowed"] is False and rules["ai_generated_allowed"] is False
    assert rules["audience_restrictions"] == ["Adults"]
    for link in ["http://example.com", "https://secret@example.com", "file:///private"]:
        with pytest.raises(ValidationError):
            CampaignRules(required_links=[link])


def test_required_links_are_retained_and_semantic_restrictions_do_not_auto_pass():
    service = LocalPipelineService()
    rules = CampaignRules(allowed_platforms=["youtube"], draft_approval_required=False,
                          required_links=["https://example.com/campaign"], music_allowed=False,
                          ai_voice_allowed=False, original_footage_required=True,
                          paid_promotion_allowed=False).model_dump()
    plan = build_manual_plan({"start": 0, "end": 5, "title": "Actual source"},
                             {"duration": 10, "filename": "source.mp4"}, {}, rules)
    metadata = service.generate_metadata(plan, rules)
    assert rules["required_links"][0] in metadata["youtube"]["variants"][0]["description"]
    result = check_compliance(plan, metadata, rules, True,
                              {"width": 1080, "height": 1920, "codec": "h264",
                               "duration": 5, "has_audio": True, "decode_verified": True})
    by_rule = {item["rule"]: item["status"] for item in result["checks"]}
    for key in ["music_restrictions", "ai_voice_restrictions", "original_footage", "paid_promotion"]:
        assert by_rule[key] == "REVIEW_REQUIRED"
    assert not result["publish_ready"]
