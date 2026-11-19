"""Actual observations, date-range reports and descriptive local learning."""
from collections import defaultdict
from datetime import date,datetime,timedelta
from datetime import timezone
import csv,json,io
from datetime import date as CalendarDate
from statistics import median
from urllib.parse import parse_qs,urlparse
import re
import httpx
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .security import current_user,rate_limit
from .models import User,PublishedPost,PlatformObservation,AnalyticsSnapshot,RenderedClip,EditingPlan,now
from .social import account_owned,tiktok_token,tiktok_request
from .publishing import access_token
from .runtime import social_enabled

router=APIRouter(prefix='/api/performance',tags=['Actual performance'])


def metric(value):
    try:
        parsed=float(value)
        return parsed if 0<=parsed<1e15 else None
    except (ValueError,TypeError):return None


def video_id(post):
    parsed=urlparse(post.url)
    if post.platform=='youtube':
        value=parse_qs(parsed.query).get('v',[None])[0] if parsed.hostname!='youtu.be' else parsed.path.strip('/')
        if not value and '/shorts/' in parsed.path:value=parsed.path.split('/shorts/',1)[1].split('/')[0]
        return value if value and re.fullmatch(r'[A-Za-z0-9_-]{6,20}',value) else None
    match=re.search(r'/video/(\d+)',parsed.path)
    return match[1] if match else None


class ObservationInput(BaseModel):
    basis: str=Field(default='lifetime',pattern='^(lifetime|daily)$')
    date: CalendarDate | None=None
    views: int | None=Field(default=None,ge=0)
    likes: int | None=Field(default=None,ge=0)
    comments: int | None=Field(default=None,ge=0)
    shares: int | None=Field(default=None,ge=0)
    watch_minutes: float | None=Field(default=None,ge=0,allow_inf_nan=False)
    average_view_seconds: float | None=Field(default=None,ge=0,allow_inf_nan=False)
    provenance: str=Field(min_length=8,max_length=120)
    observed_at: datetime | None=None

    @model_validator(mode='after')
    def daily_date(self):
        if self.basis=='daily' and self.date is None:raise ValueError('Daily metrics need their actual date.')
        if self.date and self.date>date.today():raise ValueError('Future performance cannot be imported.')
        if self.observed_at and (self.observed_at.tzinfo is None or self.observed_at>datetime.now(timezone.utc)):
            raise ValueError('Observation times must have a timezone and cannot be in the future.')
        return self


@router.post('/posts/{post_id}/observations')
def import_observation(post_id: str,body: ObservationInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    post=db.get(PublishedPost,post_id)
    if not post or post.user_id!=user.id:raise HTTPException(404,'Published post not found.')
    values=body.model_dump(mode='json',exclude={'provenance','observed_at'})
    row=PlatformObservation(post_id=post.id,metrics=values,provenance=body.provenance)
    if body.observed_at:row.created_at=body.observed_at.astimezone(timezone.utc).replace(tzinfo=None)
    db.add(row);db.commit();return {'id':row.id,'metrics':values}


@router.post('/import')
def import_file(file: UploadFile=File(...),user: User=Depends(current_user),db: Session=Depends(get_db)):
    raw=file.file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise HTTPException(413,'Analytics imports are limited to2 MB.')
    try:
        text=raw.decode('utf-8-sig')
        rows=json.loads(text) if (file.filename or '').lower().endswith('.json') else list(csv.DictReader(io.StringIO(text)))
        if not isinstance(rows,list) or len(rows)>1000:raise ValueError('Use an array/table of at most1000 observations.')
        prepared=[];ignored=set()
        posts=list(db.scalars(select(PublishedPost).where(PublishedPost.user_id==user.id)))
        for record in rows:
            if not isinstance(record,dict):raise ValueError('Each observation must be an object/CSV row.')
            post=next((p for p in posts if p.id==record.get('post_id') or p.url==record.get('url') or
                record.get('video_id') and video_id(p)==record.get('video_id') and p.platform==record.get('platform')),None)
            if not post:raise ValueError('Each row needs your recorded post_id, url, or video_id and platform.')
            ignored.update(set(record)-set(ObservationInput.model_fields)-{'post_id','url','video_id','platform'})
            values={k:(None if v=='' else v) for k,v in record.items() if k in ObservationInput.model_fields}
            values.setdefault('provenance','User-imported '+(file.filename or 'metrics'))
            parsed=ObservationInput.model_validate(values)
            row=PlatformObservation(post_id=post.id,metrics=parsed.model_dump(mode='json',exclude={'provenance','observed_at'}),provenance=parsed.provenance)
            if parsed.observed_at:row.created_at=parsed.observed_at.astimezone(timezone.utc).replace(tzinfo=None)
            prepared.append(row)
    except (ValueError,UnicodeError,TypeError) as exc:
        raise HTTPException(422,'Invalid analytics import: '+str(exc)[:400]) from exc
    db.add_all(prepared);db.commit();return {'imported':len(prepared),'ignored_columns':sorted(ignored)}


class SyncInput(BaseModel):
    start: date
    end: date

    @model_validator(mode='after')
    def ordered(self):
        if self.start>self.end or (self.end-self.start).days>365 or self.end>date.today():
            raise ValueError('Choose an ordered, non-future reporting period of at most366 days.')
        return self


@router.post('/accounts/{account_id}/sync')
def sync_account(account_id: str,body: SyncInput,user: User=Depends(current_user),db: Session=Depends(get_db)):
    if not social_enabled():raise HTTPException(503,'Enable optional social integrations before syncing.')
    rate_limit('analytics-sync:'+user.id,limit=20,seconds=3600)
    account=account_owned(db,account_id,user)
    posts=list(db.scalars(select(PublishedPost).where(PublishedPost.user_id==user.id,PublishedPost.platform==account.platform).order_by(PublishedPost.published_at.desc()).limit(20)))
    mapped={video_id(p):p for p in posts if video_id(p)}
    if not mapped:return {'synced':0,'unavailable':['No supported published video IDs are recorded.']}
    warnings=[];count=0
    if account.platform=='youtube':
        token=access_token(db,account)
        with httpx.Client(timeout=60,follow_redirects=False,trust_env=False) as client:
            response=client.get('https://www.googleapis.com/youtube/v3/videos',params={'part':'snippet,statistics','id':','.join(mapped)},headers={'Authorization':'Bearer '+token})
            response.raise_for_status()
            for item in response.json().get('items',[]):
                post=mapped.get(item.get('id'))
                if not post or item.get('snippet',{}).get('channelId')!=account.external_id:continue
                stats=item.get('statistics',{})
                values={'basis':'lifetime','views':metric(stats.get('viewCount')),'likes':metric(stats.get('likeCount')),
                    'comments':metric(stats.get('commentCount')),'shares':None,'watch_minutes':None,'average_view_seconds':None}
                db.add(PlatformObservation(post_id=post.id,metrics=values,provenance='youtube_data_api'));count+=1
                if 'https://www.googleapis.com/auth/yt-analytics.readonly' not in account.scopes:
                    warnings.append('Reconnect YouTube to grant Analytics read-only scope; date-range views and watch time are unavailable.');continue
                report=client.get('https://youtubeanalytics.googleapis.com/v2/reports',headers={'Authorization':'Bearer '+token},params={
                    'ids':'channel==MINE','startDate':str(body.start),'endDate':str(body.end),'dimensions':'day',
                    'filters':'video=='+item['id'],'metrics':'views,likes,comments,shares,estimatedMinutesWatched,averageViewDuration','sort':'day'})
                if report.status_code!=200:
                    warnings.append('YouTube date-range report unavailable; lifetime counts were kept separate.');continue
                report=report.json();headers=[h['name'] for h in report.get('columnHeaders',[])]
                for values in report.get('rows',[]):
                    row=dict(zip(headers,values));day=row.get('day')
                    if not day or not str(body.start)<=day<=str(body.end):continue
                    db.add(PlatformObservation(post_id=post.id,provenance='youtube_analytics_api',metrics={
                        'basis':'daily','date':day,'views':metric(row.get('views')),'likes':metric(row.get('likes')),
                        'comments':metric(row.get('comments')),'shares':metric(row.get('shares')),
                        'watch_minutes':metric(row.get('estimatedMinutesWatched')),'average_view_seconds':metric(row.get('averageViewDuration'))}))
    elif account.platform=='tiktok':
        if 'video.list' not in account.scopes:raise HTTPException(403,'Reconnect TikTok with video.list permission.')
        videos=tiktok_request('video/query/',tiktok_token(db,account),params={'fields':'id,view_count,like_count,comment_count,share_count'},json={'filters':{'video_ids':list(mapped)}}).get('videos',[])
        for item in videos:
            post=mapped.get(item.get('id'))
            if not post:continue
            db.add(PlatformObservation(post_id=post.id,provenance='tiktok_display_api',metrics={'basis':'lifetime',
                'views':metric(item.get('view_count')),'likes':metric(item.get('like_count')),'comments':metric(item.get('comment_count')),
                'shares':metric(item.get('share_count')),'watch_minutes':None,'average_view_seconds':None}));count+=1
        warnings.append('TikTok Display metrics are current lifetime snapshots; date-range views and retention are unavailable.')
    else:raise HTTPException(422,'This account has no supported analytics adapter.')
    db.commit();return {'synced':count,'unavailable':list(dict.fromkeys(warnings)),'limit':'At most20 recent recorded posts per synchronization.'}


def dashboard_data(db,user,start,end,platform=None):
    query=select(PublishedPost).where(PublishedPost.user_id==user.id)
    if platform:query=query.where(PublishedPost.platform==platform)
    posts=list(db.scalars(query));rows=[];daily=defaultdict(float);period=[]
    for post in posts:
        observations=list(db.scalars(select(PlatformObservation).where(PlatformObservation.post_id==post.id).order_by(PlatformObservation.created_at.desc())))
        latest=next((o for o in observations if o.metrics.get('basis')=='lifetime'),None)
        values=latest.metrics if latest else None
        captured=latest.created_at if latest else None
        if values is None:
            legacy=db.scalar(select(AnalyticsSnapshot).where(AnalyticsSnapshot.post_id==post.id).order_by(AnalyticsSnapshot.created_at.desc()))
            if legacy:
                values={'basis':'lifetime','views':legacy.reported_views,'likes':legacy.likes,'comments':None,'shares':legacy.shares,'watch_minutes':None,'average_view_seconds':None}
                captured=legacy.created_at
        seen=set();ranges=[]
        for observation in observations:
            m=observation.metrics;day=m.get('date')
            if m.get('basis')!='daily' or not day or day in seen or not str(start)<=day<=str(end):continue
            seen.add(day);ranges.append(m)
            if m.get('views') is not None:daily[day]+=m['views']
        period.extend(ranges)
        clip=db.get(RenderedClip,post.clip_id);plan=db.get(EditingPlan,clip.editing_plan_id).plan if clip else {}
        available=[key for key in ('likes','comments','shares') if values and values.get(key) is not None]
        rate=sum(values[k] for k in available)/values['views'] if available and values.get('views') else None
        age=max(1,(captured-post.published_at).total_seconds()/86400) if captured else None
        rows.append({'post_id':post.id,'clip_id':post.clip_id,'title':clip.title if clip else 'Recorded post','platform':post.platform,
            'url':post.url,'published_at':post.published_at.isoformat()+'Z','last_sync':captured.isoformat()+'Z' if captured else None,
            'lifetime':values,'period':ranges,'engagement_rate':round(rate,6) if rate is not None else None,
            'engagement_components':available,'views_per_day_since_publication':round(values['views']/age,2) if values and values.get('views') is not None and age else None,
            'duration':clip.media_info.get('duration') if clip else None,'style':plan.get('edit_dna',{}).get('visual_effects'),
            'hook':plan.get('hook'),'campaign_id':post.campaign_id})
    lifetime=[r['lifetime']['views'] for r in rows if r['lifetime'] and r['lifetime'].get('views') is not None]
    period_views=[m['views'] for m in period if m.get('views') is not None]
    return {'posts':rows,'lifetime_views':sum(lifetime) if lifetime else None,'period_views':sum(period_views) if period_views else None,
        'daily_views':[{'date':d,'views':v} for d,v in sorted(daily.items())],
        'range':{'start':str(start),'end':str(end)},'missing':'Missing metrics remain unavailable. Lifetime totals are not date-range views. Partial engagement rates identify which metrics were available.',
        'best_performing':sorted([r for r in rows if r['views_per_day_since_publication'] is not None],key=lambda r:r['views_per_day_since_publication'],reverse=True)[:5]}


@router.get('/dashboard')
def dashboard(start: date | None=None,end: date | None=None,platform: str | None=None,user: User=Depends(current_user),db: Session=Depends(get_db)):
    end=end or date.today();start=start or end-timedelta(days=29)
    if start>end or (end-start).days>3650 or platform not in {None,'youtube','tiktok'}:raise HTTPException(422,'Choose a valid reporting range/platform.')
    return dashboard_data(db,user,start,end,platform)


def learning_data(db,user):
    data=dashboard_data(db,user,date.today()-timedelta(days=89),date.today())
    cutoff=user.preferences.get('learning_reset_at','')
    rows=[r for r in data['posts'] if r['views_per_day_since_publication'] is not None and r['published_at']>cutoff]
    # Re-uploading one draft does not create independent training examples.
    unique={}
    for row in sorted(rows,key=lambda r:r['last_sync'] or ''):unique[(row['clip_id'],row['platform'])]=row
    rows=list(unique.values())
    if len(rows)<8:return {'status':'insufficient_data','sample_count':len(rows),'patterns':[],
        'posting_time':'Insufficient historical data for a reliable publishing-time recommendation.','limitation':'At least8 posts and3 comparable samples per group are required; descriptions are observational, not causal.'}
    groups=defaultdict(list)
    for row in rows:
        bucket='under15s' if (row['duration'] or 0)<15 else '15s_or_longer'
        for category,value in [('style',row['style']),('duration',bucket),('hook_form','question' if '?' in (row['hook'] or '') else 'statement')]:
            if value:groups[(row['platform'],category,value)].append(row['views_per_day_since_publication'])
    patterns=[{'platform':key[0],'feature':key[1],'value':key[2],'sample_count':len(values),'median_views_per_day':round(median(values),2)} for key,values in groups.items() if len(values)>=3]
    patterns.sort(key=lambda p:p['median_views_per_day'],reverse=True)
    posting='Insufficient historical data for a reliable publishing-time recommendation.'
    if len(rows)>=12:
        times=[datetime.fromisoformat(r['published_at'].replace('Z','+00:00')) for r in rows]
        if (max(times)-min(times)).days>=21:
            hours=defaultdict(list)
            for row,timestamp in zip(rows,times):hours[(row['platform'],timestamp.hour//3*3)].append(row['views_per_day_since_publication'])
            comparable=[(key,values) for key,values in hours.items() if len(values)>=3]
            if len(comparable)>=2:
                key,values=max(comparable,key=lambda item:median(item[1]))
                posting=f'Observed higher median views/day for {key[0]} posts published {key[1]:02d}:00–{key[1]+3:02d}:00 UTC ({len(values)} posts). Descriptive only; review campaign deadlines and confirm any schedule yourself.'
    return {'status':'descriptive_observations','sample_count':len(rows),'patterns':patterns,
        'posting_time':posting,
        'limitation':'Age-normalized captured lifetime views/day; no randomized comparison, causal claim or guaranteed future improvement.'}


@router.get('/learning')
def learning(user: User=Depends(current_user),db: Session=Depends(get_db)):
    return learning_data(db,user)


@router.post('/learning/reset')
def reset_learning(user: User=Depends(current_user),db: Session=Depends(get_db)):
    user.preferences={**user.preferences,'learning_reset_at':now().isoformat()+'Z'};db.commit()
    return learning_data(db,user)
