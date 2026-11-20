import pytest
from app.services.url_import import validate_youtube_url
from app.services.media import PipelineError


@pytest.mark.parametrize('value',['http://youtube.com/watch?v=abc','https://127.0.0.1/private','https://youtube.com.evil.example/watch?v=x','https://user:secret@youtube.com/watch?v=x','https://youtube.com/channel/private','https://youtube.com:444/watch?v=x'])
def test_import_rejects_unapproved_destinations_and_credentials(value):
    with pytest.raises(PipelineError):validate_youtube_url(value)


def test_public_single_video_url_remains_exact():
    value='https://www.youtube.com/watch?v=abcdef12345'
    assert validate_youtube_url(value)==value


def test_downloader_is_bounded_and_preserves_original_title(monkeypatch,tmp_path):
    from app.services.url_import import import_youtube
    import yt_dlp
    class ControlledDownloader:
        def __init__(self,options):
            assert options['noplaylist'] and options['max_filesize']==1024
            assert not any(key in options for key in ['cookiefile','username','password'])
            self.options=options
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def extract_info(self,url,download):
            (tmp_path/'source.mp4').write_bytes(b'Controlled download fixture')
            self.options['progress_hooks'][0]({'downloaded_bytes':27})
            return {'title':'Authorized controlled fixture'}
    monkeypatch.setattr(yt_dlp,'YoutubeDL',ControlledDownloader)
    path,title=import_youtube('https://youtu.be/abcdef12345',tmp_path,1024)
    assert path.name=='source.mp4' and title=='Authorized controlled fixture'
