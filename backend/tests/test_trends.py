from datetime import datetime, timezone, timedelta
import httpx
from app.services.trends import TrendResearch


def test_missing_key_never_requests_network(monkeypatch, tmp_path):
    monkeypatch.delenv('YOUTUBE_DATA_API_KEY', raising=False)
    result=TrendResearch(tmp_path/'cache.db', httpx.MockTransport(lambda r: (_ for _ in ()).throw(AssertionError()))).research('Warzone')
    assert result['status']=='unavailable' and result['sources']==[]


def test_public_dates_urls_cache_and_persistent_quota(monkeypatch,tmp_path):
    monkeypatch.setenv('YOUTUBE_DATA_API_KEY','test-only');monkeypatch.setenv('YOUTUBE_RESEARCH_DAILY_REQUEST_LIMIT','2')
    calls=[]
    def reply(request):
        assert request.headers['X-Goog-Api-Key']=='test-only'
        assert 'test-only' not in str(request.url)
        calls.append(request.url.path)
        if request.url.path.endswith('/search'): return httpx.Response(200,json={'items':[{'id':{'videoId':'abcdefghijk'}}]})
        return httpx.Response(200,json={'items':[{'id':'abcdefghijk','snippet':{'title':'Actual public title','publishedAt':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat()},'statistics':{'viewCount':'120','likeCount':'6'}}]})
    transport=httpx.MockTransport(reply);path=tmp_path/'cache.db'
    result=TrendResearch(path,transport).research('Warzone')
    assert result['sources'][0]['url']=='https://www.youtube.com/watch?v=abcdefghijk'
    assert result['sources'][0]['likes_per_view']==.05
    assert result['classification']=='research_supported_suggestion'
    assert TrendResearch(path,transport).research('Warzone')['cached']
    assert TrendResearch(path,transport).research('Another game')['status']=='unavailable'
    assert len(calls)==2 and 'test-only' not in str(result)
