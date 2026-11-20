"""Opt-in official social adapters, encrypted credentials and explicit approval."""
import json
import os
import re
import secrets
import time
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode,urlparse
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import User,OAuthState,ConnectedAccount,PublishingJob,RenderedClip,EditingPlan,Campaign,DraftEvaluation,DraftDecision,PublishedPost,PlatformObservation,now
from .security import current_user,token_hash
from .runtime import social_enabled
from .config import settings
from .storage import materialize
from .publishing import cipher,access_token,selected_metadata

router=APIRouter(prefix='/api/social',tags=['Optional official social integrations'])


def require_approved_draft(db,clip):
    if db.scalar(select(DraftEvaluation.id).where(DraftEvaluation.clip_id==clip.id)):
        decision=db.scalar(select(DraftDecision).where(DraftDecision.clip_id==clip.id,DraftDecision.version==clip.current_version).order_by(DraftDecision.created_at.desc()))
        if not decision or decision.decision!='approved':
            raise HTTPException(409,'Approve the current draft version before publishing.')


def account_owned(db,key,user):
    account=db.get(ConnectedAccount,key)
    if not account or account.user_id!=user.id or account.status!='connected':
        raise HTTPException(404,'Connected account not found.')
    return account


def tiktok_configured():
    return social_enabled() and all(os.getenv(k) for k in ('TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REDIRECT_URI','TOKEN_ENCRYPTION_KEY'))


def tiktok_request(endpoint,token=None,**kwargs):
    # All endpoint names are application constants, never user-supplied URLs.
    with httpx.Client(timeout=60,follow_redirects=False,trust_env=False) as client:
        response=client.post('https://open.tiktokapis.com/v2/'+endpoint,
            headers={'Authorization':'Bearer '+token} if token else {},**kwargs)
    response.raise_for_status()
    payload=response.json()
    error=payload.get('error')
    if isinstance(error,dict) and error.get('code') not in {None,'ok'}:
        code=re.sub(r'[^a-zA-Z0-9_]', '',str(error.get('code','unknown')))[:80]
        raise HTTPException(502,'TikTok refused the request ('+code+'). Review account permissions and quota.')
    if isinstance(error,str) and error:
        raise HTTPException(502,'TikTok authorization failed. Reconnect your account.')
    return payload.get('data',payload)


def tiktok_token(db,account):
    if not social_enabled():raise HTTPException(503,'Social connections are disabled; local editing remains available.')
    credentials=json.loads(cipher().decrypt(account.encrypted_credentials.encode()))
    if credentials.get('expires_at',0)>time.time()+60:
        return credentials['access_token']
    try:
        if not credentials.get('refresh_token'):raise HTTPException(409,'Reconnect TikTok to grant offline account access.')
        updated=tiktok_request('oauth/token/',data={'client_key':os.environ['TIKTOK_CLIENT_KEY'],
            'client_secret':os.environ['TIKTOK_CLIENT_SECRET'],'grant_type':'refresh_token','refresh_token':credentials['refresh_token']})
    except (HTTPException,httpx.HTTPStatusError):
        account.status='reauthorization_required';db.commit();raise
    updated['expires_at']=time.time()+updated.get('expires_in',0)
    updated.setdefault('refresh_token',credentials['refresh_token'])
    account.encrypted_credentials=cipher().encrypt(json.dumps(updated).encode()).decode();db.commit()
    return updated['access_token']


@router.get('/configuration')
def configuration(user: User=Depends(current_user)):
    from .publishing import configured
    return {'enabled':social_enabled(),'youtube_configured':configured(),'tiktok_configured':tiktok_configured(),
        'missing_configuration':{p:[k for k in fields if not os.getenv(k)] for p,fields in {
            'youtube':('YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REDIRECT_URI','TOKEN_ENCRYPTION_KEY'),
            'tiktok':('TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REDIRECT_URI','TOKEN_ENCRYPTION_KEY')}.items()},
        'redirects':{'youtube':os.getenv('YOUTUBE_REDIRECT_URI',''),'tiktok':os.getenv('TIKTOK_REDIRECT_URI','')},
        'tiktok_public_posting_audit_confirmed':os.getenv('TIKTOK_DIRECT_POST_AUDITED','false').lower()=='true',
        'limitation':'Developer app credentials, approved scopes and platform review may be required. Unauthenticated tests are not real publishing. Offline editing requires no connected account.'}


@router.post('/tiktok/connect')
def tiktok_connect(user: User=Depends(current_user),db: Session=Depends(get_db)):
    if not tiktok_configured():raise HTTPException(503,'Enable social integrations and configure TikTok client/secret, registered HTTPS redirect and encryption key.')
    redirect=os.environ['TIKTOK_REDIRECT_URI']
    uri=urlparse(redirect)
    if uri.scheme!='https' or not uri.hostname or uri.query or uri.fragment:
        raise HTTPException(503,'TikTok Web Login requires a registered static HTTPS redirect URI.')
    state=secrets.token_urlsafe(32)
    db.add(OAuthState(user_id=user.id,state_hash=token_hash('tiktok:'+state),verifier='tiktok-web',expires_at=now()+timedelta(minutes=10)))
    db.commit()
    scopes=os.getenv('TIKTOK_SCOPES','user.info.basic,video.list')
    return {'url':'https://www.tiktok.com/v2/auth/authorize/?'+urlencode({'client_key':os.environ['TIKTOK_CLIENT_KEY'],
        'redirect_uri':redirect,'scope':scopes,'state':state,'response_type':'code'})}


@router.get('/tiktok/callback')
def tiktok_callback(state: str,code: str,request: Request,user: User=Depends(current_user),db: Session=Depends(get_db)):
    request.scope['query_string']=b''
    if not tiktok_configured():raise HTTPException(503,'TikTok connection is not configured.')
    row=db.scalar(select(OAuthState).where(OAuthState.user_id==user.id,OAuthState.state_hash==token_hash('tiktok:'+state),OAuthState.expires_at>now()))
    if not row:raise HTTPException(400,'Expired or invalid OAuth state. Connect again.')
    db.delete(row);db.commit()
    credentials=tiktok_request('oauth/token/',data={'client_key':os.environ['TIKTOK_CLIENT_KEY'],'client_secret':os.environ['TIKTOK_CLIENT_SECRET'],
        'code':code,'grant_type':'authorization_code','redirect_uri':os.environ['TIKTOK_REDIRECT_URI']})
    scopes=credentials.get('scope','').split(',')
    if 'user.info.basic' not in scopes:raise HTTPException(400,'TikTok basic account permission was not granted.')
    token=credentials['access_token']
    with httpx.Client(timeout=30,follow_redirects=False,trust_env=False) as client:
        response=client.get('https://open.tiktokapis.com/v2/user/info/',params={'fields':'open_id,display_name'},headers={'Authorization':'Bearer '+token})
    response.raise_for_status();profile=response.json().get('data',{}).get('user',{})
    external=credentials.get('open_id')
    if not external or profile.get('open_id')!=external:raise HTTPException(400,'TikTok account identity could not be verified.')
    account=db.scalar(select(ConnectedAccount).where(ConnectedAccount.user_id==user.id,ConnectedAccount.platform=='tiktok',ConnectedAccount.external_id==external))
    if not account:
        account=ConnectedAccount(user_id=user.id,platform='tiktok',external_id=external,name=profile.get('display_name','TikTok'),encrypted_credentials='');db.add(account)
    credentials['expires_at']=time.time()+credentials.get('expires_in',0)
    account.encrypted_credentials=cipher().encrypt(json.dumps(credentials).encode()).decode()
    account.scopes=scopes;account.status='connected';db.commit()
    return RedirectResponse(settings.frontend_url+'/?view=accounts&connected=tiktok')


@router.post('/accounts/{account_id}/creator-info')
def creator_info(account_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    account=account_owned(db,account_id,user)
    if account.platform!='tiktok':raise HTTPException(422,'Choose a TikTok account.')
    if 'video.publish' not in account.scopes:raise HTTPException(403,'Direct Post scope was not granted. Use the manual upload package.')
    return tiktok_request('post/publish/creator_info/query/',tiktok_token(db,account),json={})


class TikTokPublish(BaseModel):
    delivery: str=Field(default='direct',pattern='^(direct|inbox)$')
    account_id: str
    version: int
    explicit_authorization: bool
    privacy_level: str=Field(pattern='^(PUBLIC_TO_EVERYONE|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR|SELF_ONLY)$')
    consent_to_music_usage: bool
    brand_content_toggle: bool
    brand_organic_toggle: bool
    is_aigc: bool=False
    disable_comment: bool=True
    disable_duet: bool=True
    disable_stitch: bool=True


@router.post('/clips/{clip_id}/tiktok')
def authorize_tiktok(clip_id: str,body: TikTokPublish,user: User=Depends(current_user),db: Session=Depends(get_db)):
    if not social_enabled():raise HTTPException(503,'Social publishing is disabled. Export a manual upload package.')
    account=account_owned(db,body.account_id,user)
    clip=db.get(RenderedClip,clip_id)
    if not clip or clip.user_id!=user.id:raise HTTPException(404,'Draft not found.')
    if clip.current_version!=body.version:raise HTTPException(409,'Draft version changed. Review and approve again.')
    require_approved_draft(db,clip)
    if not body.explicit_authorization or not body.consent_to_music_usage:raise HTTPException(422,'Explicit posting consent and Music Usage Confirmation are required.')
    if clip.compliance.get('status')!='PASS':raise HTTPException(409,'Resolve campaign compliance before publishing.')
    campaign=db.get(Campaign,clip.campaign_id);plan=db.get(EditingPlan,clip.editing_plan_id)
    from .services.campaign_requirements import deadline_state
    if deadline_state(campaign.rules.get('submission_deadline'))=='expired':raise HTTPException(409,'Campaign deadline has expired.')
    if campaign.rules!=plan.rules_snapshot or 'tiktok' not in campaign.rules.get('allowed_platforms',[]) or 'tiktok' in campaign.rules.get('prohibited_platforms',[]):
        raise HTTPException(409,'Current campaign rules do not permit this TikTok draft.')
    if body.delivery=='inbox' and 'video.upload' not in account.scopes:raise HTTPException(403,'Reconnect with the approved video.upload scope for the TikTok inbox workflow.')
    if body.delivery=='direct' and body.privacy_level!='SELF_ONLY' and os.getenv('TIKTOK_DIRECT_POST_AUDITED','false').lower()!='true':
        raise HTTPException(403,'Unaudited TikTok clients may post privately only. Export for manual posting or complete the official audit.')
    info=creator_info(account.id,user,db) if body.delivery=='direct' else {}
    if body.delivery=='direct' and body.privacy_level not in info.get('privacy_level_options',[]):raise HTTPException(422,'Select a privacy setting offered by this creator account.')
    if clip.media_info['duration']>(info.get('max_video_post_duration_sec',0) if body.delivery=='direct' else 600):raise HTTPException(422,'Draft exceeds the creator account duration limit.')
    for key in ('comment','duet','stitch'):
        if info.get(key+'_disabled') and not getattr(body,'disable_'+key):raise HTTPException(422,'Creator settings prohibit enabling '+key+'.')
    existing=db.scalar(select(PublishingJob).where(PublishingJob.clip_id==clip.id,PublishingJob.platform=='tiktok',PublishingJob.version==clip.current_version))
    if existing:
        from .main import obj
        return obj(existing,'upload_state')
    job=PublishingJob(user_id=user.id,clip_id=clip.id,account_id=account.id,platform='tiktok',version=clip.current_version,
        authorized=True,privacy={'SELF_ONLY':'private','PUBLIC_TO_EVERYONE':'public','MUTUAL_FOLLOW_FRIENDS':'friends','FOLLOWER_OF_CREATOR':'followers'}[body.privacy_level],upload_state={'delivery':body.delivery,'post_info':body.model_dump(exclude={'account_id','version','explicit_authorization','consent_to_music_usage','delivery'})})
    db.add(job);db.commit()
    from .main import obj
    return obj(job,'upload_state')


def publish_tiktok(db,job):
    if not social_enabled():raise ValueError('Social integrations are disabled.')
    clip=db.get(RenderedClip,job.clip_id);account=db.get(ConnectedAccount,job.account_id)
    require_approved_draft(db,clip)
    if not job.authorized or not account or account.status!='connected' or account.user_id!=job.user_id or clip.current_version!=job.version or clip.compliance.get('status')!='PASS':
        raise ValueError('Current approved version, compliance and connected account are required.')
    campaign=db.get(Campaign,clip.campaign_id);plan=db.get(EditingPlan,clip.editing_plan_id)
    from .services.campaign_requirements import deadline_state
    if deadline_state(campaign.rules.get('submission_deadline'))=='expired':raise ValueError('Campaign deadline expired before publication.')
    if campaign.rules!=plan.rules_snapshot or 'tiktok' not in campaign.rules.get('allowed_platforms',[]) or 'tiktok' in campaign.rules.get('prohibited_platforms',[]):
        raise ValueError('Campaign changed or prohibits TikTok.')
    inbox=job.upload_state.get('delivery')=='inbox'
    if ('video.upload' if inbox else 'video.publish') not in account.scopes:raise ValueError('The required approved TikTok posting scope is unavailable; use manual export.')
    token=tiktok_token(db,account);state=dict(job.upload_state or {})
    privacy=state.get('post_info',{}).get('privacy_level')
    if not state.get('publish_id'):
        if state.get('init_attempted'):raise ValueError('An earlier TikTok initialization has an unknown result. Review the account before starting another upload.')
        info=tiktok_request('post/publish/creator_info/query/',token,json={}) if not inbox else {}
        if not inbox and privacy not in info.get('privacy_level_options',[]):raise ValueError('TikTok creator privacy options changed; review consent again.')
        if clip.media_info['duration']>(600 if inbox else info.get('max_video_post_duration_sec',0)):raise ValueError('Draft exceeds the current TikTok creator duration limit.')
        if not inbox and privacy!='SELF_ONLY' and os.getenv('TIKTOK_DIRECT_POST_AUDITED','false').lower()!='true':raise ValueError('Public Direct Post requires official TikTok audit.')
        meta=selected_metadata(clip.metadata_json,'tiktok')
        from .services.publication_text import publication_text
        caption=publication_text(meta,'tiktok')
        if len(caption.encode('utf-16-le'))//2>2200:raise ValueError('TikTok caption exceeds2200 UTF-16 units; review required text.')
        with materialize(clip.storage_key) as path:
            size=path.stat().st_size;chunk=min(size,10*1024*1024);count=max(1,size//chunk)
            state.update(init_attempted=True,total=size,chunk_size=chunk,chunk_count=count,offset=0)
            job.upload_state=state;db.commit()
            payload={'source_info':{'source':'FILE_UPLOAD','video_size':size,'chunk_size':chunk,'total_chunk_count':count}}
            if not inbox:payload['post_info']={**state['post_info'],'title':caption}
            init=tiktok_request('post/publish/inbox/video/init/' if inbox else 'post/publish/video/init/',token,json=payload)
        upload=urlparse(init.get('upload_url',''))
        if upload.scheme!='https' or not (upload.hostname or '').endswith('.tiktokapis.com') or upload.username or upload.password:
            raise ValueError('TikTok returned an invalid upload URL.')
        state.update(publish_id=init['publish_id'],upload_url=init['upload_url']);job.upload_state=state;db.commit()
    if state.get('offset',0)<state['total']:
        if state.get('chunk_inflight'):raise ValueError('A TikTok chunk has an unknown result. Check post status; no duplicate initialization was attempted.')
        with materialize(clip.storage_key) as path,path.open('rb') as stream,httpx.Client(timeout=180,follow_redirects=False,trust_env=False) as client:
            offset=state.get('offset',0);stream.seek(offset)
            while offset<state['total']:
                remaining=state['total']-offset
                size=remaining if remaining<2*state['chunk_size'] else state['chunk_size']
                chunk=stream.read(size)
                state['chunk_inflight']=True;job.upload_state=dict(state);db.commit()
                response=client.put(state['upload_url'],content=chunk,headers={'Content-Type':'video/mp4',
                    'Content-Length':str(len(chunk)),'Content-Range':f"bytes {offset}-{offset+len(chunk)-1}/{state['total']}"})
                if response.status_code not in {201,206}:response.raise_for_status();raise ValueError('Unexpected TikTok chunk response.')
                offset+=len(chunk);state.update(offset=offset,chunk_inflight=False);job.upload_state=dict(state);db.commit()
    status=tiktok_request('post/publish/status/fetch/',token,json={'publish_id':state['publish_id']})
    if status.get('status')=='FAILED':raise ValueError('TikTok rejected processing. Review content and account limits before retrying.')
    if inbox and status.get('status') in {'SEND_TO_USER_INBOX','PUBLISH_COMPLETE'}:
        job.status='uploaded_draft';job.error='Sent to your TikTok inbox. Finish editing and publish in TikTok. No public post or KPI was inferred.';db.commit();return
    if status.get('status')!='PUBLISH_COMPLETE':
        job.status='awaiting_publication';job.error='TikTok is processing this upload. No public publication is recorded.';db.commit();return
    if privacy=='SELF_ONLY':
        job.status='uploaded_private';job.error='TikTok confirmed private completion. No public post or views were invented.';db.commit();return
    ids=status.get('publicaly_available_post_id',status.get('publicly_available_post_id',[]))
    if not ids or 'video.list' not in account.scopes:
        job.status='awaiting_publication';job.error='Awaiting an authorized public video ID and actual publication time.';db.commit();return
    videos=tiktok_request('video/query/',token,params={'fields':'id,create_time,share_url'},json={'filters':{'video_ids':[str(ids[0])]}}).get('videos',[])
    if not videos or not videos[0].get('create_time') or not videos[0].get('share_url'):
        job.status='awaiting_publication';db.commit();return
    item=videos[0]
    from .submissions import validate_post_url,create_submission
    url=validate_post_url('tiktok',item['share_url'])
    post=db.scalar(select(PublishedPost).where(PublishedPost.user_id==job.user_id,PublishedPost.url==url))
    if not post:
        post=PublishedPost(user_id=job.user_id,clip_id=clip.id,campaign_id=clip.campaign_id,platform='tiktok',url=url,
            published_at=datetime.fromtimestamp(item['create_time'],timezone.utc).replace(tzinfo=None),provenance='tiktok_api')
        db.add(post);db.flush();create_submission(db,post,campaign)
    job.status='published';job.error=None;job.upload_state={**state,'video_id':str(item['id'])};db.commit()
