"""Preserve timestamped account-level audience observations."""
from alembic import op
from app.models import AccountObservation
revision='c730ea230002'
down_revision='b9207a12d001'
branch_labels=None
depends_on=None

def upgrade():AccountObservation.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():AccountObservation.__table__.drop(op.get_bind(),checkfirst=True)
