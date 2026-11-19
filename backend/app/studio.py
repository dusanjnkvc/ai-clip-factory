"""Native project/draft endpoints; existing sources, campaigns and jobs are reused."""
import os
from pathlib import Path
from statistics import median
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .security import current_user
from .runtime import free_mode, local_no_auth
from .models import User, SourceVideo, Campaign, ProcessingJob, FactoryProject, ReferenceStyle, RenderedClip, EditingPlan, DraftDecision, DraftEvaluation
from .storage import materialize

def require_local(request: Request):
    if not free_mode() or not local_no_auth() or request.client.host not in {'127.0.0.1','::1','testclient'}:
        raise HTTPException(403,'Studio is restricted to the free loopback local workspace.')


router=APIRouter(prefix='/api/studio', tags=['Local studio'], dependencies=[Depends(require_local)])


def owner(db, model, key, user):
    row=db.get(model,key)
    if row is None or getattr(row,'user_id',None)!=user.id:
        raise HTTPException(404,'Record not found.')
    return row


def row_json(row):
    from .main import obj
    return obj(row)


class ProjectInput(BaseModel):
    name: str=Field(min_length=1,max_length=200)
    source_id: str
    campaign_id: str | None=None
    reference_ids: list[str]=Field(default_factory=list,max_length=3)
    clip_count: int=Field(default=3,ge=1,le=3)
    duration: float=Field(default=10,ge=1,le=180,allow_inf_nan=False)
    minimum_duration: float=Field(default=6,ge=1,le=180)
    maximum_duration: float=Field(default=20,ge=1,le=180)
    game: str=Field(default='',max_length=160)
    context: str=Field(default='',max_length=4000)
    original_creator_confirmed: bool=False
    processing_mode: str=Field(default='balanced',pattern='^(fast|balanced|quality)$')
    editing_profile: str=Field(default='automatic',pattern='^(automatic|gaming|cinematic|clean|reference)$')
    framing: str=Field(default='fit',pattern='^(fit|crop)$')

    @model_validator(mode='after')
    def duration_bounds(self):
        if self.minimum_duration>self.maximum_duration:
            raise ValueError('Minimum duration exceeds maximum.')
        return self


@router.get('/projects')
def projects(user: User=Depends(current_user),db: Session=Depends(get_db)):
    result=[]
    for project in db.scalars(select(FactoryProject).where(FactoryProject.user_id==user.id).order_by(FactoryProject.created_at.desc())):
        job=db.get(ProcessingJob,project.job_id) if project.job_id else None
        result.append({**row_json(project),'job':row_json(job) if job else None})
    return result


@router.post('/projects')
def create_project(body: ProjectInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    owner(db,SourceVideo,body.source_id,user)
    if body.campaign_id: owner(db,Campaign,body.campaign_id,user)
    for key in body.reference_ids: owner(db,ReferenceStyle,key,user)
    if body.editing_profile=='reference' and not body.reference_ids:
        raise HTTPException(422,'Choose a measured reference profile for Match Reference Style.')
    project=FactoryProject(user_id=user.id,name=body.name,source_id=body.source_id,campaign_id=body.campaign_id,
        options=body.model_dump(exclude={'name','source_id','campaign_id','reference_ids'}),reference_ids=body.reference_ids)
    db.add(project);db.commit()
    return row_json(project)


@router.post('/projects/{project_id}/start')
def start(project_id: str,request: Request,user: User=Depends(current_user),db: Session=Depends(get_db)):
    project=owner(db,FactoryProject,project_id,user)
    if project.job_id:
        job=db.get(ProcessingJob,project.job_id)
        if job.status in {'queued','processing','completed'}:
            return row_json(job)
    from .main import AutoCreate,auto_create
    options={**project.options,'source_id':project.source_id,'campaign_id':project.campaign_id,'studio':True}
    if project.reference_ids:
        options['reference_profile']=owner(db,ReferenceStyle,project.reference_ids[0],user).profile
    result=auto_create(AutoCreate.model_validate(options),request,user,db)
    job=db.get(ProcessingJob,result['id'])
    job.payload={**job.payload,'options':{**job.payload['options'],
        'minimum_duration':project.options['minimum_duration'],'maximum_duration':project.options['maximum_duration']},'project_id':project.id}
    project.job_id=job.id
    project.campaign_id=job.campaign_id
    db.commit()
    return row_json(job)


@router.get('/projects/{project_id}')
def detail(project_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    project=owner(db,FactoryProject,project_id,user)
    from .main import clip_json
    clips=[]
    for clip in db.scalars(select(RenderedClip).where(RenderedClip.job_id==project.job_id,RenderedClip.user_id==user.id)) if project.job_id else []:
        evaluation=db.scalar(select(DraftEvaluation).where(DraftEvaluation.clip_id==clip.id,DraftEvaluation.version==clip.current_version).order_by(DraftEvaluation.created_at.desc()))
        decision=db.scalar(select(DraftDecision).where(DraftDecision.clip_id==clip.id,DraftDecision.version==clip.current_version).order_by(DraftDecision.created_at.desc()))
        clips.append({**clip_json(clip),'plan':db.get(EditingPlan,clip.editing_plan_id).plan,
            'evaluation':evaluation.evaluation if evaluation else None,'decision':decision.decision if decision else 'needs_review'})
    job=db.get(ProcessingJob,project.job_id) if project.job_id else None
    return {**row_json(project),'job':row_json(job) if job else None,'drafts':clips}


class ReferenceInput(BaseModel):
    source_id: str
    name: str=Field(min_length=1,max_length=200)


@router.post('/references')
def reference(body: ReferenceInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    source=owner(db,SourceVideo,body.source_id,user)
    from .services.local_analysis import detect_scenes,sample_frames,sampling_times
    with materialize(source.storage_key) as path:
        duration=source.media_info['duration']
        cuts=detect_scenes(Path(path),duration)
        frames,_=sample_frames(Path(path),sampling_times(duration,cuts,6),duration)
    lengths=[c['end']-c['start'] for c in cuts]
    profile={'source_sha256':source.sha256,'cut_count':len(cuts),'median_shot_seconds':median(lengths) if lengths else duration,
        'frame_samples':frames,'gentle_transitions':median(lengths)>4 if lengths else True,
        'unavailable':['Semantic caption font/effect/zoom/sound-event recognition','Continuous subject tracking'],
        'method':'actual_source_scene_and_sampled_pixel_measurements','rights':'Reference audiovisual content is not inserted into exports.'}
    row=ReferenceStyle(user_id=user.id,source_id=source.id,name=body.name,profile=profile)
    db.add(row);db.commit();return row_json(row)


@router.get('/references')
def references(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return [row_json(r) for r in db.scalars(select(ReferenceStyle).where(ReferenceStyle.user_id==user.id))]


@router.get('/input-directory')
def input_directory(user: User=Depends(current_user)):
    path=Path(user.preferences.get('input_directory') or os.getenv('SOURCE_VIDEO_DIR',r'C:\Users\duled\Documents\AI Clip Factory Videos to be edited')).resolve()
    files=[{'filename':p.name,'size_bytes':p.stat().st_size} for p in path.iterdir() if p.is_file() and p.suffix.lower() in {'.mp4','.mov','.mkv','.webm','.m4v'}] if path.is_dir() else []
    return {'path':str(path),'exists':path.is_dir(),'files':files}


class DirectoryUpdate(BaseModel):
    path: str=Field(max_length=1000)


@router.patch('/input-directory')
def directory_update(body: DirectoryUpdate,user: User=Depends(current_user),db: Session=Depends(get_db)):
    path=Path(body.path).resolve()
    if not path.is_dir(): raise HTTPException(422,'Choose an existing local directory.')
    user.preferences={**user.preferences,'input_directory':str(path)};db.commit()
    return input_directory(user)


class ImportInput(BaseModel):
    filename: str=Field(max_length=300)
    rights_note: str=Field(min_length=8,max_length=4000)
    rights_confirmed: bool


@router.post('/input-directory/import')
def import_local(body: ImportInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    from .main import upload_source
    from fastapi import UploadFile
    directory=Path(input_directory(user)['path'])
    path=(directory/body.filename).resolve()
    if path.parent!=directory or not path.is_file(): raise HTTPException(422,'Select a file directly inside the configured input directory.')
    with path.open('rb') as stream:
        return upload_source(UploadFile(filename=path.name,file=stream),body.rights_confirmed,body.rights_note,user,db)


class DecisionInput(BaseModel):
    decision: str=Field(pattern='^(approved|rejected)$')
    note: str=Field(min_length=8,max_length=4000)
    version: int


@router.post('/drafts/{clip_id}/decision')
def decide(clip_id: str,body: DecisionInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user)
    if clip.current_version!=body.version: raise HTTPException(409,'The draft changed; review the current version.')
    if body.decision=='approved' and clip.compliance.get('status')!='PASS':
        raise HTTPException(409,'Resolve non-compliant or ambiguous campaign checks before approving.')
    db.add(DraftDecision(user_id=user.id,clip_id=clip.id,version=clip.current_version,decision=body.decision,note=body.note))
    clip.status=body.decision;db.commit();return row_json(clip)


@router.post('/drafts/{clip_id}/auto-improve')
def improve(clip_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user)
    score=db.scalar(select(DraftEvaluation).where(DraftEvaluation.clip_id==clip.id,DraftEvaluation.version==clip.current_version).order_by(DraftEvaluation.created_at.desc()))
    if not score or not score.evaluation.get('suggestions'):
        raise HTTPException(409,'No supported automatic improvement is backed by this draft evaluation.')
    import copy
    plan=copy.deepcopy(db.get(EditingPlan,clip.editing_plan_id).plan)
    for suggestion in score.evaluation['suggestions']:
        if suggestion['action']=='fit_gameplay': plan['framing']='fit'
        elif suggestion['action']=='clean_captions': plan['subtitle_style']='clean'
        elif suggestion['action']=='shorten_hook': plan['hook']=plan['hook'][:65].rsplit(' ',1)[0]
    from .main import regenerate_clip,RegenerateRequest
    return regenerate_clip(clip.id,RegenerateRequest(plan=plan),user,db)


@router.get('/projects/{project_id}/advisor')
def advisor(project_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    project=detail(project_id,user,db)
    result={}
    for platform in ('youtube','tiktok'):
        ranked=[]
        for draft in project['drafts']:
            evaluation=draft.get('evaluation') or {}
            score=evaluation.get('platforms',{}).get(platform)
            if score:
                ranked.append({'clip_id':draft['id'],'title':draft['title'],'score':score['score'],
                    'confidence':score['confidence'],'compliance':draft['compliance']['status'],
                    'eligible':draft['compliance']['status']=='PASS','approved':draft['decision']=='approved',
                    'components':score['components'],'suggestions':evaluation.get('suggestions',[])})
        ranked.sort(key=lambda r:(r['eligible'],r['score']),reverse=True)
        result[platform]={'order':ranked,'recommended_clip_id':next((r['clip_id'] for r in ranked if r['eligible']),None),
            'posting_time':'Insufficient historical data for a reliable publishing-time recommendation.'}
    return result
