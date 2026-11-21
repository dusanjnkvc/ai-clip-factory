from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///./data/factory.db')
    media_root: Path = Path(os.getenv('MEDIA_ROOT', './data/media')).resolve()
    frontend_url: str = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    api_base_url: str = os.getenv('API_BASE_URL', 'http://localhost:8000').rstrip('/')
    secret: str = os.getenv('APP_SECRET', '')
    production: bool = os.getenv('APP_ENV', 'development') == 'production'
    max_upload_mb: int = int(os.getenv('MAX_UPLOAD_MB', '1500'))
    monthly_limit: float = float(os.getenv('MONTHLY_SPEND_LIMIT_USD', '25'))
    max_job_cost: float = float(os.getenv('MAX_JOB_COST_USD', '2'))
    retention_days: int = int(os.getenv('RETENTION_DAYS', '30'))

    def validate(self):
        if self.production and len(self.secret) < 32:
            raise RuntimeError('Production requires APP_SECRET with at least 32 characters.')
        self.media_root.mkdir(parents=True, exist_ok=True)


settings = Settings()
