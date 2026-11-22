"""Non-destructive editor drafts, reusable designs and owned library assets.

Uses existing preference JSON and media storage; no destructive schema rewrite.
"""
import json,tempfile,uuid,wave
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .security import current_user
from .models import User,RenderedClip,EditingPlan,ClipVersion,SourceVideo
from .studio import require_local,owner
from .storage import local_path,put_file,materialize
from .services.schemas import ClipPlan,Metadata
from .services.editor_schema import EditorState
from .models import Transcript as SavedTranscript

router=APIRouter(prefix='/api/editor',tags=['Shared editor'],dependencies=[Depends(require_local)])

class PreviewInput(BaseModel):plan:dict

@router.post('/drafts/{clip_id}/preview')
def build_edit_preview(clip_id:str,body:PreviewInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .services.local import LocalPipelineService
    from .storage import materialize
    from .services.media import timeline_cues,timeline_words
    from .storage import materialize
    import hashlib,copy
    clip=owner(db,RenderedClip,clip_id,user);source=owner(db,SourceVideo,clip.source_id,user)
    try:plan=ClipPlan.model_validate(body.plan)
    except ValidationError as exc:raise HTTPException(422,'Invalid preview timeline.') from exc
    if plan.end>source.media_info['duration']+.01:raise HTTPException(422,'Preview exceeds the original source.')
    check_assets(user,plan.model_dump());clean=plan.model_dump();clean.update(show_hook=False,subtitles_enabled=False,text_overlays=[],required_on_video_text=[],editor=None)
    digest=hashlib.sha256(json.dumps(clean,sort_keys=True).encode()).hexdigest()[:24];key=f'{user.id}/editor-proxies/{clip.id}-{digest}.mp4';path=local_path(key);path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with materialize(source.storage_key) as original:LocalPipelineService().render_clip(original,clean,{'text':'','words':[],'segments':[]},path)
    speech=db.scalar(select(SavedTranscript).where(SavedTranscript.source_id==source.id));transcript=speech.content if speech else {'words':[],'segments':[]}
    from .services.schemas import Transcript
    t=Transcript.model_validate(transcript)
    cues=[v.model_dump() for v in plan.manual_captions] if plan.manual_captions else timeline_words(plan,t) if t.words else timeline_cues(plan,t)
    if not plan.subtitles_enabled:cues=[]
    from .services.media import probe_media
    info=probe_media(path)
    return {'videoUrl':f'/api/editor/drafts/{clip.id}/preview-content/{digest}','duration':round(info['duration']*plan.output_fps),'fps':plan.output_fps,'width':info['width'],'height':info['height'],'hook':plan.hook,'showHook':plan.show_hook,'requiredText':plan.required_on_video_text,'captions':[{'text':c.get('text',' '+c.get('word','')),'startMs':c['start']*1000,'endMs':c['end']*1000,'timestampMs':None,'confidence':None} for c in cues],'overlays':[v.model_dump() for v in plan.text_overlays],'captionColor':plan.caption_color,'captionSize':plan.caption_size or 64,'safeTop':200,'safeBottom':plan.caption_margin,'editor':plan.editor.model_dump() if plan.editor else None}

@router.get('/drafts/{clip_id}/preview-content/{digest}')
def edit_preview_content(clip_id:str,digest:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    import re
    clip=owner(db,RenderedClip,clip_id,user)
    if not re.fullmatch('[0-9a-f]{24}',digest):raise HTTPException(404,'Preview not found.')
    path=local_path(f'{user.id}/editor-proxies/{clip.id}-{digest}.mp4')
    if not path.is_file():raise HTTPException(404,'Build this edit preview first.')
    return FileResponse(path,media_type='video/mp4')

def assets(user):return user.preferences.get('editor_assets',[])
def asset(user,key):
    result=next((a for a in assets(user) if a['id']==key),None)
    if result is None:raise HTTPException(404,'Library asset not found.')
    return result
def public_asset(a):return {k:v for k,v in a.items() if k!='storage_key'}|{'url':f"/api/editor/assets/{a['id']}/content"}
def check_assets(user,plan):
    paths={}
    for layer in (plan or {}).get('editor',{}).get('layers',[]) if (plan or {}).get('editor') else []:
        if layer['kind']=='text':continue
        a=asset(user,layer['asset_id'])
        if a['kind']!=layer['kind']:raise HTTPException(422,'Layer and library asset types differ.')
        if a.get('duration') is not None and layer['trim_start']+layer['end']-layer['start']>a['duration']+.05:raise HTTPException(422,'A timed media layer extends beyond its asset.')
        paths[a['id']]={'path':str(local_path(a['storage_key'])),'mime':a['mime']}
    return paths

@router.get('/assets')
def list_assets(user:User=Depends(current_user)):return [public_asset(a) for a in assets(user) if not a.get('archived')]

@router.post('/assets')
def upload_asset(file:UploadFile=File(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    from .main import save_upload
    from .services.media import run_media,ffmpeg_binary
    if len(assets(user))>=200:raise HTTPException(422,'The library supports up to 200 imported assets.')
    suffix=Path(file.filename or '').suffix.lower();key=str(uuid.uuid4())
    with tempfile.TemporaryDirectory(prefix='acf-editor-asset-') as temp:
        original=Path(temp)/('input'+suffix);save_upload(file,original,50*1024*1024)
        if suffix in {'.png','.jpg','.jpeg','.webp'}:
            from PIL import Image,ImageOps,UnidentifiedImageError
            Image.MAX_IMAGE_PIXELS=16_000_000
            try:
                with Image.open(original) as image:
                    if image.width*image.height>16_000_000:raise ValueError('Image dimensions are too large.')
                    image=ImageOps.exif_transpose(image).convert('RGBA');image.thumbnail((2048,2048))
                    output=Path(temp)/'asset.png';image.save(output,'PNG',optimize=True)
                    info={'width':image.width,'height':image.height}
            except (ValueError,UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:raise HTTPException(422,'Use a valid PNG/JPEG/WebP image with at most 16 million pixels.') from exc
            kind='image';mime='image/png';extension='.png'
        elif suffix in {'.mp3','.wav','.ogg','.flac','.m4a'}:
            with original.open('rb') as stream:header=stream.read(16)
            demux='wav' if header.startswith(b'RIFF') and header[8:12]==b'WAVE' else 'ogg' if header.startswith(b'OggS') else 'flac' if header.startswith(b'fLaC') else 'mov' if header[4:8]==b'ftyp' else 'mp3' if header.startswith(b'ID3') or header[:1]==b'\xff' else None
            if not demux:raise HTTPException(422,'Unsupported audio container; playlists and remote references are rejected.')
            output=Path(temp)/'asset.wav'
            run_media([ffmpeg_binary(),'-v','error','-protocol_whitelist','file,pipe','-f',demux,'-i',str(original),'-t','301','-vn','-ar','48000','-ac','2','-c:a','pcm_s16le',str(output)],timeout=120)
            with wave.open(str(output),'rb') as audio:duration=audio.getnframes()/audio.getframerate()
            if duration>300:raise HTTPException(422,'Audio assets must be at most five minutes.')
            info={'duration':duration};kind='audio';mime='audio/wav';extension='.wav'
        else:raise HTTPException(422,'Upload PNG, JPEG, WebP, MP3, WAV, OGG, FLAC or M4A. SVG must first be safely rasterized by the editor.')
        storage_key=f'{user.id}/editor-assets/{key}{extension}';put_file(output,storage_key)
        item={'id':key,'name':(file.filename or 'Asset')[:200],'kind':kind,'mime':mime,'storage_key':storage_key,'size_bytes':output.stat().st_size,**info}
    user.preferences={**user.preferences,'editor_assets':[*assets(user),item]};db.commit();return public_asset(item)

class FromSource(BaseModel):source_id:str
@router.post('/assets/from-source')
def from_source(body:FromSource,user:User=Depends(current_user),db:Session=Depends(get_db)):
    source=owner(db,SourceVideo,body.source_id,user)
    existing=next((a for a in assets(user) if a.get('source_id')==source.id),None)
    if existing:return public_asset(existing)
    item={'id':str(uuid.uuid4()),'source_id':source.id,'name':source.filename,'kind':'video','mime':'video/webm' if source.filename.lower().endswith('.webm') else 'video/mp4','storage_key':source.storage_key,'size_bytes':source.size_bytes,**source.media_info}
    user.preferences={**user.preferences,'editor_assets':[*assets(user),item]};db.commit();return public_asset(item)

@router.get('/assets/{key}/content')
def asset_content(key:str,user:User=Depends(current_user)):
    a=asset(user,key);return FileResponse(local_path(a['storage_key']),media_type=a['mime'],headers={'Cache-Control':'private, max-age=3600','X-Content-Type-Options':'nosniff'})

class AssetRename(BaseModel):name:str=Field(min_length=1,max_length=200)
@router.patch('/assets/{key}')
def rename_asset(key:str,body:AssetRename,user:User=Depends(current_user),db:Session=Depends(get_db)):
    a=asset(user,key);next_asset={**a,'name':body.name};user.preferences={**user.preferences,'editor_assets':[next_asset if x['id']==key else x for x in assets(user)]};db.commit();return public_asset(next_asset)

@router.delete('/assets/{key}')
def archive_asset(key:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    asset(user,key)
    references=[p.plan for p in db.scalars(select(EditingPlan).join(RenderedClip,RenderedClip.editing_plan_id==EditingPlan.id).where(RenderedClip.user_id==user.id))]
    references += [v.plan for v in db.scalars(select(ClipVersion).join(RenderedClip).where(RenderedClip.user_id==user.id))]
    references += list(user.preferences.get('editor_drafts',{}).values())+user.preferences.get('editor_templates',[])
    if any(key in json.dumps(record) for record in references):raise HTTPException(409,'This asset is used by a saved clip, version, draft or template. Keep it to preserve those projects.')
    user.preferences={**user.preferences,'editor_assets':[{**a,'archived':True} if a['id']==key else a for a in assets(user)]};db.commit();return {'archived':True,'original_preserved':True}

class DraftInput(BaseModel):
    revision:int=Field(ge=0)
    plan:dict
    metadata:dict

@router.get('/drafts/{clip_id}')
def load_draft(clip_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    owner(db,RenderedClip,clip_id,user);return user.preferences.get('editor_drafts',{}).get(clip_id)

@router.post('/drafts/{clip_id}/duplicate')
def duplicate_draft(clip_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from copy import deepcopy
    from .services.local import LocalPipelineService
    original=owner(db,RenderedClip,clip_id,user);old=db.get(EditingPlan,original.editing_plan_id)
    plan=EditingPlan(candidate_id=old.candidate_id,plan=deepcopy(old.plan),rules_snapshot=deepcopy(old.rules_snapshot));db.add(plan);db.flush()
    clip=RenderedClip(user_id=user.id,job_id=original.job_id,campaign_id=original.campaign_id,source_id=original.source_id,editing_plan_id=plan.id,title=(original.title+' · copy')[:300],storage_key='pending',media_info=deepcopy(original.media_info),metadata_json=deepcopy(original.metadata_json),edit_dna=deepcopy(original.edit_dna),compliance=deepcopy(original.compliance),status='review',draft_approved=False)
    db.add(clip);db.flush();key=f'{user.id}/clips/{clip.id}/v1.mp4'
    from .main import rights_for
    clip.compliance=LocalPipelineService().check_compliance(plan.plan,clip.metadata_json,plan.rules_snapshot,rights_for(db,clip.source_id,user.id),clip.media_info,draft_approved=False)
    with materialize(original.storage_key) as path:put_file(path,key)
    clip.storage_key=key
    if original.media_info.get('remotion_base_key'):
        base_key=f'{user.id}/clips/{clip.id}/v1-base.mp4'
        with materialize(original.media_info['remotion_base_key']) as path:put_file(path,base_key)
        clip.media_info={**clip.media_info,'remotion_base_key':base_key}
    db.add(ClipVersion(clip_id=clip.id,version=1,plan=plan.plan,metadata_json=clip.metadata_json,storage_key=key));db.commit()
    return {'id':clip.id,'original_preserved':True,'current_version':1}

@router.put('/drafts/{clip_id}')
def save_draft(clip_id:str,body:DraftInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    clip=owner(db,RenderedClip,clip_id,user);drafts=user.preferences.get('editor_drafts',{});old=drafts.get(clip_id)
    if body.revision!=(old or {}).get('revision',0):raise HTTPException(409,'This draft changed in another window. Reopen it before saving.')
    try:plan=ClipPlan.model_validate(body.plan).model_dump();metadata=Metadata.model_validate(body.metadata).model_dump()
    except ValidationError as exc:raise HTTPException(422,'Invalid editable plan or publication metadata.') from exc
    check_assets(user,plan)
    result={'plan':plan,'metadata':metadata,'revision':body.revision+1,'base_version':clip.current_version}
    if len(drafts)>=50 and clip_id not in drafts:raise HTTPException(422,'Save or archive an existing editor draft before creating another.')
    user.preferences={**user.preferences,'editor_drafts':{**drafts,clip_id:result}};db.commit();return result

class TemplateInput(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    editor:EditorState
    duration:float=Field(ge=1,le=600)
    campaign_id:str|None=None

@router.get('/templates')
def templates(user:User=Depends(current_user)):return user.preferences.get('editor_templates',[])

@router.post('/templates')
def save_template(body:TemplateInput,user:User=Depends(current_user),db:Session=Depends(get_db)):
    body.editor.check_duration(body.duration);check_assets(user,{'editor':body.editor.model_dump()})
    if body.campaign_id:
        from .models import Campaign
        owner(db,Campaign,body.campaign_id,user)
    existing=user.preferences.get('editor_templates',[])
    if len(existing)>=50:raise HTTPException(422,'Keep at most 50 reusable designs.')
    item={'id':str(uuid.uuid4()),**body.model_dump()};user.preferences={**user.preferences,'editor_templates':[*existing,item]};db.commit();return item
