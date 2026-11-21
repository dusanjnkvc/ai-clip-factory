"""Native project/draft endpoints; existing sources, campaigns and jobs are reused."""
import os
import json,tempfile,zipfile
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path
from statistics import median
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .security import current_user
from .runtime import free_mode, local_no_auth
from .models import User, SourceVideo, Campaign, ProcessingJob, FactoryProject, ReferenceStyle, RenderedClip, EditingPlan, DraftDecision, DraftEvaluation
from .storage import materialize
from contextlib import ExitStack

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
    clip_count: int=Field(default=3,ge=1,le=10)
    duration: float=Field(default=10,ge=1,le=180,allow_inf_nan=False)
    minimum_duration: float=Field(default=6,ge=1,le=180)
    maximum_duration: float=Field(default=20,ge=1,le=180)
    game: str=Field(default='',max_length=160)
    context: str=Field(default='',max_length=4000)
    original_creator_confirmed: bool=False
    processing_mode: str=Field(default='balanced',pattern='^(fast|balanced|quality)$')
    editing_profile: str=Field(default='opus',pattern='^(opus|automatic|gaming|cinematic|clean|reference)$')
    destination: str=Field(default='both',pattern='^(both|youtube|tiktok)$')
    render_engine: str=Field(default='ffmpeg',pattern='^(ffmpeg|remotion)$')
    framing: str=Field(default='fit',pattern='^(fit|crop)$')
    output_preset: str=Field(default='portrait_1080',pattern='^(portrait_1080|portrait_720|square_1080|landscape_1080)$')

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


@router.post('/campaigns/{campaign_id}/analyze')
def analyze_rules(campaign_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    campaign=owner(db,Campaign,campaign_id,user)
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status=='processing')):
        raise HTTPException(409,'Finish or cancel current local processing before campaign inference.')
    from .services.campaign_ai import analyze_campaign
    from .services.ollama_provider import OllamaProvider
    provider=OllamaProvider();provider.keep_alive_seconds=60
    try:
        with ExitStack() as stack:
            attachments=[{**a,'path':str(stack.enter_context(materialize(a['storage_key'])))} for a in campaign.attachments]
            result=analyze_campaign(provider,campaign.brief,attachments)
    finally:
        provider.unload()
    campaign.rules=result['rules'];campaign.evidence=result['evidence'];campaign.review_required=True;campaign.status='review'
    from .models import CampaignRule
    existing=list(db.scalars(select(CampaignRule).where(CampaignRule.campaign_id==campaign.id)))
    db.add(CampaignRule(campaign_id=campaign.id,version=len(existing)+1,rules=campaign.rules,evidence=campaign.evidence))
    db.commit();return row_json(campaign)


@router.post('/projects/{project_id}/start')
def start(project_id: str,request: Request,user: User=Depends(current_user),db: Session=Depends(get_db)):
    project=owner(db,FactoryProject,project_id,user)
    if project.job_id:
        job=db.get(ProcessingJob,project.job_id)
        if job.status in {'queued','processing','completed'}:
            return row_json(job)
    from .main import AutoCreate,auto_create
    options={**project.options,'source_id':project.source_id,'campaign_id':project.campaign_id,'studio':True}
    options['platform']='tiktok' if options.get('destination')=='tiktok' else 'youtube'
    if project.reference_ids:
        options['reference_profile']=owner(db,ReferenceStyle,project.reference_ids[0],user).profile
    result=auto_create(AutoCreate.model_validate(options),request,user,db)
    job=db.get(ProcessingJob,result['id'])
    job.payload={**job.payload,'options':{**job.payload['options'],
        'minimum_duration':project.options['minimum_duration'],'maximum_duration':project.options['maximum_duration']},'project_id':project.id}
    from .performance import learning_data
    job.payload={**job.payload,'options':{**job.payload['options'],'history':learning_data(db,user)}}
    job.payload={**job.payload,'options':{**job.payload['options'],'research_examples':user.preferences.get('research_examples',[])[:20]}}
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
    active=list(db.scalars(select(ProcessingJob).where(ProcessingJob.user_id==user.id,ProcessingJob.source_id==project.source_id,ProcessingJob.status.in_(['queued','processing']))))
    return {**row_json(project),'job':row_json(job) if job else None,'drafts':clips,'active_jobs':[row_json(j) for j in active]}


@router.get('/clips')
def generated_clips(user: User=Depends(current_user),db: Session=Depends(get_db)):
    """Include legacy outputs alongside new projects without rewriting saved rows."""
    from .main import clip_json
    from .models import PublishedPost,PublishingJob
    result=[]
    for clip in db.scalars(select(RenderedClip).where(RenderedClip.user_id==user.id).order_by(RenderedClip.created_at.desc())):
        campaign=db.get(Campaign,clip.campaign_id);job=db.get(ProcessingJob,clip.job_id)
        evaluation=db.scalar(select(DraftEvaluation).where(DraftEvaluation.clip_id==clip.id,DraftEvaluation.version==clip.current_version).order_by(DraftEvaluation.created_at.desc()))
        decision=db.scalar(select(DraftDecision).where(DraftDecision.clip_id==clip.id,DraftDecision.version==clip.current_version).order_by(DraftDecision.created_at.desc()))
        options=(job.payload or {}).get('options',{}) if job else {}
        result.append({**clip_json(clip),'plan':db.get(EditingPlan,clip.editing_plan_id).plan,
            'campaign_name':campaign.name if campaign and campaign.name!='General local creation' else 'No Campaign',
            'destination':options.get('destination','both'),'evaluation':evaluation.evaluation if evaluation else None,
            'editing_style':{'opus':'Opus-Style Gaming','gaming':'Dynamic Gaming','cinematic':'Cinematic Gaming','automatic':'AI Auto'}.get(options.get('editing_profile'),''),
            'decision':decision.decision if decision else 'needs_review',
            'publications':[row_json(p) for p in db.scalars(select(PublishedPost).where(PublishedPost.clip_id==clip.id,PublishedPost.user_id==user.id))],
            'publishing_jobs':[{'id':p.id,'platform':p.platform,'status':p.status,'error':p.error,'version':p.version} for p in db.scalars(select(PublishingJob).where(PublishingJob.clip_id==clip.id,PublishingJob.user_id==user.id))]})
    return result


@router.get('/projects/{project_id}/export')
def export_approved(project_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    project=detail(project_id,user,db)
    approved=[d for d in project['drafts'] if d['decision']=='approved' and d['compliance']['status']=='PASS']
    if not approved:raise HTTPException(409,'Approve at least one compliant current draft version before exporting the approved package. Preview downloads remain available.')
    temporary=tempfile.NamedTemporaryFile(prefix='acf-approved-',suffix='.zip',delete=False);temporary.close()
    path=Path(temporary.name)
    try:
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
            for draft in approved:
                clip=db.get(RenderedClip,draft['id']);prefix=clip.id+f'/v{clip.current_version}'
                with materialize(clip.storage_key) as video:archive.write(video,prefix+'/clip.mp4')
                archive.writestr(prefix+'/metadata.json',json.dumps(draft['metadata'],ensure_ascii=False,indent=2))
                archive.writestr(prefix+'/evaluation.json',json.dumps(draft['evaluation'],ensure_ascii=False,indent=2))
                archive.writestr(prefix+'/compliance.json',json.dumps(draft['compliance'],ensure_ascii=False,indent=2))
            archive.writestr('README.txt','Only approved, compliant current draft versions are included. This local package does not publish to any platform. Editorial scores do not predict views.')
    except Exception:
        path.unlink(missing_ok=True);raise
    return FileResponse(path,filename='approved-clips.zip',media_type='application/zip',background=BackgroundTask(path.unlink,missing_ok=True))


class ReferenceInput(BaseModel):
    source_id: str
    name: str=Field(min_length=1,max_length=200)


@router.post('/sources/{source_id}/preview')
def prepare_preview(source_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    source=owner(db,SourceVideo,source_id,user)
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Finish or cancel local processing before building a preview.')
    from .storage import local_path
    from .services.source_preview import build_preview
    target=local_path(f'preview-cache/{source.sha256}-720-v1.mp4')
    with materialize(source.storage_key) as path:info=build_preview(path,target)
    return {'preview_url':f'/api/studio/sources/{source.id}/preview','media_info':info,'basis':'720-pixel local proxy of the original; no edits applied.'}


@router.get('/sources/{source_id}/preview')
def source_preview(source_id: str,user: User=Depends(current_user),db: Session=Depends(get_db)):
    source=owner(db,SourceVideo,source_id,user)
    from .storage import local_path
    path=local_path(f'preview-cache/{source.sha256}-720-v1.mp4')
    if not path.is_file():raise HTTPException(404,'Build the local original preview first.')
    return FileResponse(path,media_type='video/mp4')


@router.post('/references')
def reference(body: ReferenceInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    source=owner(db,SourceVideo,body.source_id,user)
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Finish or cancel active local processing before reference analysis.')
    from .services.reference_style import measure_reference
    from .services.ollama_provider import OllamaProvider
    provider=OllamaProvider();provider.keep_alive_seconds=60
    with materialize(source.storage_key) as path:
        try:profile=measure_reference(Path(path),source.media_info,provider if provider.status(require_vision=True).get('available') else None)
        finally:
            try:provider.unload()
            except Exception:pass
    profile['source_sha256']=source.sha256
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


class URLImportInput(BaseModel):
    url: str=Field(max_length=2000)
    rights_confirmed: bool


@router.post('/sources/import-url')
def import_video_url(body: URLImportInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    if not body.rights_confirmed:raise HTTPException(422,'Confirm permission to download and edit the video.')
    from .services.url_import import import_youtube
    from .main import upload_source,settings
    from fastapi import UploadFile
    with tempfile.TemporaryDirectory(prefix='acf-authorized-import-') as directory:
        path,title=import_youtube(body.url,directory,settings.max_upload_mb*1024*1024)
        with path.open('rb') as stream:return upload_source(UploadFile(filename=title+path.suffix,file=stream),True,'User confirms permission to download and edit this YouTube video: '+body.url,user,db)


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


class ComponentRequest(BaseModel):
    component: str=Field(pattern='^(titles|metadata|hook|captions|effects)$')
    version: int
    platform: str=Field(default='youtube',pattern='^(youtube|tiktok)$')
    field: str | None=Field(default=None,pattern='^(title|description|caption|hashtags)$')


class DraftEdit(BaseModel):
    version: int
    plan: dict | None=None
    metadata: dict | None=None
    restore_version: int | None=Field(default=None,ge=1)
    render_engine: str=Field(default='remotion',pattern='^(ffmpeg|remotion)$')

@router.get('/drafts/{clip_id}/remotion')
def remotion_preview(clip_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user)
    if not clip.media_info.get('remotion_base_key'):return None
    return {**clip.media_info['remotion_props'],'videoUrl':f'/api/studio/drafts/{clip.id}/remotion-base'}

@router.get('/drafts/{clip_id}/remotion-base')
def remotion_base(clip_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .storage import local_path
    clip=owner(db,RenderedClip,clip_id,user)
    key=clip.media_info.get('remotion_base_key')
    if not key:raise HTTPException(404,'This older clip needs a Remotion render before a live composition preview is available.')
    return FileResponse(local_path(key),media_type='video/mp4')


@router.post('/drafts/{clip_id}/edit')
def edit_draft(clip_id: str,body: DraftEdit,user: User=Depends(current_user),db: Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user)
    if clip.current_version!=body.version:raise HTTPException(409,'The clip changed. Reopen the current version before editing.')
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.user_id==user.id,ProcessingJob.source_id==clip.source_id,ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Wait for the current edit to finish before saving another change.')
    plan=body.plan;metadata=body.metadata
    if body.restore_version:
        from .models import ClipVersion
        old=db.scalar(select(ClipVersion).where(ClipVersion.clip_id==clip.id,ClipVersion.version==body.restore_version))
        if not old:raise HTTPException(404,'Saved version not found.')
        plan=old.plan;metadata=old.metadata_json
    from .main import regenerate_clip,RegenerateRequest,update_metadata,ClipMetadataUpdate
    from .services.schemas import Metadata
    if metadata is not None:
        from pydantic import ValidationError
        try:metadata=Metadata.model_validate(metadata).model_dump()
        except ValidationError as exc:raise HTTPException(422,'Invalid platform metadata.') from exc
    current=db.get(EditingPlan,clip.editing_plan_id).plan
    if plan is not None and (plan!=current or body.restore_version):
        result=regenerate_clip(clip.id,RegenerateRequest(plan=plan),user,db)
        job=db.get(ProcessingJob,result['id']);job.payload={**job.payload,'options':{**job.payload.get('options',{}),'render_engine':body.render_engine},**({'processing_provider':'local_ai'} if body.render_engine=='remotion' else {})};db.commit()
        if metadata is not None:
            job=db.get(ProcessingJob,result['id']);job.payload={**job.payload,'metadata':metadata};db.commit()
        return {'action':'render_queued','job':result}
    if metadata is not None:return {'action':'metadata_saved','clip':update_metadata(clip.id,ClipMetadataUpdate(metadata=metadata),user,db)}
    return {'action':'unchanged'}


@router.post('/drafts/{clip_id}/regenerate-component')
def regenerate_component(clip_id: str,body: ComponentRequest,user: User=Depends(current_user),db: Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user)
    if clip.current_version!=body.version:raise HTTPException(409,'Draft changed; review the current version.')
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Finish or cancel active processing before regenerating a component.')
    import copy
    plan=copy.deepcopy(db.get(EditingPlan,clip.editing_plan_id).plan)
    from .main import regenerate_clip,RegenerateRequest,update_metadata,ClipMetadataUpdate
    if body.component=='captions':
        plan['manual_captions']=[];plan['subtitles_enabled']=True
        return regenerate_clip(clip.id,RegenerateRequest(plan=plan),user,db)
    from .services.ollama_provider import OllamaProvider
    from .services.studio_metadata import rendered_context,generate_studio_package,generate_titles
    from .services.campaign_requirements import enforce_metadata
    from .services.local_hooks import generate_hooks
    from .services.viral_score import evaluate_render
    from .services.local_analysis import Contract
    provider=OllamaProvider();provider.keep_alive_seconds=60
    try:
        score=db.scalar(select(DraftEvaluation).where(DraftEvaluation.clip_id==clip.id,DraftEvaluation.version==clip.current_version).order_by(DraftEvaluation.created_at.desc()))
        evaluation=score.evaluation if score else None
        original_job=db.get(ProcessingJob,clip.job_id);options=original_job.payload.get('options',{})
        rules=db.get(EditingPlan,clip.editing_plan_id).rules_snapshot
        context=rendered_context(plan,evaluation,options.get('game') or rules.get('game_name'))
        if context is None:
            source=owner(db,SourceVideo,clip.source_id,user)
            render_info={**clip.media_info,'source_aspect_ratio':source.media_info['width']/source.media_info['height']}
            with materialize(clip.storage_key) as path:evaluation=evaluate_render(path,plan,clip.metadata_json,provider,render_info=render_info)
            context=rendered_context(plan,evaluation,options.get('game') or rules.get('game_name'))
            db.add(DraftEvaluation(clip_id=clip.id,version=clip.current_version,artifact_sha256=evaluation['visual']['artifact_sha256'],evaluation=evaluation));db.commit()
        metadata=copy.deepcopy(clip.metadata_json)
        if body.component=='titles':
            titles=generate_titles(provider,plan,context,rules)
            block=metadata['youtube'];block['title_candidates']=titles;block['generation_status']='generated'
            index=block['recommended_index'];block['variants'][index]=enforce_metadata({**block['variants'][index],'title':titles[0]['title']},rules)
            return update_metadata(clip.id,ClipMetadataUpdate(metadata=metadata),user,db)
        if body.component=='metadata':
            research=original_job.payload.get('auto_result',{}).get('research',{'status':'unavailable'})
            generated=generate_studio_package(provider,plan,context,rules,research)['metadata']
            if body.field:
                target=metadata[body.platform];source=generated[body.platform]
                for index,variant in enumerate(target['variants']):variant[body.field]=source['variants'][index][body.field]
                target['generation_status']='generated'
                if body.field=='title' and 'title_candidates' in source:target['title_candidates']=source['title_candidates']
            else:
                metadata=generated
                for block in metadata.values():
                    block['generation_status']='generated'
                    for variant in block['variants']:variant['opening_hook']=plan['hook']
            return update_metadata(clip.id,ClipMetadataUpdate(metadata=metadata),user,db)
        if body.component=='hook':
            hooks=generate_hooks(provider,plan,context);plan['hook']=hooks['selected']
            for block in metadata.values():
                for variant in block['variants']:variant['opening_hook']=plan['hook']
        else:
            from typing import Literal
            class StyleChoice(Contract):
                style: Literal['clean','gaming','cinematic']
                reason: str=Field(max_length=150)
            choice=provider.structured(StyleChoice,'Choose restrained clean, gaming or cinematic editing for only these actual rendered observations. Do not invent action, outcomes or assets.',json.dumps(context))
            for scene in plan['scenes']:
                scene['effect']='contrast' if choice.style=='gaming' else 'none'
                scene['transition']='fade' if choice.style=='cinematic' else 'cut'
                scene['effect_intensity']=.4;scene['shake']=0
            plan['edit_dna']['visual_effects']=choice.style+': '+choice.reason
        queued=regenerate_clip(clip.id,RegenerateRequest(plan=plan),user,db)
        job=db.get(ProcessingJob,queued['id']);job.payload={**job.payload,'metadata':metadata};db.commit()
        return queued
    finally:
        try:provider.unload()
        except Exception:pass


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


def cache_files():
    from .main import settings
    root=settings.media_root.resolve()
    result=[]
    for name in ('analysis-cache','preview-cache'):
        directory=(root/name).resolve()
        if directory.parent!=root:raise HTTPException(409,'Cache directory resolves outside the local media root.')
        if directory.is_dir():
            result.extend(p for p in directory.iterdir() if p.is_file() and not p.is_symlink() and p.suffix in {'.json','.jpg','.tmp','.mp4'})
    return result


@router.get('/cache')
def cache_status(user: User=Depends(current_user)):
    files=cache_files()
    return {'files':len(files),'bytes':sum(p.stat().st_size for p in files),'scope':'Rebuildable analysis and preview cache only; originals, versions, models, approvals and analytics are preserved.'}


@router.delete('/cache')
def clear_cache(user: User=Depends(current_user),db: Session=Depends(get_db)):
    if db.scalar(select(ProcessingJob.id).where(ProcessingJob.status.in_(['queued','processing']))):
        raise HTTPException(409,'Wait for processing or cancel active jobs before cleaning caches.')
    files=cache_files()
    for path in files:path.unlink()
    return {'removed_files':len(files),'originals_preserved':True}


class ResearchExample(BaseModel):
    platform: str=Field(pattern='^(youtube|tiktok)$')
    url: str=Field(max_length=2000)
    title: str=Field(min_length=1,max_length=250)
    description: str=Field(default='',max_length=1500)
    published_at: datetime | None=None
    views: int | None=Field(default=None,ge=0)
    likes: int | None=Field(default=None,ge=0)
    provenance: str=Field(min_length=8,max_length=200)

    @model_validator(mode='after')
    def permitted_url(self):
        uri=urlparse(self.url);host=uri.hostname or ''
        allowed=host in {'youtube.com','www.youtube.com','youtu.be'} if self.platform=='youtube' else host=='tiktok.com' or host.endswith('.tiktok.com')
        if uri.scheme!='https' or not allowed or uri.username or uri.password:
            raise ValueError('Supply a canonical HTTPS YouTube/TikTok example link without credentials.')
        if self.published_at and self.published_at.tzinfo is None:raise ValueError('Publication dates need a timezone.')
        return self


@router.post('/research/examples')
def add_example(body: ResearchExample,user: User=Depends(current_user),db: Session=Depends(get_db)):
    examples=user.preferences.get('research_examples',[])
    if len(examples)>=100:raise HTTPException(422,'Keep at most100 supplied research examples.')
    item={**body.model_dump(mode='json'),'captured_at':datetime.now().astimezone().isoformat(),'verification':'user_supplied_unverified'}
    user.preferences={**user.preferences,'research_examples':[*examples,item]};db.commit();return item


@router.get('/research')
def research(subject: str='',user: User=Depends(current_user)):
    from .services.trends import TrendResearch
    return {'youtube':TrendResearch().research(subject[:160] or 'gaming'),'supplied_examples':user.preferences.get('research_examples',[]),
        'tiktok_limitation':'Broad TikTok viral discovery is not available through this integration. Supply authorized examples/metadata, or synchronize your authorized account metrics. No scraping or invented trend counts.'}


class ResearchImport(BaseModel):
    examples: list[ResearchExample]=Field(max_length=100)


@router.post('/research/import')
def import_examples(body: ResearchImport,user: User=Depends(current_user),db: Session=Depends(get_db)):
    existing=user.preferences.get('research_examples',[])
    if len(existing)+len(body.examples)>100:raise HTTPException(422,'Keep at most100 supplied research examples.')
    items=[{**item.model_dump(mode='json'),'captured_at':datetime.now().astimezone().isoformat(),'verification':'user_supplied_unverified'} for item in body.examples]
    user.preferences={**user.preferences,'research_examples':[*existing,*items]};db.commit();return {'imported':len(items)}
