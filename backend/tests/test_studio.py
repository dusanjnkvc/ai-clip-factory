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
        def finalize_metadata(self,*a,**kw):return sample_metadata()
    monkeypatch.setattr('app.services.local_auto.LocalAutoPipelineService',Controlled)
    project=client.post('/api/studio/projects',json={'name':'Three clips','source_id':source,'campaign_id':campaign}).json()
    assert project['options']['duration']==10 and project['options']['clip_count']==3
    first=client.post(f"/api/studio/projects/{project['id']}/start")
    assert first.status_code==200,first.text
    assert client.post(f"/api/studio/projects/{project['id']}/start").json()['id']==first.json()['id']
    assert worker.run_once()
    detail=client.get(f"/api/studio/projects/{project['id']}").json()
    assert len(detail['drafts'])==3 and all(d['media_info']['decode_verified'] for d in detail['drafts'])
    gallery=client.get('/api/studio/clips').json()
    assert len(gallery)==3 and gallery[0]['campaign_name']=='Authorized campaign'
    assert 'publishing_jobs' in gallery[0] and gallery[0]['decision']=='needs_review'
    custom=client.post('/api/studio/projects',json={'name':'Five requested','source_id':source,'clip_count':5,'destination':'both'})
    assert custom.status_code==200 and custom.json()['options']['clip_count']==5
    assert all(d['decision']=='needs_review' for d in detail['drafts'])
    clip=detail['drafts'][0]
    assert client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':1,'decision':'approved','note':'I reviewed the video.'}).status_code==409
    response=client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':1,'decision':'rejected','note':'Please adjust the framing.'})
    assert response.status_code==200
    assert client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':2,'decision':'rejected','note':'Wrong version review.'}).status_code==409
    assert client.post(f"/api/studio/drafts/{clip['id']}/edit",json={'version':2,'metadata':sample_metadata()}).status_code==409
    assert client.get(f"/api/studio/projects/{project['id']}/export").status_code==409
    # The generated fixture is ours and contains only known test patterns/audio.
    review=client.post(f"/api/clips/{clip['id']}/review",json={'note':'Reviewed the actual generated test fixture.',
        'evidence':{'creative_context':{'confirmed':True,'note':'Only generated test patterns are present; this is controlled contract validation.'}}})
    assert review.status_code==200 and review.json()['compliance']['status']=='PASS',review.text
    assert client.post(f"/api/studio/drafts/{clip['id']}/decision",json={'version':1,'decision':'approved','note':'Approved the controlled generated fixture.'}).status_code==200
    exported=client.get(f"/api/studio/projects/{project['id']}/export")
    import io,zipfile
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert len([n for n in archive.namelist() if n.endswith('/clip.mp4')])==1
    changed=client.patch(f"/api/clips/{clip['id']}/metadata",json={'metadata':sample_metadata()})
    assert changed.status_code==200 and changed.json()['current_version']==2
    assert client.get(f"/api/studio/projects/{project['id']}/export").status_code==409
    assert client.post(f"/api/studio/drafts/{clip['id']}/regenerate-component",json={'component':'captions','version':1}).status_code==409
    response=client.post(f"/api/studio/drafts/{clip['id']}/regenerate-component",json={'component':'captions','version':2})
    assert response.status_code==200 and response.json()['payload']['plan']['manual_captions']==[]


def test_source_proxy_is_rebuildable_without_modifying_original(environment,monkeypatch):
    client,factory,config=environment;user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    enable(monkeypatch)
    from app.models import SourceVideo
    from app.storage import local_path
    from app.services.media import sha256_file
    with factory() as db:path=local_path(db.get(SourceVideo,source).storage_key)
    original=sha256_file(path)
    proxy=client.post(f'/api/studio/sources/{source}/preview')
    assert proxy.status_code==200,proxy.text
    assert proxy.json()['media_info']['width']<=720
    assert client.get(proxy.json()['preview_url']).status_code==200
    assert sha256_file(path)==original
    client.delete('/api/studio/cache')
    assert client.get(proxy.json()['preview_url']).status_code==404 and sha256_file(path)==original


def test_directory_import_restricts_paths_and_preserves_original(environment,monkeypatch,tmp_path):
    client,factory,config=environment;user=register(client);campaign,source=seed_job_data(factory,user['id'],config)
    enable(monkeypatch)
    response=client.patch('/api/studio/input-directory',json={'path':str(tmp_path)})
    assert response.status_code==200
    payload={'filename':'../private.mp4','rights_confirmed':True,'rights_note':'I created this source.'}
    assert client.post('/api/studio/input-directory/import',json=payload).status_code==422
    assert client.post('/api/studio/projects',json={'name':'Bad bounds','source_id':source,'minimum_duration':20,'maximum_duration':6}).status_code==422
    cache=config.media_root/'analysis-cache';cache.mkdir()
    cached=cache/'measurement.json';cached.write_text('{}')
    original=config.media_root/'original.mp4';original.write_bytes(b'Original placeholder, never eligible for cache deletion.')
    response=client.delete('/api/studio/cache')
    assert response.status_code==200 and response.json()['removed_files']==1
    assert original.is_file() and not cached.exists()


def test_single_clip_edit_restore_and_selective_regeneration_preserve_other_fields(environment,monkeypatch):
    import copy
    from app.services.schemas import Metadata
    from test_social import setup_social,seed_clip
    from app.models import ClipVersion,ProcessingJob,EditingPlan
    client,factory,config=environment;user=register(client);setup_social(monkeypatch);enable(monkeypatch)
    clip_id,_=seed_clip(factory,user['id'],config)
    with factory() as db:
        clip=db.get(RenderedClip,clip_id);original=Metadata.model_validate(clip.metadata_json).model_dump()
        db.add(ClipVersion(clip_id=clip.id,version=1,plan=db.get(EditingPlan,clip.editing_plan_id).plan,metadata_json=original,storage_key=clip.storage_key));db.commit()
    edited=copy.deepcopy(original);edited['youtube']['variants'][0]['description']='My retained manual description.'
    edited['tiktok']['generation_status']='manual'
    response=client.post(f'/api/studio/drafts/{clip_id}/edit',json={'version':1,'metadata':edited})
    assert response.status_code==200,response.text
    assert response.json()['action']=='metadata_saved'
    generated=copy.deepcopy(original)
    for v in generated['youtube']['variants']:v['title']='Regenerated title'
    monkeypatch.setattr('app.services.studio_metadata.rendered_context',lambda *args:{'findings':[]})
    monkeypatch.setattr('app.services.studio_metadata.generate_studio_package',lambda *args,**kw:{'metadata':generated})
    response=client.post(f'/api/studio/drafts/{clip_id}/regenerate-component',json={'version':2,'component':'metadata','platform':'youtube','field':'title'})
    assert response.status_code==200,response.text
    with factory() as db:
        clip=db.get(RenderedClip,clip_id)
        assert clip.current_version==3 and clip.metadata_json['tiktok']==edited['tiktok']
        assert clip.metadata_json['youtube']['variants'][0]['description']=='My retained manual description.'
        assert clip.metadata_json['youtube']['variants'][0]['opening_hook']==edited['youtube']['variants'][0]['opening_hook']
        assert db.scalar(select(ProcessingJob.id).where(ProcessingJob.status=='queued')) is None
    response=client.post(f'/api/studio/drafts/{clip_id}/edit',json={'version':3,'restore_version':1})
    assert response.status_code==200,response.text
    assert response.json()['action']=='render_queued'
    with factory() as db:
        job=db.get(ProcessingJob,response.json()['job']['id'])
        assert job.clip_count==1 and job.payload['clip_id']==clip_id
        assert job.payload['metadata']==original and db.get(RenderedClip,clip_id).current_version==3
        assert len(list(db.scalars(select(ClipVersion).where(ClipVersion.clip_id==clip_id))))==3


def test_bounded_polish_retains_decoded_original_when_second_render_fails(tmp_path,monkeypatch):
    import copy
    from app.services.media import PipelineError
    service=LocalAutoPipelineService({'studio':True})
    original=tmp_path/'clip.mp4';original.write_bytes(b'Already decoded original fixture')
    plan=sample_plan();plan['subtitle_style']='bold';before=copy.deepcopy(plan)
    monkeypatch.setattr(service.provider,'unload',lambda:None)
    def unavailable(*args,**kw):raise PipelineError('Controlled second-render failure')
    monkeypatch.setattr(service,'render_clip',unavailable)
    render={'decode_verified':True,'sha256':'controlled-original'}
    evaluation={'suggestions':[{'action':'clean_captions'}],'visual':{'model_review':{'readability':30}}}
    result,score=service.polish_render(tmp_path/'source.mp4',plan,sample_transcript(),original,render,sample_metadata(),evaluation,'fast')
    assert result==render and plan==before and original.read_bytes()==b'Already decoded original fixture'
    assert score['optimization']['attempts']==1 and score['optimization']['status']=='original_retained'
