import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse
from collections import defaultdict, deque
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import Session, User, now
from .config import settings
from .runtime import local_no_auth
from sqlalchemy.exc import IntegrityError

COOKIE = 'acf_session'
_attempts = defaultdict(deque)

def hash_password(password: str) -> str:
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(422, 'Use a password with 12–256 characters.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'

def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split('$')
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def rate_limit(key: str, limit=15, seconds=60):
    queue = _attempts[key]
    current = time.monotonic()
    while queue and current - queue[0] > seconds:
        queue.popleft()
    if len(queue) >= limit:
        raise HTTPException(429, 'Too many attempts. Try again shortly.')
    queue.append(current)

def create_session(db, user, response):
    raw = secrets.token_urlsafe(32)
    db.add(Session(user_id=user.id, token_hash=token_hash(raw), expires_at=now() + timedelta(days=7)))
    db.commit()
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.production, samesite='lax', max_age=604800, path='/')

def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    if local_no_auth():
        return local_workspace_user(request,db)
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, 'Sign in to continue.')
    session = db.scalar(select(Session).where(Session.token_hash == token_hash(raw), Session.expires_at > now()))
    if not session:
        raise HTTPException(401, 'Your session has expired. Sign in again.')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Sign in to continue.')
    return user


def local_workspace_user(request,db):
    # Preserve the current local user's campaigns when switching off login.
    users=list(db.scalars(select(User).order_by(User.created_at)))
    existing=next((u for u in users if u.preferences.get('local_workspace_owner') is True),None)
    if existing:
        return existing
    raw=request.cookies.get(COOKIE)
    session=db.scalar(select(Session).where(Session.token_hash==token_hash(raw),Session.expires_at>now())) if raw else None
    user=db.get(User,session.user_id) if session else users[0] if users else None
    if user is None:
        user=User(id='local-workspace',email='local-workspace@localhost.invalid',name='Local workspace',password_hash='!local-workspace-no-password',preferences={'local_workspace_owner':True})
        db.add(user)
    else:
        user.preferences={**user.preferences,'local_workspace_owner':True}
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user=db.get(User,'local-workspace')
        if user is None:
            raise
    return user

def check_origin(request: Request):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        permitted = {settings.frontend_url, settings.api_base_url, str(request.base_url).rstrip('/')}
        if not settings.production:
            frontend = urlparse(settings.frontend_url)
            if frontend.hostname in {'localhost', '127.0.0.1', '::1'}:
                permitted.update(f'{frontend.scheme}://{host}:{frontend.port or 3000}' for host in ('localhost', '127.0.0.1', '[::1]'))
        if origin and origin.rstrip('/') not in permitted:
            raise HTTPException(403, 'Request origin is not allowed.')
        # JSON and custom header requests cannot be forged by HTML forms. Multipart
        # requests from browsers always include Origin and are checked above.
        if not origin and request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'Cross-site requests are not allowed.')

def audit(db, user_id, action, entity_id=None, **detail):
    from .models import AuditLog
    db.add(AuditLog(user_id=user_id, action=action, entity_id=entity_id, detail=detail))
