import json,time
from urllib.parse import parse_qs,urlparse
import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_backend import environment,register,seed_job_data
from test_pipeline import sample_plan,sample_metadata
from app.models import ConnectedAccount,ClipCandidate,EditingPlan,RenderedClip,DraftEvaluation,DraftDecision,PublishingJob,PublishedPost
from app import social


def setup_social(monkeypatch):
    monkeypatch.setenv('FREE_MODE','true');monkeypatch.setenv('SOCIAL_INTEGRATIONS_ENABLED','true')
    monkeypatch.setenv('TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    monkeypatch.setenv('TIKTOK_CLIENT_KEY','test-client');monkeypatch.setenv('TIKTOK_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('TIKTOK_REDIRECT_URI','https://localhost.example/api/social/tiktok/callback')
    monkeypatch.setenv('TIKTOK_SCOPES','user.info.basic,video.list,video.publish')
    monkeypatch.setenv('TIKTOK_DIRECT_POST_AUDITED','false')


def test_inbox_delivery_uses_upload_scope_and_never_invents_a_public_post(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip_id,account_id=seed_clip(factory,user['id'],config)
    with factory() as db:
        account=db.get(ConnectedAccount,account_id);account.scopes=['user.info.basic','video.upload'];db.commit()
    endpoints=[]
    def request(endpoint,*args,**kwargs):
        endpoints.append(endpoint)
        if endpoint.endswith('init/'):
            assert endpoint=='post/publish/inbox/video/init/'
            assert 'post_info' not in kwargs['json']
            return {'publish_id':'controlled-inbox','upload_url':'https://upload.tiktokapis.com/controlled'}
        return {'status':'SEND_TO_USER_INBOX'}
    monkeypatch.setattr(social,'tiktok_request',request)
    original=httpx.Client
    monkeypatch.setattr(social.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(lambda req:httpx.Response(201)),**kw))
    response=client.post(f'/api/social/clips/{clip_id}/tiktok',json={'account_id':account_id,'version':1,'explicit_authorization':True,'delivery':'inbox','privacy_level':'SELF_ONLY','consent_to_music_usage':True,'brand_content_toggle':False,'brand_organic_toggle':False})
    assert response.status_code==200,response.text
    with factory() as db:
        job=db.get(PublishingJob,response.json()['id']);social.publish_tiktok(db,job)
        assert job.status=='uploaded_draft' and db.scalar(select(PublishedPost.id)) is None
    assert 'post/publish/creator_info/query/' not in endpoints


def seed_clip(factory,user_id,config):
    campaign,source=seed_job_data(factory,user_id,config)
    from app.models import ProcessingJob,Campaign,SourceVideo
    with factory() as db:
        c=db.get(Campaign,campaign);c.rules={**c.rules,'allowed_platforms':['youtube','tiktok']}
        job=ProcessingJob(user_id=user_id,campaign_id=campaign,source_id=source,status='completed',rules_snapshot=c.rules)
        db.add(job);db.flush()
        candidate=ClipCandidate(job_id=job.id,source_id=source,start=0,end=2,scores={},fingerprint='controlled-protocol-test')
        db.add(candidate);db.flush()
        plan=EditingPlan(candidate_id=candidate.id,plan=sample_plan(),rules_snapshot=c.rules);db.add(plan);db.flush()
        clip=RenderedClip(user_id=user_id,job_id=job.id,campaign_id=campaign,source_id=source,editing_plan_id=plan.id,
            title='Controlled protocol fixture',storage_key=db.get(SourceVideo,source).storage_key,media_info={'duration':2},metadata_json=sample_metadata(),edit_dna={},compliance={'status':'PASS'})
        db.add(clip);db.flush()
        db.add(DraftEvaluation(clip_id=clip.id,version=1,artifact_sha256='a'*64,evaluation={'controlled_test':True}))
        db.add(DraftDecision(user_id=user_id,clip_id=clip.id,version=1,decision='approved',note='Controlled approval fixture.'))
        credentials={'access_token':'test-access','refresh_token':'test-refresh','expires_at':time.time()+300}
        account=ConnectedAccount(user_id=user_id,platform='tiktok',external_id='open-id',name='Test Creator',encrypted_credentials=social.cipher().encrypt(json.dumps(credentials).encode()).decode(),scopes=['user.info.basic','video.list','video.publish'])
        db.add(account);db.commit();return clip.id,account.id


def test_tiktok_oauth_state_single_use_and_encrypted_credentials(environment,monkeypatch):
    client,factory,config=environment;register(client);setup_social(monkeypatch)
    def handler(request):
        if request.url.path.endswith('/oauth/token/'):
            return httpx.Response(200,json={'access_token':'sensitive-test-token','refresh_token':'test-refresh','open_id':'open-id','scope':'user.info.basic,video.list','expires_in':3600})
        return httpx.Response(200,json={'data':{'user':{'open_id':'open-id','display_name':'Creator'}}})
    original=httpx.Client
    monkeypatch.setattr(social.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    response=client.post('/api/social/tiktok/connect');assert response.status_code==200,response.text
    state=parse_qs(urlparse(response.json()['url']).query)['state'][0]
    assert client.get('/api/social/tiktok/callback',params={'state':'wrong','code':'test'},follow_redirects=False).status_code==400
    response=client.get('/api/social/tiktok/callback',params={'state':state,'code':'test'},follow_redirects=False)
    assert response.status_code==307,response.text
    assert client.get('/api/social/tiktok/callback',params={'state':state,'code':'test'},follow_redirects=False).status_code==400
    with factory() as db:
        account=db.scalar(select(ConnectedAccount));assert 'sensitive-test-token' not in account.encrypted_credentials
    assert 'encrypted_credentials' not in client.get('/api/accounts').text


def test_tiktok_audit_consent_idempotence_and_private_confirmation(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip,account=seed_clip(factory,user['id'],config)
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/creator_info/query/'):
            return httpx.Response(200,json={'data':{'privacy_level_options':['SELF_ONLY','PUBLIC_TO_EVERYONE'],'max_video_post_duration_sec':60},'error':{'code':'ok'}})
        if request.url.path.endswith('/video/init/'):
            return httpx.Response(200,json={'data':{'publish_id':'pub-test','upload_url':'https://upload.us.tiktokapis.com/video/?token=test'},'error':{'code':'ok'}})
        if request.url.host=='upload.us.tiktokapis.com':return httpx.Response(201)
        if request.url.path.endswith('/status/fetch/'):
            return httpx.Response(200,json={'data':{'status':'PUBLISH_COMPLETE'},'error':{'code':'ok'}})
        raise AssertionError(request.url)
    original=httpx.Client
    monkeypatch.setattr(social.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    body={'account_id':account,'version':1,'explicit_authorization':True,'consent_to_music_usage':True,'privacy_level':'PUBLIC_TO_EVERYONE','brand_content_toggle':False,'brand_organic_toggle':False}
    assert client.post(f'/api/social/clips/{clip}/tiktok',json=body).status_code==403
    body['privacy_level']='SELF_ONLY';body['consent_to_music_usage']=False
    assert client.post(f'/api/social/clips/{clip}/tiktok',json=body).status_code==422
    body['consent_to_music_usage']=True
    response=client.post(f'/api/social/clips/{clip}/tiktok',json=body);assert response.status_code==200,response.text
    job_id=response.json()['id']
    assert client.post(f'/api/social/clips/{clip}/tiktok',json=body).json()['id']==job_id
    with factory() as db:
        job=db.get(PublishingJob,job_id);social.publish_tiktok(db,job)
        assert job.status=='uploaded_private'
        social.publish_tiktok(db,job)
        assert not list(db.scalars(select(PublishedPost)))
    assert calls.count('/v2/post/publish/video/init/')==1
    assert calls.count('/video/')==1


def test_approval_required_after_version_change(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip,account=seed_clip(factory,user['id'],config)
    with factory() as db:
        row=db.get(RenderedClip,clip);social.require_approved_draft(db,row)
        row.current_version=2;db.commit()
        with pytest.raises(Exception,match='Approve the current'):
            social.require_approved_draft(db,row)


def test_setup_wizard_encrypts_app_secrets_and_enables_official_connect(environment,monkeypatch,tmp_path):
    from app.services.social_settings import directory
    client,factory,config=environment;register(client)
    monkeypatch.setenv('MEDIA_ROOT',str(tmp_path/'owned-media'))
    for key in ['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','TOKEN_ENCRYPTION_KEY']:monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('FREE_MODE','true');monkeypatch.setenv('SOCIAL_INTEGRATIONS_ENABLED','false')
    response=client.post('/api/social/setup',json={'platform':'youtube','client_id':'controlled.apps.googleusercontent.com','client_secret':'controlled-secret-do-not-expose','redirect_uri':'http://localhost:3000/api/accounts/youtube/callback'})
    assert response.status_code==200,response.text
    assert response.json()['youtube_configured'] and 'controlled-secret' not in response.text
    encoded=(directory()/'app-settings.enc').read_bytes()
    assert b'controlled-secret' not in encoded
    result=client.post('/api/accounts/youtube/connect')
    assert result.status_code==200 and 'accounts.google.com' in result.json()['url']
    assert 'controlled-secret' not in result.text
    monkeypatch.setenv('APP_ENV','production')
    assert client.post('/api/social/setup',json={'platform':'youtube','client_id':'another-controlled','redirect_uri':'http://localhost:3000/callback'}).status_code==403
