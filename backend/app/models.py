import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def uid():
    return str(uuid.uuid4())

class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class User(Record, Base):
    __tablename__ = 'users'
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    campaigns: Mapped[list['Campaign']] = relationship(back_populates='user')

class Session(Record, Base):
    __tablename__ = 'sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class ConnectedAccount(Record, Base):
    __tablename__ = 'connected_accounts'
    __table_args__ = (UniqueConstraint('user_id', 'platform', 'external_id'),)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    platform: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    encrypted_credentials: Mapped[str] = mapped_column(Text)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default='connected')

class OAuthState(Record, Base):
    __tablename__ = 'oauth_states'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    state_hash: Mapped[str] = mapped_column(String(64), unique=True)
    verifier: Mapped[str] = mapped_column(String(200))
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class Campaign(Record, Base):
    __tablename__ = 'campaigns'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    user: Mapped[User] = relationship(back_populates='campaigns')
    name: Mapped[str] = mapped_column(String(250))
    brief: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='draft')
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    analysis_error: Mapped[str | None] = mapped_column(Text)
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    rule_versions: Mapped[list['CampaignRule']] = relationship(back_populates='campaign')

class CampaignRule(Record, Base):
    __tablename__ = 'campaign_rules'
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'), index=True)
    campaign: Mapped[Campaign] = relationship(back_populates='rule_versions')
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))

class SourceVideo(Record, Base):
    __tablename__ = 'source_videos'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    media_info: Mapped[dict] = mapped_column(JSON)
    rights: Mapped[list['MediaRightsRecord']] = relationship(back_populates='source')

class MediaRightsRecord(Record, Base):
    __tablename__ = 'media_rights_records'
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'), index=True)
    source: Mapped[SourceVideo] = relationship(back_populates='rights')
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    confirmed: Mapped[bool] = mapped_column(Boolean)
    note: Mapped[str] = mapped_column(Text)

class Transcript(Record, Base):
    __tablename__ = 'transcripts'
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'), unique=True)
    content: Mapped[dict] = mapped_column(JSON)
    provider: Mapped[str] = mapped_column(String(100))

class ProcessingJob(Record, Base):
    __tablename__ = 'processing_jobs'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'))
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(200), default='Waiting for worker')
    progress: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(20), default='fast')
    clip_count: Mapped[int] = mapped_column(Integer, default=1)
    completed_clips: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)
    rules_snapshot: Mapped[dict] = mapped_column(JSON)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_reservation: Mapped[float] = mapped_column(Float, default=0)
    first_clip_seconds: Mapped[float | None] = mapped_column(Float)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

class ClipCandidate(Record, Base):
    __tablename__ = 'clip_candidates'
    job_id: Mapped[str] = mapped_column(ForeignKey('processing_jobs.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'))
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    scores: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)

class EditingPlan(Record, Base):
    __tablename__ = 'editing_plans'
    candidate_id: Mapped[str] = mapped_column(ForeignKey('clip_candidates.id'))
    plan: Mapped[dict] = mapped_column(JSON)
    rules_snapshot: Mapped[dict] = mapped_column(JSON)

class RenderedClip(Record, Base):
    __tablename__ = 'rendered_clips'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('processing_jobs.id'), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'))
    editing_plan_id: Mapped[str] = mapped_column(ForeignKey('editing_plans.id'))
    title: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str] = mapped_column(Text)
    media_info: Mapped[dict] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    edit_dna: Mapped[dict] = mapped_column(JSON)
    compliance: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default='review')
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    draft_approved: Mapped[bool] = mapped_column(Boolean, default=False)

class ClipVersion(Record, Base):
    __tablename__ = 'clip_versions'
    __table_args__ = (UniqueConstraint('clip_id', 'version'),)
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    plan: Mapped[dict] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    storage_key: Mapped[str] = mapped_column(Text)

class ComplianceCheck(Record, Base):
    __tablename__ = 'compliance_checks'
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    checks: Mapped[list] = mapped_column(JSON)
    rules_snapshot: Mapped[dict] = mapped_column(JSON)

class PublishingJob(Record, Base):
    __tablename__ = 'publishing_jobs'
    __table_args__ = (UniqueConstraint('clip_id', 'platform', 'version'),)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'))
    account_id: Mapped[str] = mapped_column(ForeignKey('connected_accounts.id'))
    platform: Mapped[str] = mapped_column(String(30))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    attended: Mapped[bool] = mapped_column(Boolean, default=True)
    privacy: Mapped[str] = mapped_column(String(20), default='private')
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    authorization_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    upload_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    upload_lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    upload_state: Mapped[dict] = mapped_column(JSON, default=dict)

class PublishedPost(Record, Base):
    __tablename__ = 'published_posts'
    __table_args__ = (UniqueConstraint('user_id', 'url'),)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'))
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    platform: Mapped[str] = mapped_column(String(30))
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    provenance: Mapped[str] = mapped_column(String(30))

class CampaignSubmission(Record, Base):
    __tablename__ = 'campaign_submissions'
    post_id: Mapped[str] = mapped_column(ForeignKey('published_posts.id'), unique=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    status: Mapped[str] = mapped_column(String(30), default='pending')
    submission_url: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime | None] = mapped_column(DateTime)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirmation: Mapped[str | None] = mapped_column(Text)

class AnalyticsSnapshot(Record, Base):
    __tablename__ = 'analytics_snapshots'
    post_id: Mapped[str] = mapped_column(ForeignKey('published_posts.id'), index=True)
    reported_views: Mapped[int] = mapped_column(Integer, default=0)
    eligible_views: Mapped[int | None] = mapped_column(Integer)
    likes: Mapped[int | None] = mapped_column(Integer)
    shares: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[str] = mapped_column(String(100))

class EarningsRecord(Record, Base):
    __tablename__ = 'earnings_records'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default='USD')
    kind: Mapped[str] = mapped_column(String(20))
    provenance: Mapped[str] = mapped_column(Text)

class ProcessingCost(Record, Base):
    __tablename__ = 'processing_costs'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey('processing_jobs.id'))
    amount: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(20), default='reported')
    provider: Mapped[str] = mapped_column(String(100))

class AuditLog(Record, Base):
    __tablename__ = 'audit_logs'
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    action: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class FactoryProject(Record, Base):
    __tablename__ = 'factory_projects'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(200))
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'))
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey('campaigns.id'))
    job_id: Mapped[str | None] = mapped_column(ForeignKey('processing_jobs.id'))
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    reference_ids: Mapped[list] = mapped_column(JSON, default=list)


class ReferenceStyle(Record, Base):
    __tablename__ = 'reference_styles'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('source_videos.id'))
    name: Mapped[str] = mapped_column(String(200))
    profile: Mapped[dict] = mapped_column(JSON)


class DraftEvaluation(Record, Base):
    __tablename__ = 'draft_evaluations'
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    evaluation: Mapped[dict] = mapped_column(JSON)


class DraftDecision(Record, Base):
    __tablename__ = 'draft_decisions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    clip_id: Mapped[str] = mapped_column(ForeignKey('rendered_clips.id'), index=True)
    version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)


class PlatformObservation(Record, Base):
    __tablename__ = 'platform_observations'
    post_id: Mapped[str] = mapped_column(ForeignKey('published_posts.id'), index=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    provenance: Mapped[str] = mapped_column(String(120))
