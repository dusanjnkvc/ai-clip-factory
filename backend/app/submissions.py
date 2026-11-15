from datetime import timedelta
from urllib.parse import urlparse
from fastapi import HTTPException
from .models import CampaignSubmission, now

HOSTS = {'youtube': {'youtube.com', 'www.youtube.com', 'youtu.be'}, 'tiktok': {'www.tiktok.com', 'tiktok.com'}, 'instagram': {'www.instagram.com', 'instagram.com'}}

def validate_post_url(platform, url):
    parsed = urlparse(url)
    if platform not in HOSTS or parsed.scheme != 'https' or parsed.hostname not in HOSTS[platform] or not parsed.path.strip('/'):
        raise HTTPException(422, 'Provide an HTTPS post URL on the selected official platform.')
    return url

def submission_minutes(rules):
    value = rules.get('submission_window_minutes')
    if isinstance(value, dict):
        value = value.get('value')
    if value is None:
        value = rules.get('submission_deadline_minutes')
    try:
        return int(value) if value is not None and int(value) > 0 else None
    except (ValueError, TypeError):
        return None

def create_submission(db, post, campaign):
    window = submission_minutes(campaign.rules)
    submission = CampaignSubmission(post_id=post.id, user_id=post.user_id, campaign_id=campaign.id, submission_url=campaign.rules.get('submission_url') or campaign.url, deadline=post.published_at + timedelta(minutes=window) if window else None)
    db.add(submission)
    return submission

def countdown(submission, at=None):
    if not submission.deadline or submission.status != 'pending':
        return {'seconds_remaining': None, 'warning': None}
    seconds = int((submission.deadline - (at or now())).total_seconds())
    warning = 'expired' if seconds <= 0 else '5 minutes remaining' if seconds <= 300 else '10 minutes remaining' if seconds <= 600 else '15 minutes remaining' if seconds <= 900 else None
    return {'seconds_remaining': max(0, seconds), 'warning': warning}

def estimate_earnings(kind, eligible_views=None, rate=None, maximum=None, confirmed_flat=None):
    if kind == 'cpm' and eligible_views is not None and rate is not None:
        value = max(0, eligible_views) / 1000 * max(0, rate)
        return min(value, maximum) if maximum is not None else value
    if kind in {'flat', 'flat_fee', 'retainer'} and confirmed_flat is not None:
        return confirmed_flat
    return None
