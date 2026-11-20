from datetime import datetime,timedelta,date
import httpx
from test_backend import environment,register
from test_social import setup_social,seed_clip
from app.models import PublishedPost,PlatformObservation,ConnectedAccount,User
from app import performance


def seed_post(factory,user,clip,url='https://www.youtube.com/watch?v=abcdef12345'):
    from app.models import RenderedClip
    with factory() as db:
        row=db.get(RenderedClip,clip)
        post=PublishedPost(user_id=user,clip_id=clip,campaign_id=row.campaign_id,platform='youtube',url=url,
            published_at=datetime.utcnow()-timedelta(days=10),provenance='controlled_import_fixture')
        db.add(post);db.commit();return post.id


def test_lifetime_is_never_reported_as_date_range_and_missing_metrics_stay_null(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip,_=seed_clip(factory,user['id'],config);post=seed_post(factory,user['id'],clip)
    response=client.post(f'/api/performance/posts/{post}/observations',json={'views':1000,'likes':20,'provenance':'User exported real count fixture.'})
    assert response.status_code==200,response.text
    report=client.get('/api/performance/dashboard').json()
    assert report['lifetime_views']==1000 and report['period_views'] is None
    assert report['posts'][0]['lifetime']['comments'] is None
    assert report['posts'][0]['engagement_components']==['likes']
    today=str(date.today())
    client.post(f'/api/performance/posts/{post}/observations',json={'basis':'daily','date':today,'views':12,'provenance':'Controlled daily report fixture.'})
    client.post(f'/api/performance/posts/{post}/observations',json={'basis':'daily','date':today,'views':15,'provenance':'New corrected daily report fixture.'})
    report=client.get('/api/performance/dashboard').json()
    assert report['period_views']==15 and report['lifetime_views']==1000
    assert report['daily_views']==[{'date':today,'views':15}]
    profile=client.get('/api/performance/learning').json()
    assert profile['status']=='insufficient_data' and profile['sample_count']==1
    assert client.post('/api/performance/learning/reset').json()['sample_count']==0


def test_youtube_sync_separates_lifetime_and_authorized_daily_reports(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip,account=seed_clip(factory,user['id'],config);seed_post(factory,user['id'],clip)
    with factory() as db:
        row=db.get(ConnectedAccount,account);row.platform='youtube';row.external_id='channel-id';row.scopes=['https://www.googleapis.com/auth/yt-analytics.readonly'];db.commit()
    monkeypatch.setattr(performance,'access_token',lambda *a:'controlled-test-token')
    def handler(request):
        if request.url.path.endswith('/channels'):
            return httpx.Response(200,json={'items':[{'id':'channel-id','statistics':{'subscriberCount':'1200','viewCount':'5000','hiddenSubscriberCount':False}}]})
        if request.url.host=='www.googleapis.com':
            return httpx.Response(200,json={'items':[{'id':'abcdef12345','snippet':{'channelId':'channel-id'},'statistics':{'viewCount':'500','likeCount':'10'}}]})
        return httpx.Response(200,json={'columnHeaders':[{'name':'day'},{'name':'views'},{'name':'estimatedMinutesWatched'}],
            'rows':[[str(date.today()),0,0]]})
    original=httpx.Client
    monkeypatch.setattr(performance.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    result=client.post(f'/api/performance/accounts/{account}/sync',json={'start':str(date.today()-timedelta(days=7)),'end':str(date.today())})
    assert result.status_code==200,result.text
    report=client.get('/api/performance/dashboard').json()
    assert report['lifetime_views']==500 and report['period_views']==0
    assert report['posts'][0]['lifetime']['shares'] is None
    assert report['posts'][0]['period'][0]['watch_minutes']==0
    assert report['account_audience'][0]['total']==1200
    assert report['account_audience'][0]['growth'] is None


def test_account_growth_and_post_windows_require_actual_coverage(environment,monkeypatch):
    from app.models import AccountObservation,RenderedClip
    from sqlalchemy import select
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    clip,account=seed_clip(factory,user['id'],config);post=seed_post(factory,user['id'],clip)
    today=date.today();start=today-timedelta(days=7)
    with factory() as db:
        db.add(AccountObservation(account_id=account,user_id=user['id'],platform='tiktok',metrics={'audience':100},provenance='controlled',created_at=datetime.combine(start,datetime.min.time())))
        db.add(AccountObservation(account_id=account,user_id=user['id'],platform='tiktok',metrics={'audience':108},provenance='controlled',created_at=datetime.utcnow()))
        published=db.get(PublishedPost,post).published_at.date()
        for day in range(7):
            db.add(PlatformObservation(post_id=post,metrics={'basis':'daily','date':str(published+timedelta(days=day)),'views':day,'likes':0,'watch_minutes':0},provenance='controlled'))
        db.commit()
    report=client.get('/api/performance/dashboard',params={'start':str(today-timedelta(days=29)),'end':str(today),'clip_id':clip}).json()
    row=report['posts'][0]
    assert row['publication_windows']['7_calendar_days']['views']==21
    assert row['publication_windows']['30_calendar_days']['views'] is None
    assert row['first_24h_views'] is None and row['retention'] is None and row['reported_watch_minutes']==0
    report=client.get('/api/performance/dashboard',params={'start':str(start),'end':str(today)}).json()
    assert report['account_audience'][0]['growth']==8
    assert not client.get('/api/performance/dashboard',params={'clip_id':'unrelated-owned-or-missing'}).json()['posts']


def test_idle_sync_failure_is_persisted_and_backed_off(environment,monkeypatch):
    client,factory,config=environment;user=register(client);setup_social(monkeypatch)
    _,account=seed_clip(factory,user['id'],config);calls=[]
    def unavailable(*args):calls.append(True);raise RuntimeError('Controlled provider outage')
    monkeypatch.setattr(performance,'sync_account',unavailable)
    with factory() as db:
        assert performance.sync_idle_account(db)
        assert not performance.sync_idle_account(db)
        saved=db.get(User,user['id']).preferences['analytics_sync_'+account]
        assert saved['status']=='failed' and 'Controlled provider outage' not in str(saved)
    assert len(calls)==1
