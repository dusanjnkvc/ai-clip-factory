"""Backend tests use isolated SQLite and generated test media; no external account is contacted."""
import os
import subprocess
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main, storage, worker
from app.db import Base, get_db
from app.models import *
from app.security import _attempts, verify_password, hash_password
from app.submissions import countdown, estimate_earnings

@pytest.fixture
def environment(tmp_path,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('S3_BUCKET',raising=False)
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine,expire_on_commit=False)
    def db_dependency():
        with factory() as db:
            yield db
    main.app.dependency_overrides[get_db]=db_dependency
    config=replace(main.settings,media_root=tmp_path/'media')
    config.media_root.mkdir()
    monkeypatch.setattr(main,'settings',config)
    monkeypatch.setattr(storage,'settings',config)
    monkeypatch.setattr(worker,'SessionLocal',factory)
    _attempts.clear()
    with TestClient(main.app) as client:
        yield client,factory,config
    main.app.dependency_overrides.clear()
    engine.dispose()

def register(client,email='creator@example.com'):
    response=client.post('/api/auth/register',json={'email':email,'password':'correct horse battery staple','name':'Creator'})
    assert response.status_code==200,response.text
    return response.json()

def seed_job_data(factory,user_id,config):
    with factory() as db:
        campaign=Campaign(user_id=user_id,name='Authorized campaign',brief='Use YouTube. No draft approval.',rules={'allowed_platforms':['youtube'],'draft_approval_required':False,'min_duration':1,'max_duration':30,'evidence':[{'field':'allowed_platforms','quote':'Use YouTube','source':'brief'}]},status='active',review_required=False)
        source=SourceVideo(user_id=user_id,filename='owned.mp4',storage_key=f'{user_id}/source.mp4',sha256='a'*64,size_bytes=1,media_info={'duration':2,'width':320,'height':180,'has_audio':True})
        db.add_all([campaign,source])
        db.flush()
        db.add(MediaRightsRecord(source_id=source.id,user_id=user_id,confirmed=True,note='I created and own this generated test media.'))
        db.commit()
        path=storage.local_path(source.storage_key)
        path.parent.mkdir(parents=True)
        import imageio_ffmpeg
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i','testsrc2=size=320x180:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],check=True,capture_output=True)
        return campaign.id,source.id

def test_auth_sessions_passwords_and_origin(environment):
    client,factory,_=environment
    assert client.get('/api/auth/me').status_code==401
    user=register(client)
    cookie=client.cookies.get('acf_session')
    assert len(cookie)>30
    assert client.get('/api/auth/me').json()['id']==user['id']
    with factory() as db:
        stored=db.get(User,user['id'])
        assert stored.password_hash.startswith('scrypt$')
        assert 'correct horse' not in stored.password_hash
        assert verify_password('correct horse battery staple',stored.password_hash)
    assert client.patch('/api/settings',json={'monthly_spend_limit_usd':10,'max_job_cost_usd':1},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'email':user['email'],'password':'incorrect password'}).status_code==401
    assert client.post('/api/auth/login',json={'email':user['email'],'password':'correct horse battery staple'}).status_code==200

def test_campaign_preserves_input_when_ai_unconfigured_and_manual_review(environment):
    client,factory,_=environment
    register(client)
    campaign=client.post('/api/campaigns',json={'name':'My campaign','brief':'YouTube, 10–30 seconds. #owned'}).json()
    assert campaign['status']=='draft'
    assert 'OPENAI_API_KEY' in campaign['analysis_error']
    assert campaign['rules']=={}
    reviewed=client.patch(f"/api/campaigns/{campaign['id']}/rules",json={'rules':{'allowed_platforms':['youtube'],'min_duration':10,'max_duration':30,'draft_approval_required':False},'note':'Reviewed original authorized campaign brief.'})
    assert reviewed.status_code==200,reviewed.text
    assert reviewed.json()['rules']['min_duration']==10
    assert reviewed.json()['evidence'][-1]['source']=='manual_review'

def test_owner_scoping_zero_analytics_and_budget(environment):
    client,factory,config=environment
    first=register(client)
    campaign_id,source_id=seed_job_data(factory,first['id'],config)
    dashboard=client.get('/api/dashboard').json()
    assert dashboard['metrics']['reported_views']==0
    assert dashboard['metrics']['estimated_earnings']==0
    assert dashboard['metrics']['paid_earnings']==0
    assert client.patch('/api/settings',json={'monthly_spend_limit_usd':0,'max_job_cost_usd':1}).status_code==200
    assert client.post('/api/jobs',json={'campaign_id':campaign_id,'source_id':source_id}).status_code==402
    client.post('/api/auth/logout')
    register(client,'other@example.com')
    assert client.get('/api/campaigns').json()==[]
    assert client.post('/api/jobs',json={'campaign_id':campaign_id,'source_id':source_id}).status_code==404

def test_real_source_upload_and_missing_ai_job_blocked(environment):
    client,factory,config=environment
    user=register(client)
    campaign_id,source_id=seed_job_data(factory,user['id'],config)
    source_path=storage.local_path(f"{user['id']}/source.mp4")
    with source_path.open('rb') as media:
        invalid=client.post('/api/sources',files={'file':('owned.mp4',media,'video/mp4')},data={'rights_confirmed':'false','rights_note':'I own it.'})
        assert invalid.status_code==422
    with source_path.open('rb') as media:
        uploaded=client.post('/api/sources',files={'file':('owned.mp4',media,'video/mp4')},data={'rights_confirmed':'true','rights_note':'I generated this media and own publication rights.'})
    assert uploaded.status_code==200,uploaded.text
    assert uploaded.json()['media_info']['has_audio'] is True
    assert 'path' not in uploaded.json()['media_info']
    response=client.post('/api/jobs',json={'campaign_id':campaign_id,'source_id':uploaded.json()['id'],'mode':'fast','clip_count':1})
    assert response.status_code==200,response.text
    job_id=response.json()['id']
    assert worker.run_once() is True
    result=next(j for j in client.get('/api/jobs').json() if j['id']==job_id)
    assert result['status']=='blocked'
    assert 'OPENAI_API_KEY' in result['error']
    assert client.get('/api/clips').json()==[]

def seed_clip(factory,user_id,config):
    campaign_id,source_id=seed_job_data(factory,user_id,config)
    with factory() as db:
        campaign=db.get(Campaign,campaign_id)
        campaign.rules={**campaign.rules,'submission_window_minutes':30}
        job=ProcessingJob(user_id=user_id,campaign_id=campaign_id,source_id=source_id,rules_snapshot=campaign.rules)
        db.add(job)
        db.flush()
        candidate=ClipCandidate(job_id=job.id,source_id=source_id,start=0,end=2,scores={},fingerprint='f'*64)
        db.add(candidate)
        db.flush()
        plan=EditingPlan(candidate_id=candidate.id,plan={},rules_snapshot=campaign.rules)
        db.add(plan)
        db.flush()
        clip=RenderedClip(user_id=user_id,job_id=job.id,campaign_id=campaign_id,source_id=source_id,editing_plan_id=plan.id,title='Test clip',storage_key='not-rendered',media_info={},metadata_json={},edit_dna={},compliance={'status':'REVIEW_REQUIRED'})
        db.add(clip)
        db.commit()
        return clip.id,campaign_id

def test_submission_countdown_starts_at_actual_publication(environment):
    client,factory,config=environment
    user=register(client)
    clip_id,campaign_id=seed_clip(factory,user['id'],config)
    published=now()-timedelta(minutes=20)
    response=client.post(f'/api/clips/{clip_id}/record-publication',json={'platform':'youtube','url':'https://www.youtube.com/watch?v=test123','published_at':published.isoformat()+'Z','confirmation':'I verified the public post and actual publication time.'})
    assert response.status_code==200,response.text
    submission=response.json()['submission']
    assert 590<=submission['seconds_remaining']<=600
    assert submission['warning']=='10 minutes remaining'
    pending=client.get('/api/submissions').json()[0]
    assert pending['post_url'].endswith('test123')
    confirmed=client.post(f"/api/submissions/{submission['id']}/confirm",json={'status':'submitted','confirmation':'Campaign submission receipt reference TEST-123.'})
    assert confirmed.json()['status']=='submitted'
    assert confirmed.json()['deadline']==submission['deadline']

def test_publish_requires_authorization_compliance_and_eligible_platform(environment):
    client,factory,config=environment
    user=register(client)
    clip_id,_=seed_clip(factory,user['id'],config)
    with factory() as db:
        account=ConnectedAccount(user_id=user['id'],platform='youtube',external_id='channel',name='My channel',encrypted_credentials='encrypted')
        db.add(account)
        db.commit()
        account_id=account.id
    body={'account_id':account_id,'explicit_authorization':False,'privacy':'public'}
    assert client.post(f'/api/clips/{clip_id}/publish',json=body).status_code==422
    body['explicit_authorization']=True
    assert client.post(f'/api/clips/{clip_id}/publish',json=body).status_code==409
    assert client.get('/api/publishing').json()==[]

def test_earnings_separate_eligibility_currency_and_reported_costs(environment):
    client,factory,config=environment
    user=register(client)
    campaign_id,_=seed_job_data(factory,user['id'],config)
    for kind,amount,currency in [('estimated',12,'USD'),('confirmed',5,'USD'),('paid',3,'USD'),('paid',100,'EUR')]:
        assert client.post('/api/earnings',json={'campaign_id':campaign_id,'kind':kind,'amount':amount,'currency':currency,'provenance':'User confirmed campaign dashboard import.'}).status_code==200
    metric=client.get('/api/dashboard').json()['metrics']
    assert metric['estimated_earnings']==12
    assert metric['confirmed_earnings']==5
    assert metric['paid_earnings']==3
    assert metric['processing_expenses']==0
    assert estimate_earnings('cpm',eligible_views=None,rate=2) is None
    assert estimate_earnings('cpm',eligible_views=12000,rate=2,maximum=20)==20
    assert estimate_earnings('shared_pool',eligible_views=1000,rate=2) is None

def test_budget_includes_campaign_analysis_and_is_shared_across_users(environment,monkeypatch):
    client,factory,config=environment
    first=register(client)
    assert client.patch('/api/settings',json={'monthly_spend_limit_usd':0,'max_job_cost_usd':1}).status_code==200
    monkeypatch.setenv('OPENAI_API_KEY','test-key-never-sent')
    result=client.post('/api/campaigns',json={'name':'No budget','brief':'No cloud call should occur.'})
    assert result.status_code==402
    with factory() as db:
        user=db.get(User,first['id'])
        user.preferences={}
        db.add(ProcessingCost(user_id=first['id'],amount=config.monthly_limit,kind='reserved',provider='test allowance'))
        db.commit()
    client.post('/api/auth/logout')
    register(client,'second@example.com')
    assert client.post('/api/campaigns',json={'name':'Global cap','brief':'Must stop before network.'}).status_code==402

def test_upload_retry_uses_active_lease_not_job_creation(environment):
    client,factory,config=environment
    user=register(client)
    clip_id,_=seed_clip(factory,user['id'],config)
    with factory() as db:
        account=ConnectedAccount(user_id=user['id'],platform='youtube',external_id='channel',name='Channel',encrypted_credentials='encrypted')
        db.add(account)
        db.flush()
        job=PublishingJob(user_id=user['id'],clip_id=clip_id,account_id=account.id,platform='youtube',version=1,status='uploading',authorized=True,created_at=now()-timedelta(days=1),upload_started_at=now(),upload_lease_until=now()+timedelta(minutes=30))
        db.add(job)
        db.commit()
        job_id=job.id
    assert client.post(f'/api/publishing/{job_id}/retry').status_code==409


def test_expired_attendance_stops_before_any_external_upload(environment,monkeypatch):
    from app import publishing
    client,factory,config=environment
    user=register(client)
    clip_id,_=seed_clip(factory,user['id'],config)
    def unexpected_network(*args,**kwargs):
        raise AssertionError('Expired attendance must stop before requesting an access token.')
    monkeypatch.setattr(publishing,'access_token',unexpected_network)
    with factory() as db:
        clip=db.get(RenderedClip,clip_id)
        clip.compliance={'status':'PASS'}
        account=ConnectedAccount(user_id=user['id'],platform='youtube',external_id='expired-test',name='Channel',encrypted_credentials='not-a-real-token')
        db.add(account)
        db.flush()
        job=PublishingJob(user_id=user['id'],clip_id=clip_id,account_id=account.id,platform='youtube',version=1,authorized=True,attended=True,authorization_expires_at=now()-timedelta(seconds=1))
        db.add(job)
        db.commit()
        publishing.publish_youtube(db,job)
        assert job.status=='needs_authorization'
        assert 'expired' in job.error
        assert db.scalar(select(PublishedPost.id)) is None
        assert db.scalar(select(CampaignSubmission.id)) is None


def test_full_api_bounds_unauthenticated_upload_before_parsing(environment):
    client,_,_=environment
    response=client.post('/api/sources',content=b'',headers={'Content-Length':str(600*1024*1024)})
    assert response.status_code==413
    assert 'upload limit' in response.json()['detail']


def test_malformed_metadata_returns_validation_error_without_changing_clip(environment):
    client,factory,config=environment
    user=register(client)
    clip_id,_=seed_clip(factory,user['id'],config)
    response=client.patch(f'/api/clips/{clip_id}/metadata',json={'metadata':{'youtube':{'title':'incomplete'}}})
    assert response.status_code==422
    with factory() as db:
        clip=db.get(RenderedClip,clip_id)
        assert clip.metadata_json=={}
        assert clip.current_version==1


def test_reported_usage_is_persisted_without_inventing_a_price(environment):
    from types import SimpleNamespace
    from app.usage import record_usage
    client,factory,_=environment
    user=register(client)
    service=SimpleNamespace(usage=[{'operation':'/chat/completions','model':'test-only','usage':{'total_tokens':42},'provider_reported':True}])
    with factory() as db:
        record_usage(db,service,user['id'])
        db.commit()
        row=db.scalar(select(AuditLog).where(AuditLog.action=='ai.usage'))
        assert row.detail['usage']['total_tokens']==42
        assert 'amount' not in row.detail
        assert service.usage==[]
