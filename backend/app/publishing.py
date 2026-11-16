"""Official YouTube OAuth/resumable uploads; no consumer website automation."""
import base64
import hashlib
import json
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlparse
import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select, update, or_
from .db import SessionLocal
from .models import (OAuthState, ConnectedAccount, PublishingJob, RenderedClip, EditingPlan,
    Campaign, PublishedPost, AuditLog, now)
from .security import token_hash
from .storage import materialize
from .submissions import create_submission, submission_minutes
from .runtime import free_mode

SCOPES = ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly']

def configured():
    return not free_mode() and all(os.getenv(key) for key in ('YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REDIRECT_URI','TOKEN_ENCRYPTION_KEY'))

def cipher():
    key = os.getenv('TOKEN_ENCRYPTION_KEY')
    if not key:
        raise HTTPException(503, 'Set TOKEN_ENCRYPTION_KEY before connecting an account.')
    try:
        return Fernet(key.encode())
    except ValueError:
        raise HTTPException(503, 'TOKEN_ENCRYPTION_KEY must be a valid Fernet key.')

def authorization_url(db, user_id):
    if free_mode():
        raise HTTPException(503,'Free local mode uses manual upload packages. No external publishing connection is required.')
    if not configured():
        raise HTTPException(503, 'Configure the YouTube OAuth client, redirect URI and token encryption key first.')
    cipher()
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    db.add(OAuthState(user_id=user_id, state_hash=token_hash(state), verifier=verifier, expires_at=now()+timedelta(minutes=10)))
    db.commit()
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({'client_id':os.environ['YOUTUBE_CLIENT_ID'], 'redirect_uri':os.environ['YOUTUBE_REDIRECT_URI'], 'response_type':'code', 'scope':' '.join(SCOPES), 'state':state, 'access_type':'offline', 'prompt':'consent', 'code_challenge':challenge, 'code_challenge_method':'S256'})

def finish_oauth(db, user, state, code):
    if free_mode():
        raise HTTPException(503,'External account connections are disabled in free local mode.')
    row = db.scalar(select(OAuthState).where(OAuthState.user_id == user.id, OAuthState.state_hash == token_hash(state), OAuthState.expires_at > now()))
    if not row:
        raise HTTPException(400, 'OAuth request expired or invalid. Connect again.')
    verifier = row.verifier
    db.delete(row)
    db.commit()
    with httpx.Client(timeout=60) as client:
        response = client.post('https://oauth2.googleapis.com/token', data={'client_id':os.environ['YOUTUBE_CLIENT_ID'], 'client_secret':os.environ['YOUTUBE_CLIENT_SECRET'], 'redirect_uri':os.environ['YOUTUBE_REDIRECT_URI'], 'grant_type':'authorization_code', 'code':code, 'code_verifier':verifier})
        if response.status_code != 200:
            raise HTTPException(400, 'YouTube authorization failed. Reconnect the account.')
        credentials = response.json()
        granted = credentials.get('scope','').split()
        if not set(SCOPES).issubset(granted):
            raise HTTPException(400, 'YouTube upload and channel permissions are required.')
        channels = client.get('https://www.googleapis.com/youtube/v3/channels', params={'part':'snippet','mine':'true'}, headers={'Authorization':f"Bearer {credentials['access_token']}"})
        if channels.status_code != 200 or not channels.json().get('items'):
            raise HTTPException(400, 'No eligible YouTube channel found for this account.')
        channel = channels.json()['items'][0]
    account = db.scalar(select(ConnectedAccount).where(ConnectedAccount.user_id == user.id, ConnectedAccount.platform == 'youtube', ConnectedAccount.external_id == channel['id']))
    if account is None:
        account = ConnectedAccount(user_id=user.id, platform='youtube', external_id=channel['id'], name=channel['snippet']['title'], encrypted_credentials='')
        db.add(account)
    elif 'refresh_token' not in credentials:
        credentials['refresh_token'] = json.loads(cipher().decrypt(account.encrypted_credentials.encode())).get('refresh_token')
    account.encrypted_credentials = cipher().encrypt(json.dumps(credentials).encode()).decode()
    account.scopes = granted
    account.status = 'connected'
    db.add(AuditLog(user_id=user.id,action='account.connected',entity_id=account.id,detail={'platform':'youtube'}))
    db.commit()
    return account

def access_token(db, account):
    if free_mode():
        raise ValueError('External publishing is disabled in free local mode. Use the manual upload package.')
    credentials = json.loads(cipher().decrypt(account.encrypted_credentials.encode()))
    refresh = credentials.get('refresh_token')
    if not refresh:
        raise ValueError('Reconnect YouTube to grant offline access.')
    response = httpx.post('https://oauth2.googleapis.com/token', data={'client_id':os.environ['YOUTUBE_CLIENT_ID'], 'client_secret':os.environ['YOUTUBE_CLIENT_SECRET'], 'grant_type':'refresh_token','refresh_token':refresh}, timeout=60)
    if response.status_code != 200:
        raise ValueError('YouTube token refresh failed. Reconnect the account.')
    updated = response.json()
    updated['refresh_token'] = refresh
    account.encrypted_credentials = cipher().encrypt(json.dumps(updated).encode()).decode()
    db.commit()
    return updated['access_token']

def selected_metadata(metadata, platform):
    data = metadata.get(platform, {})
    if isinstance(data, list):
        return data[0] if data else {}
    variants = data.get('variants', [])
    recommended = data.get('recommended', data.get('recommended_index', 0))
    if isinstance(recommended, dict):
        return recommended
    if variants:
        try:
            return variants[int(recommended)]
        except (IndexError, ValueError, TypeError):
            return variants[0]
    return data

def publish_youtube(db, job):
    if free_mode():
        raise ValueError('External publishing is disabled in free local mode. Use the manual upload package.')
    clip = db.get(RenderedClip, job.clip_id)
    campaign = db.get(Campaign, clip.campaign_id)
    account = db.get(ConnectedAccount, job.account_id)
    plan = db.get(EditingPlan,clip.editing_plan_id)
    if not job.authorized or not account or account.user_id != job.user_id:
        raise ValueError('Explicit publishing authorization and a connected account are required.')
    if clip.current_version != job.version:
        raise ValueError('Clip changed after approval. Review and authorize the new version.')
    if clip.compliance.get('status') != 'PASS':
        raise ValueError('Compliance review must pass before publishing.')
    if campaign.rules!=plan.rules_snapshot or 'youtube' not in campaign.rules.get('allowed_platforms',[]):
        raise ValueError('Campaign rules changed or YouTube is not a permitted platform. Generate and review against current requirements.')
    if (campaign.rules.get('draft_approval_required') or campaign.rules.get('approval_required')) and not clip.draft_approved:
        raise ValueError('Campaign draft approval is required.')
    if submission_minutes(campaign.rules) and (not job.attended or job.scheduled_at is not None):
        raise ValueError('This campaign requires attended immediate publishing so you can submit before the deadline.')
    if submission_minutes(campaign.rules) and (job.authorization_expires_at is None or job.authorization_expires_at<now()):
        job.status='needs_authorization'
        job.error='Your attended publishing approval expired while waiting. Confirm you are present and retry to start publication.'
        job.upload_lease_until=None
        db.commit()
        return
    token = access_token(db, account)
    meta = selected_metadata(clip.metadata_json, 'youtube')
    with materialize(clip.storage_key) as path, httpx.Client(timeout=180) as client:
        state = dict(job.upload_state or {})
        session_url = state.get('session_url')
        if not session_url:
            title = str(meta.get('title') or clip.title)[:100]
            description = str(meta.get('description') or meta.get('caption') or '')
            hashtags = meta.get('hashtags', [])
            if hashtags:
                description += '\n\n' + ' '.join(hashtags)
            response = client.post('https://www.googleapis.com/upload/youtube/v3/videos', params={'part':'snippet,status','uploadType':'resumable'}, headers={'Authorization':f'Bearer {token}','X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(path.stat().st_size)}, json={'snippet':{'title':title,'description':description[:5000],'categoryId':'22'},'status':{'privacyStatus':job.privacy}})
            response.raise_for_status()
            session_url = response.headers.get('location')
            if not session_url or urlparse(session_url).scheme != 'https' or not (urlparse(session_url).hostname or '').endswith('.googleapis.com'):
                raise ValueError('YouTube did not return a valid resumable upload URL.')
            job.upload_state = {'session_url':session_url,'total':path.stat().st_size}
            db.commit()
        total = path.stat().st_size
        # Query the session first: retries resume bytes rather than creating a
        # duplicate videos.insert request after an ambiguous network failure.
        query = client.put(session_url, headers={'Authorization':f'Bearer {token}','Content-Length':'0','Content-Range':f'bytes */{total}'}, content=b'')
        if query.status_code in {200,201}:
            result = query.json()
        elif query.status_code == 308:
            last = query.headers.get('range','')
            offset = int(last.split('-')[-1])+1 if last else 0
            result = None
            with path.open('rb') as media:
                media.seek(offset)
                while offset < total:
                    chunk = media.read(8*1024*1024)
                    response = client.put(session_url, headers={'Authorization':f'Bearer {token}','Content-Type':'video/mp4','Content-Length':str(len(chunk)),'Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{total}'},content=chunk)
                    if response.status_code in {200,201}:
                        result = response.json()
                        break
                    if response.status_code != 308:
                        response.raise_for_status()
                        raise ValueError('Unexpected YouTube upload response.')
                    offset += len(chunk)
                    job.upload_lease_until=now()+timedelta(minutes=30)
                    db.commit()
            if result is None:
                raise ValueError('Upload incomplete. Retry resumes the existing upload session.')
        else:
            # Expired or rejected sessions require user review; never create a
            # fresh upload automatically when publication may already have occurred.
            raise ValueError(f'YouTube upload session returned {query.status_code}. Review the channel before retrying.')
    video_id = result.get('id')
    if not video_id:
        raise ValueError('YouTube upload succeeded without a video ID; review the channel.')
    privacy = result.get('status',{}).get('privacyStatus',job.privacy)
    job.upload_state = {**job.upload_state,'video_id':video_id,'privacy':privacy}
    if privacy != 'public':
        job.status = 'uploaded_private'
        job.error = 'Uploaded privately. No publication timestamp or submission countdown has been recorded. Make the post public and record its actual publication time.'
        db.commit()
        return
    # The official API response supplies the actual public publication timestamp.
    response = httpx.get('https://www.googleapis.com/youtube/v3/videos',params={'part':'snippet,status','id':video_id},headers={'Authorization':f'Bearer {token}'},timeout=60)
    response.raise_for_status()
    items = response.json().get('items',[])
    if (not items or items[0].get('status',{}).get('privacyStatus') != 'public'
            or items[0].get('status',{}).get('uploadStatus') != 'processed'
            or not items[0].get('snippet',{}).get('publishedAt')):
        job.status = 'awaiting_publication'
        job.error = 'Awaiting confirmed public publication timestamp.'
        db.commit()
        return
    from datetime import datetime
    timestamp = datetime.fromisoformat(items[0]['snippet']['publishedAt'].replace('Z','+00:00')).replace(tzinfo=None)
    post = PublishedPost(user_id=job.user_id,clip_id=clip.id,campaign_id=campaign.id,platform='youtube',url=f'https://www.youtube.com/watch?v={video_id}',published_at=timestamp,provenance='youtube_api')
    db.add(post)
    db.flush()
    create_submission(db,post,campaign)
    job.status = 'published'
    job.error = None
    db.add(AuditLog(user_id=job.user_id,action='post.published',entity_id=post.id,detail={'platform':'youtube','timestamp':timestamp.isoformat()}))
    db.commit()

def run_publish_once():
    with SessionLocal() as db:
        job = db.scalar(select(PublishingJob).where(PublishingJob.status == 'queued',or_(PublishingJob.scheduled_at.is_(None),PublishingJob.scheduled_at <= now())).order_by(PublishingJob.created_at).limit(1))
        if not job:
            return False
        result = db.execute(update(PublishingJob).where(PublishingJob.id == job.id,PublishingJob.status == 'queued').values(status='uploading',attempts=PublishingJob.attempts+1,upload_started_at=now(),upload_lease_until=now()+timedelta(minutes=30)))
        db.commit()
        if not result.rowcount:
            return False
        db.refresh(job)
        try:
            publish_youtube(db,job)
        except Exception as exc:
            job.status = 'failed'
            # Provider errors can contain request headers/URLs: store only a
            # stable exception category for http failures, never credential data.
            job.error = f'YouTube request failed ({exc.response.status_code}). Review and retry the existing upload.' if isinstance(exc,httpx.HTTPStatusError) else str(exc)[:800]
            db.commit()
        return True
