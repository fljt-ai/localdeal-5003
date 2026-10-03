"""Initialize new demo data and migrate existing v1 files without resetting data."""
from datetime import datetime
from pathlib import Path

from database import init_db, operations
from .auth import DEMO_PASSWORD, hash_password

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'database/localdeal.db'
DEMO_EMAILS = {
    'u-demo': 'alex@example.com', 'u-amy': 'amy@example.com',
    'u-ming': 'ming@example.com', 'u-joyce': 'joyce@example.com',
    'u-ken': 'ken@example.com', 'u-wai': 'wai@example.com',
    'u-harbor': 'harbor.owner@example.com',
    'u-dumpling': 'dumpling.owner@example.com', 'u-coffee': 'coffee.owner@example.com',
}


def initialize_database(path=DEFAULT_DB):
    path = Path(path).resolve()
    if not path.exists():
        init_db.create_database(path, datetime.now(init_db.HK).date())
    connection = operations.connect(path)
    try:
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if version not in (1, 2):
            raise RuntimeError('Unsupported database version; existing file preserved')
        if version == 1:
            # Derive credentials before taking the write lock, but only fill NULL
            # hashes for the exact fictional seed identities during migration.
            hashes = [(hash_password(DEMO_PASSWORD), uid, email) for uid, email in DEMO_EMAILS.items()]
            connection.execute('BEGIN IMMEDIATE')
            try:
                script = (ROOT / 'database/migration_v2.sql').read_text(encoding='utf-8')
                # executescript would implicitly commit the surrounding transaction.
                # Execute complete statements individually so migration is atomic.
                statement = ''
                import sqlite3
                for line in script.splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ''
                for encoded, user_id, email in hashes:
                    connection.execute('UPDATE users SET password_hash = ? '
                                       'WHERE user_id = ? AND email = ? AND password_hash IS NULL',
                                       (encoded,user_id,email))
                connection.execute('COMMIT')
            except BaseException:
                connection.execute('ROLLBACK')
                raise
        if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Database integrity check failed')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Database contains foreign-key violations')
    finally:
        connection.close()
    return path
