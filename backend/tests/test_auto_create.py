"""API/worker persistence with controlled inference and real FFmpeg rendering."""
from test_backend import environment, register, seed_job_data
from test_pipeline import sample_plan, sample_metadata, sample_transcript
from app import worker
from app.models import ProcessingJob, RenderedClip
from app.services.local_auto import LocalAutoPipelineService
from sqlalchemy import select


def test_auto_job_one_export_zero_budget_and_manual_workflow_preserved(environment,monkeypatch):
    client,factory,config=environment
    user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    monkeypatch.setenv('FREE_MODE','true');monkeypatch.setenv('LOCAL_NO_AUTH','true')
    monkeypatch.setattr('app.services.ollama_provider.OllamaProvider.require_configured',lambda self,**kwargs:{'available':True})
    class ControlledAuto(LocalAutoPipelineService):
        def transcribe(self,*args,**kwargs): return sample_transcript()
        def plan_clips(self,*args,**kwargs):
            plan=sample_plan();plan.update(generation_method='local_ai',show_hook=True)
            return [plan]
        def generate_metadata(self,*args):
            self.bundle={'recommended':sample_metadata()['youtube']['variants'][0],'research':{'status':'unavailable','sources':[]}}
            return sample_metadata()
    monkeypatch.setattr('app.services.local_auto.LocalAutoPipelineService',ControlledAuto)
    response=client.post('/api/auto/jobs',json={'source_id':source,'campaign_id':campaign})
    assert response.status_code==200,response.text
    job=response.json()
    assert job['cost_reservation']==0 and job['clip_count']==1
    assert worker.run_once()
    result=client.get(f"/api/auto/jobs/{job['id']}/result")
    assert result.status_code==200,result.text
    assert result.json()['clip']['media_info']['decode_verified']
    assert result.json()['recommended']['title']
    with factory() as db:
        assert len(list(db.scalars(select(RenderedClip).where(RenderedClip.job_id==job['id']))))==1
        assert db.get(ProcessingJob,job['id']).status=='completed'
    assert client.get(f"/api/auto/jobs/{job['id']}/package").content.startswith(b'PK')
    # Existing manual endpoint still accepts explicit selections.
    manual=client.post('/api/jobs',json={'source_id':source,'campaign_id':campaign,'manual_selection':{'start':0,'end':1.5,'title':'Manual'}})
    assert manual.status_code==200,manual.text


def test_queued_auto_cancellation_and_automation_prohibition(environment,monkeypatch):
    client,factory,config=environment
    user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    monkeypatch.setenv('FREE_MODE','true');monkeypatch.setenv('LOCAL_NO_AUTH','true')
    monkeypatch.setattr('app.services.ollama_provider.OllamaProvider.require_configured',lambda self,**kwargs:{'available':True})
    job=client.post('/api/auto/jobs',json={'source_id':source,'campaign_id':campaign}).json()
    assert client.post(f"/api/auto/jobs/{job['id']}/cancel").json()['status']=='cancelled'
    from app.models import Campaign
    with factory() as db:
        row=db.get(Campaign,campaign);row.rules={**row.rules,'automated_clipping_allowed':False};db.commit()
    assert client.post('/api/auto/jobs',json={'source_id':source,'campaign_id':campaign}).status_code==422
