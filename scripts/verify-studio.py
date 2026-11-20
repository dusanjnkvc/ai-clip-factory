"""Opt-in actual-model project acceptance, isolated local storage, no publishing."""
import argparse,json,os,sys,time
from pathlib import Path
from uuid import uuid4

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path)
parser.add_argument('--rights-note')
parser.add_argument('--resume',type=Path,help='Resume a prior isolated acceptance directory without reimporting source or discarding completed drafts.')
parser.add_argument('--campaign',type=Path)
parser.add_argument('--reference',type=Path)
parser.add_argument('--endpoint',default='http://127.0.0.1:11435')
parser.add_argument('--model',default='qwen3-vl:4b-instruct')
parser.add_argument('--frames',type=int,default=4,choices=range(1,49))
args=parser.parse_args()
if not args.resume and (not args.source or len((args.rights_note or '').strip())<8):parser.error('Provide the actual source and authorization note, or --resume an existing acceptance run.')
root=Path(__file__).resolve().parents[1];os.chdir(root)
output=args.resume.resolve() if args.resume else root/'.runtime'/('studio-acceptance-'+uuid4().hex)
if args.resume:
    if not (output/'studio.db').is_file():parser.error('The resumed directory must contain its existing studio.db.')
else:output.mkdir(parents=True)
os.environ.update(FREE_MODE='true',LOCAL_NO_AUTH='true',APP_ENV='development',DATABASE_URL='sqlite:///'+str(output/'studio.db').replace('\\','/'),
    MEDIA_ROOT=str(output/'media'),OLLAMA_BASE_URL=args.endpoint,OLLAMA_MODEL=args.model,MAX_UPLOAD_MB='1500',LOCAL_AI_MAX_FRAMES=str(args.frames),LOCAL_AI_FRAME_OVERRIDE='true')
from faster_whisper.utils import download_model
os.environ['LOCAL_WHISPER_MODEL']=download_model('base',cache_dir=str(root/'.runtime/local-ultimate-media/models/faster-whisper'),local_files_only=True)
sys.path.insert(0,str(root/'backend'))
from app.main import app
from app import worker
from fastapi.testclient import TestClient

with TestClient(app) as client:
    def check(response):
        if response.is_error:raise RuntimeError(f'{response.status_code}: {response.text[:1200]}')
        return response.json()
    def local_import(path):
        check(client.patch('/api/studio/input-directory',json={'path':str(path.resolve().parent)}))
        return check(client.post('/api/studio/input-directory/import',json={'filename':path.name,'rights_confirmed':True,'rights_note':args.rights_note}))
    if args.resume:
        projects=check(client.get('/api/studio/projects'))
        if not projects:parser.error('No persisted project exists in this acceptance database.')
        project=projects[0];job=project.get('job')
        if job and job['status'] in {'failed','blocked'}:job=check(client.post(f"/api/jobs/{job['id']}/retry"))
    else:
        source=local_import(args.source)
        campaign=None
        if args.campaign:
            campaign=check(client.post('/api/campaigns',json={'name':'Local acceptance sample campaign','brief':''}))
            with args.campaign.open('rb') as stream:
                campaign=check(client.post(f"/api/campaigns/{campaign['id']}/attachments",files={'file':(args.campaign.name,stream)}))
        references=[]
        if args.reference:
            ref=local_import(args.reference)
            references=[check(client.post('/api/studio/references',json={'source_id':ref['id'],'name':'Acceptance reference'}))['id']]
        project=check(client.post('/api/studio/projects',json={'name':'Actual local-model gaming acceptance','source_id':source['id'],
            'campaign_id':campaign['id'] if campaign else None,'reference_ids':references,'editing_profile':'automatic'}))
        job=check(client.post(f"/api/studio/projects/{project['id']}/start"))
    original_progress=worker.progress
    def progress(job_id,stage,percent):
        print(json.dumps({'stage':stage,'progress':percent}),flush=True);original_progress(job_id,stage,percent)
    worker.progress=progress
    started=time.monotonic()
    if job and job['status']!='completed':worker.run_once()
    result=check(client.get(f"/api/studio/projects/{project['id']}"))
    result['elapsed_seconds']=round(time.monotonic()-started,2)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(output),'job':result['job']['status'],'error':result['job']['error'],'drafts':len(result['drafts']),'elapsed':result['elapsed_seconds']}),flush=True)
    for i,draft in enumerate(result['drafts'],1):
        video=client.get(f"/api/clips/{draft['id']}/download");video.raise_for_status();(output/f'draft-{i}.mp4').write_bytes(video.content)
    assert result['job']['status']=='completed',result['job']['error']
    assert len(result['drafts'])>=1,'No actual drafts produced.'
