"""Single-user OAuth app settings, encrypted outside the media serving root."""
import json,os
from pathlib import Path
from cryptography.fernet import Fernet

FIELDS={'YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REDIRECT_URI','TIKTOK_CLIENT_KEY','TIKTOK_CLIENT_SECRET','TIKTOK_REDIRECT_URI','TIKTOK_SCOPES','TOKEN_ENCRYPTION_KEY','SOCIAL_INTEGRATIONS_ENABLED'}

def directory():return Path(os.getenv('MEDIA_ROOT','./data/media')).resolve().parent/'private-social'

def stored():
    folder=directory();path=folder/'app-settings.enc';key=folder/'app-settings.key'
    if not path.exists():return {}
    return json.loads(Fernet(key.read_bytes()).decrypt(path.read_bytes()))

def value(name,default=None):
    if name not in FIELDS:return os.getenv(name,default)
    return stored().get(name) or os.getenv(name) or default

def save(values):
    folder=directory();folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=folder/'app-settings.key'
    if not key.exists():
        with key.open('xb') as stream:stream.write(Fernet.generate_key())
        key.chmod(0o600)
    current=stored()
    current.update({k:v.strip() for k,v in values.items() if k in FIELDS and v.strip()})
    current.setdefault('TOKEN_ENCRYPTION_KEY',os.getenv('TOKEN_ENCRYPTION_KEY') or Fernet.generate_key().decode())
    current['SOCIAL_INTEGRATIONS_ENABLED']='true'
    target=folder/'app-settings.enc';temporary=folder/'app-settings.pending'
    temporary.write_bytes(Fernet(key.read_bytes()).encrypt(json.dumps(current).encode()));temporary.chmod(0o600);temporary.replace(target)
