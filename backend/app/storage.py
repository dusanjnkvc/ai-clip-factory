import hashlib
import hmac
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from .config import settings

def local_path(key: str) -> Path:
    path = (settings.media_root / key).resolve()
    if settings.media_root not in path.parents:
        raise ValueError('Invalid storage key')
    return path

def s3_client():
    import boto3
    return boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT') or None, region_name=os.getenv('S3_REGION', 'us-east-1'))

def put_file(path: Path, key: str):
    if os.getenv('S3_BUCKET'):
        s3_client().upload_file(str(path), os.environ['S3_BUCKET'], key, ExtraArgs={'ServerSideEncryption': 'AES256'})
    else:
        dest = local_path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.resolve() != dest:
            shutil.copyfile(path, dest)

def delete_file(key: str):
    if os.getenv('S3_BUCKET'):
        s3_client().delete_object(Bucket=os.environ['S3_BUCKET'], Key=key)
    else:
        local_path(key).unlink(missing_ok=True)

@contextmanager
def materialize(key: str):
    if not os.getenv('S3_BUCKET'):
        path = local_path(key)
        if not path.is_file():
            raise FileNotFoundError('Media is no longer available.')
        yield path
        return
    with tempfile.TemporaryDirectory(prefix='acf-media-') as temp:
        target = Path(temp) / Path(key).name
        s3_client().download_file(os.environ['S3_BUCKET'], key, str(target))
        yield target

def signed_url(key: str, expires=900) -> str | None:
    if os.getenv('S3_BUCKET'):
        return s3_client().generate_presigned_url('get_object', Params={'Bucket': os.environ['S3_BUCKET'], 'Key': key}, ExpiresIn=expires)
    return None

def download_token(clip_id: str, user_id: str, expires: int) -> str:
    if not settings.secret:
        raise ValueError('APP_SECRET must be configured to create signed download links.')
    return hmac.new(settings.secret.encode(), f'{clip_id}:{user_id}:{expires}'.encode(), hashlib.sha256).hexdigest()

def verify_download_token(clip_id, user_id, expires, signature):
    if expires < int(time.time()) or expires > int(time.time()) + 3600:
        return False
    try:
        return hmac.compare_digest(download_token(clip_id, user_id, expires), signature)
    except ValueError:
        return False
