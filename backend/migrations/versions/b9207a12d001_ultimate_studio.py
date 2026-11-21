"""Add native projects, reference profiles, evaluations and approval history.

Revision ID: b9207a12d001
Revises: 805028d08678
"""
from alembic import op
from app.models import FactoryProject, ReferenceStyle, DraftEvaluation, DraftDecision, PlatformObservation

revision = 'b9207a12d001'
down_revision = '805028d08678'
branch_labels = None
depends_on = None


def upgrade():
    for model in (FactoryProject, ReferenceStyle, DraftEvaluation, DraftDecision, PlatformObservation):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    for model in (PlatformObservation, DraftDecision, DraftEvaluation, ReferenceStyle, FactoryProject):
        model.__table__.drop(op.get_bind(), checkfirst=True)
