"""Explicit, fail-safe selection of the no-service-fee local workflow."""
import os
from urllib.parse import urlparse


def free_mode() -> bool:
    # An absent or misspelled setting must never enable billable operations.
    return os.getenv('FREE_MODE', 'true').strip().lower() not in {'false', '0', 'no', 'off'}


def social_enabled() -> bool:
    # Independent of paid inference. Disabled until the operator opts in.
    from .services.social_settings import value
    return not free_mode() or value('SOCIAL_INTEGRATIONS_ENABLED','false').lower()=='true'


def local_no_auth() -> bool:
    if not free_mode() or os.getenv('APP_ENV','development') == 'production':
        return False
    if os.getenv('LOCAL_NO_AUTH','true').strip().lower() in {'false','0','no','off'}:
        return False
    # This convenience is restricted to the loopback local deployment.
    return all(urlparse(os.getenv(key,default)).hostname in {'localhost','127.0.0.1','::1'} for key,default in (
        ('FRONTEND_URL','http://localhost:3000'),('API_BASE_URL','http://localhost:8000')))


def create_pipeline_service():
    if free_mode():
        from .services.local import LocalPipelineService
        return LocalPipelineService()
    from .services.pipeline import PipelineService
    return PipelineService()
