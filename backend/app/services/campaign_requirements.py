"""Deterministic campaign precedence shared by generated/manual metadata."""
import re
from datetime import datetime,timezone
from .schemas import CampaignRules


def ordered_hashtags(required, optional):
    result, seen = [], set()
    for tag in [*required, *optional]:
        key = tag.casefold()
        if key not in seen:
            result.append(tag)
            seen.add(key)
    return result


def deadline_state(value):
    if not value:return None
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError,TypeError):return 'review'
    if parsed.tzinfo is None:return 'review'
    return 'expired' if parsed<datetime.now(timezone.utc) else 'open'


def enforce_metadata(variant, rules):
    campaign = rules if isinstance(rules, CampaignRules) else CampaignRules.model_validate(rules)
    result = dict(variant)
    embedded = [tag for field in ('description', 'caption') for tag in re.findall(r'(?<!\w)#[\w]+', result.get(field, ''))]
    result['hashtags'] = ordered_hashtags(campaign.required_hashtags, [*result.get('hashtags', []), *embedded])
    if campaign.required_title:
        result['title'] = campaign.required_title
    else:
        for phrase in campaign.required_title_phrases:
            if phrase not in result['title']:
                result['title'] = phrase + ' ' + result['title']
    required = campaign.required_mentions + campaign.required_disclosures + campaign.required_links + campaign.required_description_phrases
    for field in ('description', 'caption'):
        text = result.get(field, '')
        # Move all hashtag tokens into the final, campaign-first sequence.
        embedded = re.findall(r'(?<!\w)#[\w]+', text)
        text = re.sub(r'(?<!\w)#[\w]+', '', text).strip()
        for phrase in required:
            if phrase not in text:
                text = (text + '\n\n' + phrase).strip()
        if embedded and result['hashtags']:
            text = (text + '\n\n' + ' '.join(result['hashtags'])).strip()
        result[field] = text
    return result
