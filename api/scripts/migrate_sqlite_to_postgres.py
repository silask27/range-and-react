from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

TABLE_ORDER = [
    'users',
    'organizations',
    'auth_tokens',
    'external_identities',
    'sessions',
    'hands',
    'hand_results',
    'assignments',
    'password_reset_tokens',
    'audit_logs',
    'organization_memberships',
    'signup_invite_batches',
    'signup_invites',
]


def _default_source_path() -> str:
    raw = os.getenv('VRT_DATABASE_PATH', '').strip()
    if raw:
        return str(Path(raw).expanduser())
    legacy = Path(__file__).resolve().parents[2] / 'data' / 'villain_range_trainer.db'
    return str(legacy)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Copy all application tables from an existing SQLite database into the configured PostgreSQL database.'
    )
    parser.add_argument('--source-path', default=_default_source_path(), help='Path to the source SQLite database file.')
    parser.add_argument('--target-url', default=os.getenv('VRT_DATABASE_URL', ''), help='Target PostgreSQL database URL.')
    parser.add_argument('--reset-target', action='store_true', help='Delete target table contents before copying data.')
    return parser.parse_args()



def _sqlite_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    return [str(row['name']) for row in rows]



def main() -> None:
    args = _parse_args()
    target_url = (args.target_url or '').strip()
    if not target_url:
        raise SystemExit('A PostgreSQL target is required. Pass --target-url or set VRT_DATABASE_URL.')

    os.environ['VRT_DATABASE_URL'] = target_url

    from api.app.storage.db import DATABASE_BACKEND, get_connection, init_db

    if DATABASE_BACKEND != 'postgresql':
        raise SystemExit('Target database must be PostgreSQL for this migration script.')

    source_path = Path(args.source_path).expanduser()
    if not source_path.exists():
        raise SystemExit(f'Source SQLite database not found: {source_path}')

    init_db()

    source_conn = sqlite3.connect(str(source_path))
    source_conn.row_factory = sqlite3.Row
    try:
        with get_connection() as target_conn:
            if args.reset_target:
                for table_name in reversed(TABLE_ORDER):
                    target_conn.execute(f'DELETE FROM {table_name}')

            for table_name in TABLE_ORDER:
                columns = _sqlite_columns(source_conn, table_name)
                if not columns:
                    continue
                rows = source_conn.execute(f'SELECT * FROM {table_name}').fetchall()
                if not rows:
                    print(f'{table_name}: 0 rows')
                    continue

                column_sql = ', '.join(columns)
                placeholders = ', '.join('?' for _ in columns)
                insert_sql = (
                    f'INSERT INTO {table_name} ({column_sql}) '
                    f'VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                )
                for row in rows:
                    target_conn.execute(insert_sql, tuple(row[column] for column in columns))
                print(f'{table_name}: {len(rows)} rows')
    finally:
        source_conn.close()

    print('SQLite → PostgreSQL migration complete.')


if __name__ == '__main__':
    main()
