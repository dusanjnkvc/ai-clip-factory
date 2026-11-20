"""Upgrade the old schema with an existing record, not just an empty database."""
import os,sqlite3,subprocess,sys
from pathlib import Path


def test_existing_data_survives_studio_migration(tmp_path):
    backend=Path(__file__).resolve().parents[1]
    target=tmp_path/'existing.db'
    env={**os.environ,'DATABASE_URL':'sqlite:///'+str(target).replace('\\','/'),'MEDIA_ROOT':str(tmp_path/'media'),'APP_ENV':'test'}
    def migrate(revision):
        subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=backend,env=env,check=True,capture_output=True,text=True)
    migrate('805028d08678')
    with sqlite3.connect(target) as db:
        db.execute('INSERT INTO users (id,created_at,email,name,password_hash,preferences) VALUES (?,?,?,?,?,?)',
            ('preserved-owner','2026-11-01','existing@example.invalid','Existing creator','not-a-real-password','{}'))
    migrate('head')
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT name FROM users WHERE id=?',('preserved-owner',)).fetchone()==('Existing creator',)
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'factory_projects','reference_styles','draft_evaluations','draft_decisions','platform_observations','account_observations'}<=tables
