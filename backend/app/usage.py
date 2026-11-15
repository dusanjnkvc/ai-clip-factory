"""Persist provider-reported usage without guessing monetary charges."""
from .models import AuditLog


def record_usage(db, service, user_id, job_id=None):
    for entry in service.usage:
        db.add(AuditLog(user_id=user_id, action='ai.usage', entity_id=job_id,
                        detail=entry))
    service.usage.clear()
