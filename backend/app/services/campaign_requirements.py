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
    prefix=' '.join([*campaign.required_hashtags,*campaign.required_mentions])
    required = campaign.required_disclosures + campaign.required_links + campaign.required_description_phrases
    for field in ('description', 'caption'):
        text = result.get(field, '')
        # Move all hashtag tokens into the final, campaign-first sequence.
        for tag in campaign.required_hashtags:
            text=re.sub(r'(?<!\w)'+re.escape(tag)+r'(?!\w)','',text,flags=re.I).strip()
        for mention in campaign.required_mentions:
            text=re.sub(r'(?<!\w)'+re.escape(mention)+r'(?![\w.-])','',text,flags=re.I).strip()
        if prefix:text=re.sub(r'\n[ \t]*(?:\n[ \t]*)+','\n\n',text)
        text=(prefix+'\n\n'+text).strip() if prefix else text
        for phrase in required:
            if phrase not in text:
                text = (text + '\n\n' + phrase).strip()
        result[field] = text
    return result
