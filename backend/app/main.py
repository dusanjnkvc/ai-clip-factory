from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from contextlib import asynccontextmanager, ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete, update, text, or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .db import Base, engine, get_db
from .models import *
from .security import current_user, check_origin, hash_password, verify_password, create_session, rate_limit, audit, COOKIE, token_hash
from .storage import put_file, materialize, signed_url, local_path, download_token, verify_download_token
from .submissions import validate_post_url, create_submission, countdown, submission_minutes, estimate_earnings
from .publishing import configured as youtube_configured, authorization_url, finish_oauth
from .request_limits import RequestBodyLimitMiddleware
from .usage import record_usage
from .services.media import ConfigurationError, PipelineError
from .runtime import free_mode, local_no_auth, create_pipeline_service, social_enabled
import httpx


@asynccontextmanager
async def lifespan(app):
    settings.validate()
    if not settings.production:
        Base.metadata.create_all(engine)
    yield

app = FastAPI(title='AI Clip Factory API', version='0.1.0', lifespan=lifespan, dependencies=[Depends(check_origin)])
app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=(settings.max_upload_mb + 1) * 1024 * 1024)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=True, allow_methods=['GET','POST','PATCH','DELETE'], allow_headers=['Content-Type','X-Requested-With'])

@app.exception_handler(IntegrityError)
async def integrity_error(_, exc):
    return JSONResponse(status_code=409, content={'detail':'This record already exists. Refresh and try again.'})

@app.exception_handler(ConfigurationError)
async def provider_configuration_error(_, exc):
    return JSONResponse(status_code=503, content={'detail':str(exc)[:1200]})

@app.exception_handler(PipelineError)
async def pipeline_error(_, exc):
    return JSONResponse(status_code=502, content={'detail':str(exc)[:1200]})

@app.exception_handler(httpx.HTTPError)
async def external_service_error(_, exc):
    status=exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
    detail=('The provider rejected authorization. Reconnect the account and check granted permissions.' if status in {401,403}
        else 'The provider quota or rate limit was reached. Retry later.' if status==429
        else 'The local model or optional platform service is unavailable. Check its status and retry.')
    # Provider errors can contain signed upload URLs and tokens; never echo them.
    return JSONResponse(status_code=503 if status==429 or status is None else 502,content={'detail':detail})

def public_time(value):
    return value.isoformat() + 'Z' if value else None

def obj(row, *omit):
    result = {}
    for column in row.__table__.columns:
        if column.name not in omit:
            value = getattr(row,column.name)
            result[column.name] = public_time(value) if isinstance(value,datetime) else value
    return result

def owned(db, cls, record_id, user):
    row = db.get(cls, record_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, 'Record not found.')
    return row

def pipeline():
    return create_pipeline_service()

def rights_for(db,source_id,user_id):
    record=db.scalar(select(MediaRightsRecord).where(MediaRightsRecord.source_id==source_id,MediaRightsRecord.user_id==user_id,MediaRightsRecord.confirmed.is_(True)))
    return {'authorized':bool(record),'confirmed':bool(record),'attestation':record.note if record else ''}

def reserve_ai_budget(db,user,amount,job_id=None):
    # A no-op row write serializes allowance decisions per user in PostgreSQL
    # and obtains SQLite's write lock before the aggregate is read.
    db.execute(update(User).where(User.id==user.id).values(name=User.name))
    if db.bind.dialect.name=='postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(7126043101)'))
    db.refresh(user)
    month_start=now().replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    reserved=db.scalar(select(func.coalesce(func.sum(ProcessingCost.amount),0)).where(ProcessingCost.user_id==user.id,ProcessingCost.kind=='reserved',ProcessingCost.created_at>=month_start))
    monthly=float(user.preferences.get('monthly_spend_limit_usd',settings.monthly_limit))
    global_reserved=db.scalar(select(func.coalesce(func.sum(ProcessingCost.amount),0)).where(ProcessingCost.kind=='reserved',ProcessingCost.created_at>=month_start))
    if amount<=0 or reserved+amount>monthly or global_reserved+amount>settings.monthly_limit:
        raise HTTPException(402,'Monthly processing allowance exhausted. Review spending settings and provider usage.')
    db.add(ProcessingCost(user_id=user.id,job_id=job_id,amount=amount,kind='reserved',provider='budget_allowance'))
    db.flush()

def reserve_analysis(db,user_id):
    if not free_mode() and os.getenv('OPENAI_API_KEY'):
        user=db.get(User,user_id)
        rate_limit('paid-analysis:'+user_id,limit=30,seconds=3600)
        reserve_ai_budget(db,user,min(float(os.getenv('MAX_ANALYSIS_COST_USD','0.25')),settings.max_job_cost))
        db.commit()  # Keep reservations even if a provider request fails ambiguously.

def configuration():
    try:
        import imageio_ffmpeg
        ffmpeg_available = Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
    except Exception:
        ffmpeg_available = bool(shutil.which(os.getenv('FFMPEG_BINARY','ffmpeg')))
    return {'free_mode':free_mode(), 'local_no_auth':local_no_auth(), 'browser_mode':False, 'processing_provider':'local_manual' if free_mode() else 'hosted_ai',
        'external_calls_enabled':not free_mode(), 'ai':not free_mode() and bool(os.getenv('OPENAI_API_KEY')), 'ffmpeg':ffmpeg_available,
        'storage':'s3' if not free_mode() and os.getenv('S3_BUCKET') else 'local', 'youtube':youtube_configured(),
        'ai_model':os.getenv('AI_MODEL','gpt-4o-mini'), 'transcription_model':os.getenv('TRANSCRIPTION_MODEL','whisper-1'),
        'max_upload_mb':settings.max_upload_mb,'monthly_spend_limit_usd':settings.monthly_limit,
        'max_job_cost_usd':settings.max_job_cost,'retention_days':settings.retention_days,
        'publishing':{'youtube':'manual_package' if free_mode() else 'official_oauth' if youtube_configured() else 'configuration_required','tiktok':'manual_package','instagram':'manual_package','content_rewards':'manual_submission'},
        'budget_note':'Job reservations are conservative spending controls. Reconcile provider invoices; external provider billing is not a hard real-time cap.'}

class Registration(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=12,max_length=256)
    name: str = Field(min_length=1,max_length=100)

class Login(BaseModel):
    email: str = Field(min_length=3,max_length=254)
    password: str = Field(min_length=1,max_length=256)

@app.get('/api/health')
def health():
    return {'status':'ok','version':'0.2.0','free_mode':free_mode(),'local_no_auth':local_no_auth(),'browser_mode':False}

@app.get('/api/local-ai/status')
def local_ai_status(user: User=Depends(current_user)):
    from .services.ollama_provider import OllamaProvider
    return OllamaProvider().status(require_vision=True)

@app.post('/api/auth/register')
def register(body: Registration, response: Response, request: Request, db: DBSession=Depends(get_db)):
    rate_limit('register:'+(request.client.host if request.client else 'unknown'),limit=8)
    email = body.email.strip().lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise HTTPException(422,'Enter a valid email address.')
    if db.scalar(select(User.id).where(User.email==email)):
        raise HTTPException(409,'An account already exists with this email.')
    user = User(email=email,name=body.name.strip(),password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit(db,user.id,'auth.registered',user.id)
    create_session(db,user,response)
    return obj(user,'password_hash','preferences')

@app.post('/api/auth/login')
def login(body: Login, response: Response, request: Request, db: DBSession=Depends(get_db)):
    rate_limit('login:'+(request.client.host if request.client else 'unknown'))
    user = db.scalar(select(User).where(User.email==body.email.strip().lower()))
    if not user or not verify_password(body.password,user.password_hash):
        # Equivalent scrypt work for unknown accounts reduces timing enumeration.
        if not user:
            hash_password('invalid-account-password')
        raise HTTPException(401,'Email or password is incorrect.')
    create_session(db,user,response)
    return obj(user,'password_hash','preferences')

@app.get('/api/auth/me')
def me(user: User=Depends(current_user)):
    return {**obj(user,'password_hash','preferences'),'local_workspace':local_no_auth()}

@app.post('/api/auth/logout')
def logout(response: Response,request: Request,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash==token_hash(request.cookies.get(COOKIE,''))))
    db.commit()
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True}

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1,max_length=250)
    brief: str = Field(default='',max_length=100000)
    url: str | None = Field(default=None,max_length=2048)

def analyze_campaign_record(db, campaign):
    service = pipeline()
    try:
        reserve_analysis(db,campaign.user_id)
        with ExitStack() as stack:
            attachments = []
            for attachment in campaign.attachments:
                path = stack.enter_context(materialize(attachment['storage_key']))
                attachments.append({**attachment,'path':str(path)})
            data = service.analyze_campaign(campaign.brief,source_url=campaign.url,attachments=attachments)
        campaign.rules = data.get('rules',{})
        campaign.evidence = data.get('evidence',[])
        campaign.review_required = data.get('review_required',True)
        campaign.status = 'review' if campaign.review_required else 'active'
        campaign.analysis_error = None
        version = db.scalar(select(func.count()).select_from(CampaignRule).where(CampaignRule.campaign_id==campaign.id)) or 0
        db.add(CampaignRule(campaign_id=campaign.id,version=version+1,rules=campaign.rules,evidence=campaign.evidence))
    except HTTPException:
        raise
    except Exception as exc:
        campaign.analysis_error = str(exc)[:1200]
        campaign.status = 'draft'
        campaign.review_required = True
    record_usage(db, service, campaign.user_id)
    db.commit()
    return obj(campaign)

@app.post('/api/campaigns')
def create_campaign(body: CampaignCreate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    if body.url and urlparse(body.url).scheme != 'https':
        raise HTTPException(422,'Campaign URLs must use HTTPS. Paste private requirements or upload files; URLs are never scraped.')
    campaign = Campaign(user_id=user.id,name=body.name.strip(),brief=body.brief,url=body.url)
    db.add(campaign)
    db.flush()
    audit(db,user.id,'campaign.created',campaign.id)
    db.commit()
    if not body.brief.strip():
        campaign.analysis_error = 'Paste campaign requirements or upload a PDF/screenshot. A URL alone does not provide the campaign rules.'
        db.commit()
        return obj(campaign)
    return analyze_campaign_record(db,campaign)

@app.get('/api/campaigns')
def campaigns(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(c) for c in db.scalars(select(Campaign).where(Campaign.user_id==user.id).order_by(Campaign.created_at.desc()))]

@app.post('/api/campaigns/{campaign_id}/analyze')
def analyze_campaign(campaign_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    rate_limit('campaign-analysis:'+user.id,limit=10,seconds=3600)
    return analyze_campaign_record(db,owned(db,Campaign,campaign_id,user))

class RulesUpdate(BaseModel):
    rules: dict
    note: str = Field(min_length=8,max_length=4000)

@app.patch('/api/campaigns/{campaign_id}/rules')
def update_rules(campaign_id: str,body: RulesUpdate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    campaign = owned(db,Campaign,campaign_id,user)
    if len(json.dumps(body.rules)) > 100000:
        raise HTTPException(422,'Campaign rules are too large.')
    from .services.schemas import CampaignRules
    try:
        rules = CampaignRules.model_validate(body.rules).model_dump()
    except Exception as exc:
        raise HTTPException(422,f'Invalid campaign rules: {str(exc)[:600]}')
    evidence = list(campaign.evidence)+[{'source':'manual_review','note':body.note,'reviewed_by':user.id,'reviewed_at':public_time(now())}]
    campaign.rules = rules
    campaign.evidence = evidence
    campaign.review_required = bool(rules.get('uncertainties') or rules.get('contradictions'))
    campaign.status = 'review' if campaign.review_required else 'active'
    campaign.analysis_error = None
    version = db.scalar(select(func.count()).select_from(CampaignRule).where(CampaignRule.campaign_id==campaign.id)) or 0
    db.add(CampaignRule(campaign_id=campaign.id,version=version+1,rules=rules,evidence=evidence,reviewed_by=user.id))
    audit(db,user.id,'campaign.rules_reviewed',campaign.id,note=body.note)
    db.commit()
    return obj(campaign)

@app.post('/api/campaigns/{campaign_id}/attachments')
def campaign_attachment(campaign_id: str,file: UploadFile=File(...),user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    campaign = owned(db,Campaign,campaign_id,user)
    if len(campaign.attachments) >= 10:
        raise HTTPException(422,'A campaign supports at most 10 attachments.')
    suffix = Path(file.filename or '').suffix.lower()
    mimes = {'.pdf':'application/pdf','.txt':'text/plain','.docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}
    if suffix not in mimes:
        raise HTTPException(422,'Upload PDF, TXT, DOCX, PNG or JPEG.')
    with tempfile.TemporaryDirectory(prefix='acf-brief-') as temp:
        path = Path(temp)/('attachment'+suffix)
        size = save_upload(file,path,15*1024*1024)
        with path.open('rb') as attached:
            magic = attached.read(8)
        if not ((suffix=='.txt' and b'\x00' not in magic) or (suffix=='.docx' and magic.startswith(b'PK')) or (suffix=='.pdf' and magic.startswith(b'%PDF')) or (suffix=='.png' and magic.startswith(b'\x89PNG\r\n\x1a\n')) or (suffix in {'.jpg','.jpeg'} and magic.startswith(b'\xff\xd8\xff'))):
            raise HTTPException(422,'File content does not match its extension.')
        key = f'{user.id}/campaigns/{campaign.id}/{uid()}{suffix}'
        put_file(path,key)
    attachment = {'filename':Path(file.filename or 'attachment').name,'storage_key':key,'mime_type':mimes[suffix],'size_bytes':size}
    campaign.attachments = [*campaign.attachments,attachment]
    audit(db,user.id,'campaign.attachment_added',campaign.id,filename=attachment['filename'])
    db.commit()
    return analyze_campaign_record(db,campaign)

def save_upload(file, path, maximum):
    size = 0
    with path.open('wb') as output:
        while chunk := file.file.read(1024*1024):
            size += len(chunk)
            if size > maximum:
                raise HTTPException(413,f'File exceeds {maximum//1024//1024} MB.')
            output.write(chunk)
    if size == 0:
        raise HTTPException(422,'The file is empty.')
    return size

@app.post('/api/sources')
def upload_source(file: UploadFile=File(...),rights_confirmed: bool=Form(...),rights_note: str=Form(...),user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    rate_limit('upload:'+user.id,limit=15,seconds=3600)
    if not rights_confirmed or len(rights_note.strip()) < 8:
        raise HTTPException(422,'Confirm that you own or have permission to edit and republish this video, and describe the authorization.')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.mp4','.mov','.mkv','.webm','.m4v'}:
        raise HTTPException(422,'Supported source files: MP4, MOV, MKV, WebM, M4V.')
    with tempfile.TemporaryDirectory(prefix='acf-upload-') as temp:
        path = Path(temp)/('source'+suffix)
        size = save_upload(file,path,settings.max_upload_mb*1024*1024)
        with path.open('rb') as media:
            digest = hashlib.file_digest(media,'sha256').hexdigest()
        existing = db.scalar(select(SourceVideo).where(SourceVideo.user_id==user.id,SourceVideo.sha256==digest))
        if existing:
            return obj(existing,'storage_key')
        try:
            info = pipeline().probe_media(path)
        except Exception as exc:
            raise HTTPException(422,'The file is not a valid readable video. '+str(exc)[:400])
        if not info.get('duration') or info['duration'] < 1 or info['duration'] > 3600:
            raise HTTPException(422,'Source videos must be between 1 second and 60 minutes.')
        source = SourceVideo(user_id=user.id,filename=Path(file.filename or 'source').name,storage_key='pending',sha256=digest,size_bytes=size,media_info={k:v for k,v in info.items() if k!='path'})
        db.add(source)
        db.flush()
        key = f'{user.id}/sources/{source.id}{suffix}'
        put_file(path,key)
        source.storage_key = key
        db.add(MediaRightsRecord(source_id=source.id,user_id=user.id,confirmed=True,note=rights_note[:4000]))
        audit(db,user.id,'source.uploaded',source.id,sha256=digest,rights_note=rights_note[:4000])
        db.commit()
    return obj(source,'storage_key')

@app.get('/api/sources')
def sources(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(s,'storage_key') for s in db.scalars(select(SourceVideo).where(SourceVideo.user_id==user.id).order_by(SourceVideo.created_at.desc()))]

@app.post('/api/sources/{source_id}/subtitles')
def upload_subtitles(source_id: str,file: UploadFile=File(...),user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    source=owned(db,SourceVideo,source_id,user)
    rate_limit('subtitles:'+user.id,limit=20,seconds=3600)
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.source_id==source.id,ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Wait for this source’s active render to finish before replacing its subtitles.')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in {'.srt','.vtt'}:
        raise HTTPException(422,'Upload an SRT or WebVTT subtitle file.')
    raw=file.file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:
        raise HTTPException(413,'Subtitle files are limited to 2 MB.')
    try:
        from .services.local import parse_subtitles
        transcript=parse_subtitles(raw.decode('utf-8-sig'),suffix.lstrip('.'),source.media_info['duration'])
    except (UnicodeDecodeError,ValueError,PipelineError) as exc:
        raise HTTPException(422,'Invalid subtitle file: '+str(exc)[:600])
    row=db.scalar(select(Transcript).where(Transcript.source_id==source.id))
    if row:
        row.content=transcript
        row.provider='manual_subtitle_upload'
    else:
        db.add(Transcript(source_id=source.id,content=transcript,provider='manual_subtitle_upload'))
    audit(db,user.id,'source.subtitles_imported',source.id,filename=Path(file.filename or '').name,cues=len(transcript.get('segments',[])),timing='supplied_cue_timestamps')
    db.commit()
    return {'source_id':source.id,'provider':'manual_subtitle_upload','cues':len(transcript.get('segments',[])),'timing':'cue','word_timing_available':False}

class ManualSelection(BaseModel):
    model_config={'allow_inf_nan':False}
    start: float = Field(default=0,ge=0)
    end: float | None = Field(default=None,gt=0)
    title: str = Field(default='',max_length=100)
    description: str = Field(default='',max_length=2000)
    hashtags: list[str] = Field(default_factory=list,max_length=30)
    crop_x: float = Field(default=.5,ge=0,le=1)
    crop_y: float = Field(default=.5,ge=0,le=1)
    zoom: float = Field(default=1,ge=1,le=1.5)
    subtitle_style: Literal['clean','bold','podcast','gaming','karaoke'] = 'clean'
    hook: str = Field(default='',max_length=140)
    show_hook: bool = False

class JobCreate(BaseModel):
    campaign_id: str
    source_id: str
    mode: Literal['fast','quality'] = 'fast'
    clip_count: int = Field(default=1,ge=1,le=5)
    manual_selection: ManualSelection | None = None

@app.post('/api/jobs')
def create_job(body: JobCreate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    campaign = owned(db,Campaign,body.campaign_id,user)
    source = owned(db,SourceVideo,body.source_id,user)
    if free_mode() and not campaign.rules and campaign.brief.strip():
        analyze_campaign_record(db,campaign)
    if not campaign.rules:
        raise HTTPException(422,'Extract the supplied campaign rules or save reviewed rules before rendering clips.')
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.user_id==user.id,ProcessingJob.source_id==source.id,ProcessingJob.campaign_id==campaign.id,ProcessingJob.status.in_(['queued','processing'])))
    if active:
        raise HTTPException(409,'This source already has an active job for this campaign.')
    # Reserve the full per-job allowance conservatively, including failed jobs
    # that may have incurred provider usage. Reconcile actual provider invoices.
    payload={}
    if free_mode():
        if body.clip_count!=1 or body.manual_selection is None:
            raise HTTPException(422,'Free local rendering needs one manual clip selection. Set start/end times in Create Clips.')
        from .services.local import build_manual_plan
        transcript=db.scalar(select(Transcript).where(Transcript.source_id==source.id))
        try:
            build_manual_plan(body.manual_selection.model_dump(),{**source.media_info,'filename':source.filename},transcript.content if transcript else {},campaign.rules)
        except (ValueError,PipelineError) as exc:
            raise HTTPException(422,str(exc)[:800])
        payload={'processing_provider':'local_manual','manual_selection':body.manual_selection.model_dump()}
    per_job = 0 if free_mode() else min(float(user.preferences.get('max_job_cost_usd',settings.max_job_cost)),settings.max_job_cost)
    job = ProcessingJob(user_id=user.id,campaign_id=campaign.id,source_id=source.id,mode=body.mode,clip_count=body.clip_count,rules_snapshot=campaign.rules,cost_reservation=per_job,payload=payload)
    db.add(job)
    db.flush()
    if not free_mode():
        reserve_ai_budget(db,user,per_job,job.id)
    audit(db,user.id,'job.queued',job.id,mode=job.mode,clips=job.clip_count,cost_reservation=per_job)
    db.commit()
    return obj(job)

@app.get('/api/jobs')
def jobs(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(j) for j in db.scalars(select(ProcessingJob).where(ProcessingJob.user_id==user.id).order_by(ProcessingJob.created_at.desc()).limit(100))]

@app.post('/api/jobs/{job_id}/retry')
def retry_job(job_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    job = owned(db,ProcessingJob,job_id,user)
    if job.status not in {'failed','blocked','cancelled'} or job.attempts>=3:
        raise HTTPException(409,'Only stopped jobs with fewer than 3 attempts can resume.')
    if free_mode() and not (job.payload.get('manual_selection') or job.payload.get('plan') or job.payload.get('processing_provider')=='local_ai'):
        raise HTTPException(422,'This old AI job has no manual selection. Create a new free local render with start/end times.')
    if not free_mode():
        reserve_ai_budget(db,user,job.cost_reservation,job.id)
    job.status='queued'
    job.stage='Resuming persisted work'
    job.error=None
    job.payload={**job.payload,'cancel_requested':False}
    audit(db,user.id,'job.retried',job.id)
    db.commit()
    return obj(job)

def clip_json(clip):
    return {**obj(clip,'storage_key'),'metadata':clip.metadata_json,'preview_url':f'/api/clips/{clip.id}/video','download_url':f'/api/clips/{clip.id}/download'}

@app.get('/api/clips')
def clips(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [clip_json(c) for c in db.scalars(select(RenderedClip).where(RenderedClip.user_id==user.id).order_by(RenderedClip.created_at.desc()).limit(200))]

@app.get('/api/clips/{clip_id}')
def clip_detail(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    plan=db.get(EditingPlan,clip.editing_plan_id)
    versions=list(db.scalars(select(ClipVersion).where(ClipVersion.clip_id==clip.id).order_by(ClipVersion.version)))
    return {**clip_json(clip),'plan':plan.plan,'versions':[obj(v,'storage_key') for v in versions]}

@app.get('/api/clips/{clip_id}/video')
def video(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    url=signed_url(clip.storage_key)
    if url:
        return RedirectResponse(url)
    path=local_path(clip.storage_key)
    if not path.is_file():
        raise HTTPException(410,'This clip has expired under the configured retention policy.')
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, no-store'})

@app.get('/api/clips/{clip_id}/download')
def download(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    url=signed_url(clip.storage_key)
    if url:
        return RedirectResponse(url)
    path=local_path(clip.storage_key)
    if not path.is_file():
        raise HTTPException(410,'This clip is no longer available.')
    return FileResponse(path,media_type='video/mp4',filename=f'ai-clip-{clip.id[:8]}.mp4')

@app.post('/api/clips/{clip_id}/signed-download')
def signed_download(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    url=signed_url(clip.storage_key)
    expires=int(time.time())+900
    if not url:
        try:
            signature=download_token(clip.id,user.id,expires)
        except ValueError as exc:
            raise HTTPException(503,str(exc))
        url=f'{settings.api_base_url}/api/download/{clip.id}?user_id={user.id}&expires={expires}&signature={signature}'
    return {'url':url,'expires_at':expires}

@app.get('/api/download/{clip_id}')
def token_download(clip_id: str,user_id: str,expires: int,signature: str,db: DBSession=Depends(get_db)):
    if not verify_download_token(clip_id,user_id,expires,signature):
        raise HTTPException(403,'Download link expired or invalid.')
    clip=db.get(RenderedClip,clip_id)
    if not clip or clip.user_id!=user_id:
        raise HTTPException(404,'Clip not found.')
    path=local_path(clip.storage_key)
    if not path.is_file():
        raise HTTPException(410,'Clip no longer available.')
    return FileResponse(path,media_type='video/mp4',filename=f'ai-clip-{clip.id[:8]}.mp4')

class ClipMetadataUpdate(BaseModel):
    metadata: dict

@app.patch('/api/clips/{clip_id}/metadata')
def update_metadata(clip_id: str,body: ClipMetadataUpdate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    if len(json.dumps(body.metadata))>100000:
        raise HTTPException(422,'Metadata is too large.')
    from .services.schemas import Metadata
    from .services.campaign_requirements import enforce_metadata
    plan=db.get(EditingPlan,clip.editing_plan_id)
    try:
        supplied=Metadata.model_validate(body.metadata).model_dump()
        validated = Metadata.model_validate({p:{**block,'variants':[enforce_metadata(v,plan.rules_snapshot) for v in block['variants']]} for p,block in supplied.items()}).model_dump()
    except ValueError:
        raise HTTPException(422,'Metadata must contain three complete validated variants for each platform.')
    body.metadata=validated
    clip.metadata_json=validated
    chosen=validated['youtube']
    clip.title=chosen['variants'][chosen['recommended_index']]['title']
    clip.current_version+=1
    clip.draft_approved=False
    previous_score=db.scalar(select(DraftEvaluation).where(DraftEvaluation.clip_id==clip.id,DraftEvaluation.version==clip.current_version-1).order_by(DraftEvaluation.created_at.desc()))
    if previous_score and previous_score.evaluation.get('visual'):
        from .services.viral_score import score_metadata
        updated={**previous_score.evaluation,'platforms':score_metadata(previous_score.evaluation['visual'],validated),
                 'recalculation':'Metadata changed; actual unchanged artifact samples reused. Research not refreshed.'}
        db.add(DraftEvaluation(clip_id=clip.id,version=clip.current_version,artifact_sha256=previous_score.artifact_sha256,evaluation=updated))
    clip.compliance=pipeline().check_compliance(plan.plan,body.metadata,plan.rules_snapshot,rights_for(db,clip.source_id,user.id),clip.media_info,draft_approved=False)
    clip.status='ready' if clip.compliance['status']=='PASS' else 'review'
    db.add(ClipVersion(clip_id=clip.id,version=clip.current_version,plan=plan.plan,metadata_json=body.metadata,storage_key=clip.storage_key))
    db.add(ComplianceCheck(clip_id=clip.id,version=clip.current_version,status=clip.compliance['status'],checks=clip.compliance['checks'],rules_snapshot=plan.rules_snapshot))
    audit(db,user.id,'clip.metadata_updated',clip.id,version=clip.current_version)
    db.commit()
    return clip_json(clip)

class ReviewUpdate(BaseModel):
    evidence: dict = Field(default_factory=dict)
    draft_approved: bool = False
    note: str = Field(min_length=8,max_length=4000)

@app.post('/api/clips/{clip_id}/review')
def review_clip(clip_id: str,body: ReviewUpdate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    plan=db.get(EditingPlan,clip.editing_plan_id)
    allowed={'branding','content_restrictions','audio_restrictions','source_material','campaign_uncertainties','campaign_contradictions','platforms','approval_requirement','disclosures','campaign_evidence','creative_context','manual_editing','original_footage','music_restrictions','ai_voice_restrictions','paid_promotion','prohibited_footage','audience_restrictions','on_video_text','resolution_requirements','logo_requirements','other_requirements'}
    allowed.add('submission_deadline')
    evidence={}
    for rule,value in body.evidence.items():
        if rule not in allowed or not isinstance(value,dict) or value.get('confirmed') is not True or len(str(value.get('note','')).strip())<8:
            raise HTTPException(422,'Each semantic review requires a supported rule, confirmation and a meaningful evidence note.')
        evidence[rule]={'confirmed':True,'note':str(value['note'])[:4000],'reviewed_by':user.id,'reviewed_at':public_time(now())}
    clip.draft_approved=body.draft_approved
    result=pipeline().check_compliance(plan.plan,clip.metadata_json,plan.rules_snapshot,rights_for(db,clip.source_id,user.id),clip.media_info,draft_approved=clip.draft_approved,semantic_evidence=evidence)
    clip.compliance={**result,'semantic_evidence':evidence,'review_note':body.note}
    clip.status='ready' if result['status']=='PASS' else 'review'
    db.add(ComplianceCheck(clip_id=clip.id,version=clip.current_version,status=result['status'],checks=result['checks'],rules_snapshot=plan.rules_snapshot))
    audit(db,user.id,'clip.reviewed',clip.id,note=body.note,draft_approved=body.draft_approved,evidence=evidence)
    db.commit()
    return clip_json(clip)

@app.post('/api/clips/{clip_id}/regenerate-metadata')
def regenerate_metadata(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    if free_mode():
        raise HTTPException(503,'AI metadata regeneration is disabled in free mode. Edit and save the title, caption and hashtags manually.')
    rate_limit('metadata:'+user.id,limit=10,seconds=3600)
    clip=owned(db,RenderedClip,clip_id,user)
    plan=db.get(EditingPlan,clip.editing_plan_id)
    reserve_analysis(db,user.id)
    service = pipeline()
    try:
        metadata=service.generate_metadata(plan.plan,plan.rules_snapshot)
    finally:
        record_usage(db, service, user.id)
        db.commit()
    return update_metadata(clip_id,ClipMetadataUpdate(metadata=metadata),user,db)

@app.get('/api/clips/{clip_id}/package')
def manual_package(clip_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    # A manual package is a downloadable artifact, never a publication claim.
    temporary=tempfile.NamedTemporaryFile(prefix='acf-package-',suffix='.zip',delete=False)
    temporary.close()
    path=Path(temporary.name)
    with materialize(clip.storage_key) as media,zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.write(media,'clip.mp4')
        archive.writestr('metadata.json',json.dumps(clip.metadata_json,ensure_ascii=False,indent=2))
        archive.writestr('compliance.json',json.dumps(clip.compliance,ensure_ascii=False,indent=2))
        archive.writestr('README.txt','Review compliance and campaign draft approval before uploading. Upload through your authorized account. Record the actual public URL and publication timestamp in AI Clip Factory. Submit through the campaign link; this package does not publish or submit content.')
    from starlette.background import BackgroundTask
    return FileResponse(path,media_type='application/zip',filename=f'upload-package-{clip.id[:8]}.zip',background=BackgroundTask(path.unlink,missing_ok=True))

class RegenerateRequest(BaseModel):
    plan: dict | None = None
    optimize_metadata: bool = False
    mode: Literal['fast','quality'] = 'fast'

@app.post('/api/clips/{clip_id}/regenerate')
def regenerate_clip(clip_id: str,body: RegenerateRequest,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    original=db.get(EditingPlan,clip.editing_plan_id)
    override=None
    if body.plan:
        from .services.schemas import ClipPlan
        try:
            override=ClipPlan.model_validate(body.plan).model_dump()
        except Exception as exc:
            raise HTTPException(422,'Invalid editing timeline: '+str(exc)[:600])
        source=db.get(SourceVideo,clip.source_id)
        if override['end']>source.media_info['duration']:
            raise HTTPException(422,'The timeline extends beyond the source video.')
    if free_mode() and body.optimize_metadata:
        raise HTTPException(422,'Use the manual metadata editor in free mode. AI optimization is disabled.')
    # The same budget and duplicate-job guard used for initial generation applies.
    selected_plan=override or original.plan
    selection=None
    if free_mode():
        scene=selected_plan.get('scenes',[{}])[0]
        selection=ManualSelection(start=selected_plan['start'],end=selected_plan['end'],title=selected_plan['title'],crop_x=scene.get('crop_x',.5),crop_y=scene.get('crop_y',.5),zoom=scene.get('zoom',1),subtitle_style=selected_plan.get('subtitle_style','clean'))
    result=create_job(JobCreate(campaign_id=clip.campaign_id,source_id=clip.source_id,mode=body.mode,clip_count=1,manual_selection=selection),user,db)
    job=db.get(ProcessingJob,result['id'])
    job.rules_snapshot=original.rules_snapshot
    job.payload={'clip_id':clip.id,'base_version':clip.current_version}
    if override:
        job.payload={**job.payload,'plan':override}
    elif free_mode():
        job.payload={**job.payload,'plan':original.plan}
    if not body.optimize_metadata:
        job.payload={**job.payload,'metadata':clip.metadata_json}
    has_evaluation=bool(db.scalar(select(DraftEvaluation.id).where(DraftEvaluation.clip_id==clip.id)))
    if has_evaluation or clip.media_info.get('renderer')=='remotion':
        job.payload={**job.payload,'processing_provider':'local_ai','options':{'studio':has_evaluation,'render_engine':'remotion' if clip.media_info.get('renderer')=='remotion' else 'ffmpeg'}}
    db.commit()
    return obj(job)

@app.get('/api/accounts')
def accounts(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(a,'encrypted_credentials') for a in db.scalars(select(ConnectedAccount).where(ConnectedAccount.user_id==user.id))]

@app.post('/api/accounts/youtube/connect')
def youtube_connect(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return {'url':authorization_url(db,user.id)}

@app.get('/api/accounts/youtube/callback')
def youtube_callback(state: str,code: str,request: Request,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    request.scope['query_string']=b''
    finish_oauth(db,user,state,code)
    return RedirectResponse(settings.frontend_url+'/?view=accounts&connected=youtube')

@app.delete('/api/accounts/{account_id}')
def disconnect_account(account_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    account=owned(db,ConnectedAccount,account_id,user)
    # Keep historical references but erase credentials immediately.
    account.status='disconnected'
    account.encrypted_credentials=''
    db.query(PublishingJob).filter(PublishingJob.account_id==account.id,PublishingJob.status=='queued').update({'status':'cancelled'})
    audit(db,user.id,'account.disconnected',account.id)
    db.commit()
    return {'ok':True}

class PublishRequest(BaseModel):
    account_id: str
    explicit_authorization: bool
    attended: bool = True
    privacy: Literal['public','private','unlisted'] = 'private'
    scheduled_at: datetime | None = None
    made_for_kids: bool | None = None
    version: int | None = None

@app.post('/api/clips/{clip_id}/publish')
def authorize_publish(clip_id: str,body: PublishRequest,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    if not social_enabled():
        raise HTTPException(503,'Free local mode creates manual upload packages. Direct platform publishing is disabled.')
    clip=owned(db,RenderedClip,clip_id,user)
    account=owned(db,ConnectedAccount,body.account_id,user)
    if body.version is not None and body.version!=clip.current_version:
        raise HTTPException(409,'Draft version changed after the publishing preview. Review and approve the current version.')
    if not body.explicit_authorization:
        raise HTTPException(422,'Explicit approval is required for each publishing job.')
    if account.platform!='youtube' or account.status!='connected':
        raise HTTPException(422,'Use a connected YouTube account, or download the manual publishing package.')
    if clip.compliance.get('status')!='PASS':
        raise HTTPException(409,'Resolve all blocking compliance checks before publishing.')
    from .social import require_approved_draft
    require_approved_draft(db,clip)
    if db.scalar(select(DraftEvaluation.id).where(DraftEvaluation.clip_id==clip.id)) and body.made_for_kids is None:
        raise HTTPException(422,'Select the required YouTube audience setting before publishing.')
    if db.scalar(select(DraftEvaluation.id).where(DraftEvaluation.clip_id==clip.id)) and body.version is None:
        raise HTTPException(422,'Confirm the exact approved draft version before publishing.')
    campaign=db.get(Campaign,clip.campaign_id)
    plan=db.get(EditingPlan,clip.editing_plan_id)
    from .services.campaign_requirements import deadline_state
    if deadline_state(campaign.rules.get('submission_deadline'))=='expired':
        raise HTTPException(409,'Campaign deadline has expired.')
    if campaign.rules!=plan.rules_snapshot:
        raise HTTPException(409,'Campaign rules changed after this clip was generated. Generate and review a clip against the current requirements.')
    if account.platform not in campaign.rules.get('allowed_platforms',[]):
        raise HTTPException(409,'This platform is not permitted by the campaign rules.')
    if campaign.rules.get('draft_approval_required') and not clip.draft_approved:
        raise HTTPException(409,'Confirm campaign draft approval before publishing.')
    if submission_minutes(campaign.rules) and (not body.attended or body.scheduled_at):
        raise HTTPException(409,'This campaign requires immediate attended publishing to complete manual submission on time.')
    schedule=body.scheduled_at
    if schedule:
        if schedule.tzinfo is None:
            raise HTTPException(422,'Scheduled time must include a timezone.')
        schedule=schedule.astimezone(timezone.utc).replace(tzinfo=None)
        if schedule<=now():
            raise HTTPException(422,'Choose a future scheduled time.')
    existing=db.scalar(select(PublishingJob).where(PublishingJob.clip_id==clip.id,PublishingJob.platform=='youtube',PublishingJob.version==clip.current_version))
    if existing:return obj(existing,'upload_state')
    job=PublishingJob(user_id=user.id,clip_id=clip.id,account_id=account.id,platform='youtube',version=clip.current_version,authorized=True,attended=body.attended,privacy=body.privacy,scheduled_at=schedule,upload_state={'made_for_kids':body.made_for_kids or False},authorization_expires_at=now()+timedelta(minutes=5) if submission_minutes(campaign.rules) else None)
    db.add(job)
    db.flush()
    audit(db,user.id,'publishing.authorized',job.id,privacy=body.privacy,clip_version=clip.current_version,scheduled_at=public_time(schedule))
    db.commit()
    return obj(job,'upload_state')

@app.get('/api/publishing')
def publishing_queue(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(p,'upload_state') for p in db.scalars(select(PublishingJob).where(PublishingJob.user_id==user.id).order_by(PublishingJob.created_at.desc()))]

@app.post('/api/publishing/{job_id}/retry')
def retry_publish(job_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    job=owned(db,PublishingJob,job_id,user)
    if job.status not in {'failed','uploading','needs_authorization'} or job.attempts>=3:
        raise HTTPException(409,'This publishing job cannot be retried. Review the channel and existing post.')
    if job.status=='uploading' and (job.upload_lease_until is None or job.upload_lease_until>now()):
        raise HTTPException(409,'The upload may still be running. Wait for its result.')
    result=db.execute(update(PublishingJob).where(PublishingJob.id==job.id,or_(PublishingJob.status.in_(['failed','needs_authorization']),and_(PublishingJob.status=='uploading',PublishingJob.upload_lease_until<=now()))).values(status='queued',error=None,authorization_expires_at=now()+timedelta(minutes=5)))
    if not result.rowcount:
        raise HTTPException(409,'This upload is active in another worker.')
    db.refresh(job)
    audit(db,user.id,'publishing.retried',job.id)
    db.commit()
    return obj(job,'upload_state')

class ManualPostRequest(BaseModel):
    platform: Literal['youtube','tiktok','instagram']
    url: str = Field(max_length=2048)
    published_at: datetime
    confirmation: str = Field(min_length=8,max_length=4000)

@app.post('/api/clips/{clip_id}/record-publication')
def record_publication(clip_id: str,body: ManualPostRequest,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    clip=owned(db,RenderedClip,clip_id,user)
    validate_post_url(body.platform,body.url)
    if body.published_at.tzinfo is None:
        raise HTTPException(422,'Publication timestamp must include a timezone.')
    published=body.published_at.astimezone(timezone.utc).replace(tzinfo=None)
    if published>now()+timedelta(minutes=1):
        raise HTTPException(422,'Record the actual publication time; it cannot be in the future.')
    campaign=db.get(Campaign,clip.campaign_id)
    # Recording an already public post is distinct from authorizing publication.
    # Preserve evidence even if someone published outside this app with a review pending.
    post=PublishedPost(user_id=user.id,clip_id=clip.id,campaign_id=campaign.id,platform=body.platform,url=body.url,published_at=published,provenance='manual_confirmation')
    db.add(post)
    db.flush()
    submission=create_submission(db,post,campaign)
    audit(db,user.id,'post.manually_recorded',post.id,confirmation=body.confirmation,compliance_at_recording=clip.compliance.get('status'))
    db.commit()
    return {**obj(post),'submission':{**obj(submission),**countdown(submission)}}

@app.get('/api/submissions')
def submissions(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    rows=db.execute(select(CampaignSubmission,PublishedPost,Campaign).join(PublishedPost,CampaignSubmission.post_id==PublishedPost.id).join(Campaign,CampaignSubmission.campaign_id==Campaign.id).where(CampaignSubmission.user_id==user.id).order_by(CampaignSubmission.created_at.desc())).all()
    return [{**obj(s),'post_url':p.url,'published_at':public_time(p.published_at),'platform':p.platform,'campaign_name':c.name,'submission_instructions':c.rules.get('submission_instructions'),**countdown(s)} for s,p,c in rows]

class SubmissionUpdate(BaseModel):
    status: Literal['submitted','approved','rejected']
    confirmation: str = Field(min_length=8,max_length=4000)

@app.post('/api/submissions/{submission_id}/confirm')
def confirm_submission(submission_id: str,body: SubmissionUpdate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    submission=owned(db,CampaignSubmission,submission_id,user)
    submission.status=body.status
    submission.confirmed_at=now()
    submission.confirmation=body.confirmation
    audit(db,user.id,'submission.manually_confirmed',submission.id,status=body.status,evidence=body.confirmation)
    db.commit()
    return {**obj(submission),**countdown(submission)}

def metrics(db,user):
    def count(cls,*conditions):
        return db.scalar(select(func.count()).select_from(cls).where(cls.user_id==user.id,*conditions)) or 0
    def amount(kind):
        return db.scalar(select(func.coalesce(func.sum(EarningsRecord.amount),0)).where(EarningsRecord.user_id==user.id,EarningsRecord.currency=='USD',EarningsRecord.kind==kind)) or 0
    posts=list(db.scalars(select(PublishedPost).where(PublishedPost.user_id==user.id)))
    total_views=0
    for post in posts:
        latest=db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.post_id==post.id).order_by(AnalyticsSnapshot.created_at.desc()).limit(1))
        if latest:
            total_views+=latest.reported_views
    approved=db.scalar(select(func.count()).select_from(RenderedClip).where(RenderedClip.user_id==user.id,RenderedClip.status=='approved')) or 0
    return {'projects':count(FactoryProject),'videos_imported':count(SourceVideo),
        'videos_analyzed':db.scalar(select(func.count(func.distinct(ProcessingJob.source_id))).where(ProcessingJob.user_id==user.id,ProcessingJob.status=='completed')) or 0,
        'approved_drafts':approved,'failed_jobs':count(ProcessingJob,ProcessingJob.status.in_(['failed','blocked'])),
        'active_campaigns':count(Campaign,Campaign.status.in_(['active','review'])),'clips_generated':count(RenderedClip),'processing_jobs':count(ProcessingJob,ProcessingJob.status.in_(['queued','processing'])),
        'ready_to_publish':count(RenderedClip,RenderedClip.status=='ready'),'scheduled':count(PublishingJob,PublishingJob.status=='queued',PublishingJob.scheduled_at.is_not(None)),
        'published':count(PublishedPost),'pending_submissions':count(CampaignSubmission,CampaignSubmission.status.in_(['pending','submitted'])),'approved_submissions':count(CampaignSubmission,CampaignSubmission.status=='approved'),
        'rejected_submissions':count(CampaignSubmission,CampaignSubmission.status=='rejected'),'reported_views':total_views,'estimated_earnings':amount('estimated'),'confirmed_earnings':amount('confirmed'),'paid_earnings':amount('paid'),
        'processing_expenses':db.scalar(select(func.coalesce(func.sum(ProcessingCost.amount),0)).where(ProcessingCost.user_id==user.id,ProcessingCost.kind=='reported')) or 0,'currency':'USD',
        'earnings_provenance':'Imported or manually confirmed records; no inferred platform payouts.'}

@app.get('/api/dashboard')
def dashboard(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    from .performance import dashboard_data
    end=datetime.now(timezone.utc).date();start=end-timedelta(days=29)
    performance={p:dashboard_data(db,user,start,end,p) for p in ('youtube','tiktok')}
    return {'metrics':metrics(db,user),'recent_jobs':jobs(user,db)[:5],'campaigns':campaigns(user,db)[:5],'clips':clips(user,db)[:6],'configuration':configuration(),
        'platform_performance':{p:{'lifetime_views':v['lifetime_views'],'period_views':v['period_views'],'range':v['range'],'best_performing':v['best_performing']} for p,v in performance.items()}}

@app.get('/api/analytics')
def analytics(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    posts=list(db.scalars(select(PublishedPost).where(PublishedPost.user_id==user.id).order_by(PublishedPost.published_at.desc())))
    rows=[]
    for post in posts:
        snapshot=db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.post_id==post.id).order_by(AnalyticsSnapshot.created_at.desc()).limit(1))
        rows.append({**obj(post),'analytics':obj(snapshot) if snapshot else None})
    return {'metrics':metrics(db,user),'posts':rows,'earnings':[obj(e) for e in db.scalars(select(EarningsRecord).where(EarningsRecord.user_id==user.id).order_by(EarningsRecord.created_at.desc()))],
        'processing_costs':[obj(c) for c in db.scalars(select(ProcessingCost).where(ProcessingCost.user_id==user.id))],
        'note':'Reported views are not automatically eligible views. USD summary excludes other currencies. Estimated, confirmed and paid records are separate ledger categories.'}

class AnalyticsImport(BaseModel):
    reported_views: int = Field(ge=0)
    eligible_views: int | None = Field(default=None,ge=0)
    likes: int | None = Field(default=None,ge=0)
    shares: int | None = Field(default=None,ge=0)
    provenance: str = Field(min_length=8,max_length=100)

@app.post('/api/posts/{post_id}/analytics')
def import_analytics(post_id: str,body: AnalyticsImport,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    post=owned(db,PublishedPost,post_id,user)
    if body.eligible_views is not None and body.eligible_views>body.reported_views:
        raise HTTPException(422,'Eligible views cannot exceed reported views.')
    snapshot=AnalyticsSnapshot(post_id=post.id,**body.model_dump())
    db.add(snapshot)
    audit(db,user.id,'analytics.imported',post.id,provenance=body.provenance)
    db.commit()
    return obj(snapshot)

class EarningsImport(BaseModel):
    campaign_id: str
    amount: float = Field(ge=0,le=100000000,allow_inf_nan=False)
    currency: str = Field(default='USD',pattern='^[A-Z]{3}$')
    kind: Literal['estimated','confirmed','paid']
    provenance: str = Field(min_length=8,max_length=4000)

@app.post('/api/earnings')
def import_earnings(body: EarningsImport,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    owned(db,Campaign,body.campaign_id,user)
    record=EarningsRecord(user_id=user.id,**body.model_dump())
    db.add(record)
    audit(db,user.id,'earnings.imported',record.id,kind=body.kind,provenance=body.provenance)
    db.commit()
    return obj(record)

class CostImport(BaseModel):
    job_id: str | None = None
    amount: float = Field(ge=0,le=100000,allow_inf_nan=False)
    provider: str = Field(min_length=2,max_length=100)

@app.post('/api/costs')
def import_cost(body: CostImport,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    if body.job_id:
        owned(db,ProcessingJob,body.job_id,user)
    record=ProcessingCost(user_id=user.id,kind='reported',**body.model_dump())
    db.add(record)
    audit(db,user.id,'cost.imported',record.id,provider=body.provider)
    db.commit()
    return obj(record)

@app.post('/api/analytics/import-csv')
def import_csv(file: UploadFile=File(...),user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    import csv, io
    raw=file.file.read(1024*1024+1)
    if len(raw)>1024*1024:
        raise HTTPException(413,'CSV import is limited to 1 MB.')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        rows=list(reader)
        if len(rows)>1000:
            raise ValueError('At most 1,000 CSV rows are supported.')
        prepared=[]
        for index,row in enumerate(rows):
            post=db.scalar(select(PublishedPost).where(PublishedPost.user_id==user.id,PublishedPost.url==row.get('post_url')))
            if not post:
                raise ValueError(f'Row {index+2}: post URL is not recorded in your workspace.')
            body=AnalyticsImport(reported_views=int(row['reported_views']),eligible_views=int(row['eligible_views']) if row.get('eligible_views') else None,likes=int(row['likes']) if row.get('likes') else None,shares=int(row['shares']) if row.get('shares') else None,provenance='User CSV import')
            if body.eligible_views is not None and body.eligible_views>body.reported_views:
                raise ValueError(f'Row {index+2}: eligible views exceed reported views.')
            prepared.append(AnalyticsSnapshot(post_id=post.id,**body.model_dump()))
        db.add_all(prepared)
        audit(db,user.id,'analytics.csv_imported',rows=len(prepared))
        db.commit()
    except (ValueError,KeyError,UnicodeDecodeError) as exc:
        db.rollback()
        raise HTTPException(422,str(exc)[:600])
    return {'imported':len(prepared)}

@app.get('/api/settings')
def get_settings(user: User=Depends(current_user)):
    return {**configuration(),'preferences':user.preferences}

class SettingsUpdate(BaseModel):
    monthly_spend_limit_usd: float = Field(ge=0,le=10000,allow_inf_nan=False)
    max_job_cost_usd: float = Field(gt=0,le=100,allow_inf_nan=False)

@app.patch('/api/settings')
def update_settings(body: SettingsUpdate,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    if body.monthly_spend_limit_usd>settings.monthly_limit or body.max_job_cost_usd>settings.max_job_cost:
        raise HTTPException(422,'Workspace limits can be lowered here. Raise deployment environment limits to increase them.')
    user.preferences={**user.preferences,**body.model_dump()}
    audit(db,user.id,'settings.updated',**body.model_dump())
    db.commit()
    return get_settings(user)

@app.get('/api/audit')
def audit_log(user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    return [obj(a) for a in db.scalars(select(AuditLog).where(AuditLog.user_id==user.id).order_by(AuditLog.created_at.desc()).limit(100))]


class AutoCreate(BaseModel):
    source_id: str
    campaign_id: str | None = None
    game: str = Field(default='',max_length=160)
    context: str = Field(default='',max_length=4000)
    duration: float = Field(default=20,ge=1,le=180)
    intensity: Literal['gentle','balanced','energetic'] = 'balanced'
    platform: Literal['youtube','tiktok','instagram'] = 'youtube'
    original_creator_confirmed: bool = False
    clip_count: int = Field(default=1,ge=1,le=10)
    studio: bool = False
    processing_mode: Literal['fast','balanced','quality'] = 'balanced'
    editing_profile: Literal['opus','automatic','gaming','cinematic','clean','reference'] = 'automatic'
    destination: Literal['both','youtube','tiktok'] = 'both'
    render_engine: Literal['ffmpeg','remotion'] = 'ffmpeg'
    framing: Literal['fit','crop'] = 'fit'
    output_preset: Literal['portrait_1080','portrait_720','square_1080','landscape_1080'] = 'portrait_1080'
    reference_profile: dict | None = None

@app.post('/api/auto/jobs')
def auto_create(body: AutoCreate, request: Request, user: User=Depends(current_user), db: DBSession=Depends(get_db)):
    if not free_mode() or not local_no_auth() or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'AUTO CREATE is restricted to the free loopback local application.')
    source=owned(db,SourceVideo,body.source_id,user)
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.source_id==source.id,ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'This source already has an active render.')
    from .services.ollama_provider import OllamaProvider
    OllamaProvider().require_configured(require_vision=True)
    if body.campaign_id:
        campaign=owned(db,Campaign,body.campaign_id,user)
        if not campaign.rules and campaign.brief.strip(): analyze_campaign_record(db,campaign)
    else:
        from .services.schemas import CampaignRules
        destinations=['youtube','tiktok'] if body.studio and body.destination=='both' else [body.platform]
        general=CampaignRules(campaign_name='General local creation',allowed_platforms=destinations,draft_approval_required=False,
                              evidence=[{'field':'allowed_platforms','quote':body.platform,'source':'user_selected_platform'}]).model_dump()
        campaign=Campaign(user_id=user.id,name='General local creation',brief='No external campaign supplied.',rules=general,evidence=general['evidence'],review_required=False,status='active')
        db.add(campaign);db.flush()
    rules=campaign.rules
    if rules.get('automated_clipping_allowed') is False or rules.get('ai_generated_allowed') is False:
        raise HTTPException(422,'Campaign prohibits automation; use the manual workflow.')
    if rules.get('original_footage_required') and not body.original_creator_confirmed:
        raise HTTPException(422,'Confirm required original creator footage before AUTO CREATE.')
    if body.platform in rules.get('prohibited_platforms',[]):
        raise HTTPException(422,'Campaign prohibits this platform.')
    job=ProcessingJob(user_id=user.id,campaign_id=campaign.id,source_id=source.id,mode='quality' if body.processing_mode=='quality' else 'fast',clip_count=body.clip_count,
        cost_reservation=0,rules_snapshot=rules,payload={'processing_provider':'local_ai','options':body.model_dump()})
    db.add(job);db.commit();return obj(job)

@app.post('/api/auto/jobs/{job_id}/cancel')
def cancel_auto(job_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    job=owned(db,ProcessingJob,job_id,user)
    if job.payload.get('processing_provider')!='local_ai': raise HTTPException(422,'Not an AUTO CREATE job.')
    if job.status not in {'queued','processing'}: raise HTTPException(409,'Job is already finished.')
    job.payload={**job.payload,'cancel_requested':True}
    if job.status=='queued': job.status='cancelled'
    db.commit();return obj(job)

@app.get('/api/auto/jobs/{job_id}/result')
def auto_result(job_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    job=owned(db,ProcessingJob,job_id,user)
    if job.status!='completed': raise HTTPException(409,'The final video is not ready.')
    clip=db.scalar(select(RenderedClip).where(RenderedClip.job_id==job.id,RenderedClip.user_id==user.id))
    if not clip: raise HTTPException(409,'No final video is stored.')
    result=job.payload.get('auto_result',{})
    from .publishing import selected_metadata
    return {'clip':clip_json(clip),'recommended':selected_metadata(clip.metadata_json,result.get('platform','youtube')), 'research':result.get('research',{}),
            'ending_checks':result.get('ending_checks',[]),'platform':result.get('platform','youtube')}


@app.get('/api/auto/jobs/{job_id}/package')
def auto_package(job_id: str,user: User=Depends(current_user),db: DBSession=Depends(get_db)):
    result=auto_result(job_id,user,db)
    clip=owned(db,RenderedClip,result['clip']['id'],user)
    import io
    from fastapi.responses import StreamingResponse
    buffer=io.BytesIO()
    with materialize(clip.storage_key) as path, zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as archive:
        archive.write(path,'clip.mp4')
        archive.writestr('recommended-metadata.json',json.dumps(result['recommended'],ensure_ascii=False,indent=2))
        archive.writestr('research.json',json.dumps(result['research'],ensure_ascii=False,indent=2))
        archive.writestr('compliance.json',json.dumps(clip.compliance,ensure_ascii=False,indent=2))
    buffer.seek(0)
    return StreamingResponse(buffer,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="auto-create-package.zip"'})


from .studio import router as studio_router
app.include_router(studio_router)
from .social import router as social_router
app.include_router(social_router)
from .performance import router as performance_router
app.include_router(performance_router)
