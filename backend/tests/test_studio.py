from test_backend import environment,register,seed_job_data
from test_pipeline import sample_plan,sample_metadata,sample_transcript
from app.services.local_auto import LocalAutoPipelineService
from app import worker
from app.models import FactoryProject,DraftDecision,RenderedClip
from sqlalchemy import select


def enable(monkeypatch):
    monkeypatch.setenv('FREE_MODE','true');monkeypatch.setenv('LOCAL_NO_AUTH','true')
    monkeypatch.setattr('app.services.ollama_provider.OllamaProvider.require_configured',lambda self,**kw:{'available':True})


def test_project_defaults_three_drafts_persist_and_start_is_idempotent(environment,monkeypatch):
    client,factory,config=environment;user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    enable(monkeypatch)
    class Controlled(LocalAutoPipelineService):
        def transcribe(self,*a,**kw):return sample_transcript()
        def plan_clips(self,*a,**kw):
            # Controlled plans test persistence/rendering, not actual ranking semantics.
            return [{**sample_plan(),'title':f'Draft {i}','generation_method':'local_ai'} for i in range(3)]
        def generate_metadata(self,*a,**kw):
            self.bundle={'research':{'status':'unavailable'},'recommended':sample_metadata()['youtube']['variants'][0]}
            return sample_metadata()
        def evaluate_render(self,*a,**kw):
            return {'platforms':{},'controlled_test':True}
    monkeypatch.setattr('app.services.local_auto.LocalAutoPipelineService',Controlled)
    project=client.post('/api/studio/projects',json={'name':'Three clips','source_id':source,'campaign_id':campaign}).json()
    assert project['options']['duration']==10 and project['options']['clip_count']==3
    first=client.post(f"/api/studio/projects/{project['id']}/start")
    assert first.status_code==200,first.text
    assert client.post(f"/api/studio/projects/{project['id']}/start").json()['id']==first.json()['id']
    assert worker.run_once()
    detail=client.get(f"/api/studio/projects/{project['id']}").json()
    assert len(detail['drafts'])==3 and all(d['media_info']['decode_verified'] for d in detail['drafts'])
    assert all(d['decision']=='needs_review' for d in detail['drafts'])
    clip=detail['drafts'][0]
    assert client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':1,'decision':'approved','note':'I reviewed the video.'}).status_code==409
    response=client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':1,'decision':'rejected','note':'Please adjust the framing.'})
    assert response.status_code==200
    assert client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':2,'decision':'rejected','note':'Wrong version review.'}).status_code==409


def test_directory_import_restricts_paths_and_preserves_original(environment,monkeypatch,tmp_path):
    client,factory,config=environment;user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    enable(monkeypatch)
    response=client.patch('/api/studio/input-directory',json={'path':str(tmp_path)})
    assert response.status_code==200
    payload={'filename':'../private.mp4','rights_confirmed':True,'rights_note':'I created this source.'}
    assert client.post('/api/studio/input-directory/import',json=payload).status_code==422
    assert client.post('/api/studio/projects',json={'name':'Bad bounds','source_id':source,'minimum_duration':20,'maximum_duration':6}).status_code==422
