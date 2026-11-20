"""Optional bounded import of a user-authorized public YouTube video."""
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .media import PipelineError
import time


def validate_youtube_url(value):
    try:
        parsed=urlparse(value)
        port=parsed.port
    except ValueError as exc:raise PipelineError('Use a valid public HTTPS YouTube video URL.') from exc
    if parsed.scheme!='https' or parsed.username or parsed.password or port not in (None,443):raise PipelineError('Use a public HTTPS YouTube video URL without credentials.')
    if parsed.hostname not in {'youtube.com','www.youtube.com','m.youtube.com','youtu.be'}:raise PipelineError('URL import currently supports authorized public YouTube videos only.')
    if parsed.hostname!='youtu.be' and not (parsed.path=='/watch' and parse_qs(parsed.query).get('v') or parsed.path.startswith('/shorts/')):raise PipelineError('Paste a single YouTube video, not a channel or playlist.')
    return value


def import_youtube(value,directory,max_bytes):
    validate_youtube_url(value)
    try:import yt_dlp
    except ImportError as exc:raise PipelineError('Install the optional local analysis dependencies to enable YouTube import.') from exc
    deadline=time.monotonic()+600
    def bound(progress):
        if time.monotonic()>deadline:raise PipelineError('URL import timed out. Upload your authorized local file instead.')
        if (progress.get('downloaded_bytes') or 0)>max_bytes:raise PipelineError('Video exceeds the local import size limit.')
    options={'format':'best[ext=mp4][height<=1080]/best[height<=1080]','outtmpl':str(Path(directory)/'source.%(ext)s'),
        'noplaylist':True,'max_filesize':max_bytes,'socket_timeout':30,'retries':1,
        'quiet':True,'no_warnings':True,'restrictfilenames':True,'progress_hooks':[bound]}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:info=downloader.extract_info(value,download=True)
    except PipelineError:raise
    except Exception as exc:raise PipelineError('YouTube import failed. The video may require permission, be restricted, or need an updated local downloader. Upload your authorized local file instead.') from exc
    files=[p for p in Path(directory).glob('source.*') if p.suffix in {'.mp4','.webm','.mkv','.mov'}]
    if len(files)!=1 or files[0].stat().st_size>max_bytes:raise PipelineError('No supported video was downloaded within the import limit.')
    return files[0],str((info or {}).get('title') or 'YouTube video')[:200]
