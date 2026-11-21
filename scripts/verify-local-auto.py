"""Opt-in real inference acceptance. Supply only authorized media.

Start the local model server before running this script. No public post occurs.
"""
import os,sys,json,time,threading,subprocess
from pathlib import Path
import argparse,uuid
parser=argparse.ArgumentParser(description='Run real local Auto Create acceptance with isolated storage. No mocked inference.')
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--rights-note',required=True)
parser.add_argument('--model',default='qwen3-vl:4b-instruct')
parser.add_argument('--endpoint',default='http://127.0.0.1:11435')
parser.add_argument('--speech-model',default=None,help='Optional cached Faster-whisper model path')
args=parser.parse_args()
if len(args.rights_note.strip())<8: parser.error('Provide a meaningful source permission note.')
root=Path(__file__).resolve().parents[1]
os.chdir(root)
run=root/'.runtime'/('acceptance-'+uuid.uuid4().hex)
run.mkdir(parents=True)
os.environ.update(FREE_MODE='true',LOCAL_NO_AUTH='true',APP_ENV='development',DATABASE_URL='sqlite:///'+str(run/'acceptance.db').replace('\\','/'),MEDIA_ROOT=str(run/'media'),OLLAMA_BASE_URL=args.endpoint,OLLAMA_MODEL=args.model,LOCAL_AI_MAX_FRAMES='4',LOCAL_AI_FRAME_BATCH_SIZE='1')
os.environ['MAX_UPLOAD_MB']='1500'
if args.speech_model:
 os.environ['LOCAL_WHISPER_MODEL']=args.speech_model
else:
 try:
  from faster_whisper.utils import download_model
  os.environ['LOCAL_WHISPER_MODEL']=download_model('base',cache_dir=str(root/'.runtime/local-ultimate-media/models/faster-whisper'),local_files_only=True)
 except (ImportError,OSError):
  pass
sys.path.insert(0,str(root/'backend'))
from app.main import app
from app import worker
from fastapi.testclient import TestClient
source=args.source.resolve()
samples=[];done=threading.Event()
def monitor():
 while not done.wait(.5):
  r=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
  try:samples.append(int(r.stdout.strip()))
  except ValueError:pass
threading.Thread(target=monitor,daemon=True).start();start=time.monotonic()
try:
 with TestClient(app) as client:
  print('Uploading user-selected source to isolated local acceptance database',flush=True)
  with source.open('rb') as stream:
   response=client.post('/api/sources',files={'file':(source.name,stream,'video/mp4')},data={'rights_confirmed':'true','rights_note':args.rights_note})
  response.raise_for_status();sid=response.json()['id']
  response=client.post('/api/auto/jobs',json={'source_id':sid});response.raise_for_status();job=response.json();print('AUTO CREATE queued '+job['id'],flush=True)
  worker.run_once()
  jobs=client.get('/api/jobs').json();current=next(j for j in jobs if j['id']==job['id'])
  print(json.dumps({'status':current['status'],'error':current['error'],'progress':current['progress']}),flush=True)
  (run/'job.json').write_text(json.dumps(current,indent=2),encoding='utf-8')
  response=client.get('/api/auto/jobs/'+job['id']+'/result');response.raise_for_status();result=response.json()
  (run/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
  video=client.get('/api/clips/'+result['clip']['id']+'/download');video.raise_for_status();(run/'final.mp4').write_bytes(video.content)
  package=client.get('/api/auto/jobs/'+job['id']+'/package');package.raise_for_status();(run/'package.zip').write_bytes(package.content)
  print(json.dumps({'title':result['recommended']['title'],'research':result['research']['status'],'video_bytes':len(video.content),'elapsed':round(time.monotonic()-start,2),'output_directory':str(run)}),flush=True)
finally:
 done.set();(run/'gpu.json').write_text(json.dumps({'peak_mib':max(samples) if samples else None,'samples':samples,'gpu_validation':'measured' if samples else 'unavailable: NVIDIA samples could not be read'}),encoding='utf-8')
