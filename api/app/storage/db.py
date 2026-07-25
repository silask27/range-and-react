from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:  # Optional until postgres support is enabled in the environment.
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover - dependency availability varies by environment.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment]

_LEGACY_DB_PATH = Path(__file__).resolve().parents[3] / 'data' / 'villain_range_trainer.db'
_DEFAULT_DB_DIR = Path(os.getenv('XDG_DATA_HOME', Path.home() / '.local' / 'share')) / 'live-range-lab'
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / 'villain_range_trainer.db'

_DATABASE_BACKEND_SQLITE = 'sqlite'
_DATABASE_BACKEND_POSTGRESQL = 'postgresql'
_POSTGRES_POOL: ConnectionPool | None = None


def _resolve_db_path() -> str:
    raw = os.getenv('VRT_DATABASE_PATH', '').strip()
    if raw:
        path = Path(raw).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    _DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)

    if not _DEFAULT_DB_PATH.exists() and _LEGACY_DB_PATH.exists():
        shutil.copy2(_LEGACY_DB_PATH, _DEFAULT_DB_PATH)

    return str(_DEFAULT_DB_PATH)


def resolve_database_url() -> str:
    raw = os.getenv('VRT_DATABASE_URL', '').strip()
    if raw:
        return raw
    path = _resolve_db_path()
    return f'sqlite:///{path}'


DATABASE_URL = resolve_database_url()


def get_database_backend(database_url: str | None = None) -> str:
    url = (database_url or DATABASE_URL).strip().lower()
    if url.startswith('postgres://') or url.startswith('postgresql://'):
        return _DATABASE_BACKEND_POSTGRESQL
    if url.startswith('sqlite://'):
        return _DATABASE_BACKEND_SQLITE
    raise RuntimeError(
        'Unsupported VRT_DATABASE_URL. Use sqlite:///absolute/path.db or postgresql://user:pass@host:5432/dbname'
    )


DATABASE_BACKEND = get_database_backend()


def _sqlite_path_from_url(database_url: str | None = None) -> str:
    url = database_url or DATABASE_URL
    prefix = 'sqlite:///'
    if not url.startswith(prefix):
        raise RuntimeError('Expected a sqlite:/// database URL')
    path = url[len(prefix):]
    if not path:
        raise RuntimeError('SQLite database path cannot be empty')
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


SQLITE_DB_PATH = _sqlite_path_from_url() if DATABASE_BACKEND == _DATABASE_BACKEND_SQLITE else None


class DatabaseConnection:
    def __init__(self, backend: str, raw_connection: Any):
        self.backend = backend
        self._raw_connection = raw_connection

    def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None):
        bound_params = tuple(params or ())
        if self.backend == _DATABASE_BACKEND_POSTGRESQL:
            return self._raw_connection.execute(_translate_sql(sql), bound_params)
        return self._raw_connection.execute(sql, bound_params)


SCHEMA_STATEMENTS: tuple[str, ...] = (
    '''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        role TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_users_role_active ON users(role, is_active)',
    '''
    CREATE TABLE IF NOT EXISTS auth_tokens (
        token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        last_used_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id)',
    '''
    CREATE TABLE IF NOT EXISTS external_identities (
        external_identity_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        external_user_id TEXT NOT NULL,
        external_email TEXT,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        UNIQUE(provider, external_user_id),
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_external_identities_user_id ON external_identities(user_id)',
    '''
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)',
    '''
    CREATE TABLE IF NOT EXISTS hands (
        hand_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_hands_user_id ON hands(user_id)',
    'CREATE INDEX IF NOT EXISTS idx_hands_session_id ON hands(session_id)',
    '''
    CREATE TABLE IF NOT EXISTS hand_results (
        hand_id TEXT PRIMARY KEY,
        user_id TEXT,
        session_id TEXT,
        scenario_id TEXT,
        villain_profile_id TEXT,
        status TEXT NOT NULL,
        street TEXT,
        ui_gate TEXT,
        hand_over INTEGER NOT NULL DEFAULT 0,
        total_live_combos INTEGER,
        started_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        ranging_score REAL,
        response_score REAL,
        overall_score REAL,
        review_flagged INTEGER NOT NULL DEFAULT 0,
        review_sent_to_coaches INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        FOREIGN KEY(hand_id) REFERENCES hands(hand_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_id ON hand_results(user_id)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_session_id ON hand_results(session_id)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_status ON hand_results(status)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_completed ON hand_results(user_id, hand_over, completed_at)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_completed_scores ON hand_results(hand_over, completed_at, user_id, scenario_id, villain_profile_id)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_completed_desc ON hand_results(user_id, hand_over, completed_at DESC)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_hand_over_updated ON hand_results(user_id, hand_over, updated_at)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_hand_over_updated ON hand_results(hand_over, updated_at)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_scenario_villain_completed ON hand_results(user_id, scenario_id, villain_profile_id, hand_over, completed_at)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_hand_over_scenario ON hand_results(user_id, hand_over, scenario_id)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_hand_over_villain ON hand_results(user_id, hand_over, villain_profile_id)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_review_queue ON hand_results(review_flagged, review_sent_to_coaches, hand_over, completed_at)',
    'CREATE INDEX IF NOT EXISTS idx_hand_results_user_review ON hand_results(user_id, review_flagged, hand_over, completed_at)',
    '''
    CREATE TABLE IF NOT EXISTS assignments (
        assignment_id TEXT PRIMARY KEY,
        created_by_user_id TEXT NOT NULL,
        target_user_id TEXT NOT NULL,
        organization_id TEXT,
        title TEXT NOT NULL,
        description TEXT,
        scenario_id TEXT,
        villain_profile_id TEXT,
        repetition_target INTEGER NOT NULL,
        minimum_overall_score REAL,
        due_at TEXT,
        status TEXT NOT NULL DEFAULT \'active\',
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_assignments_target_user_id ON assignments(target_user_id)',
    'CREATE INDEX IF NOT EXISTS idx_assignments_organization_id ON assignments(organization_id)',
    'CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status)',
    'CREATE INDEX IF NOT EXISTS idx_assignments_org_status_due ON assignments(organization_id, status, due_at)',
    'CREATE INDEX IF NOT EXISTS idx_assignments_target_status_due ON assignments(target_user_id, status, due_at)',
    '''
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        reset_token_hash TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        consumed_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id)',
    '''
    CREATE TABLE IF NOT EXISTS audit_logs (
        audit_log_id TEXT PRIMARY KEY,
        actor_user_id TEXT,
        actor_role TEXT,
        target_user_id TEXT,
        organization_id TEXT,
        action_type TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        FOREIGN KEY(actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(target_user_id) REFERENCES users(user_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON audit_logs(actor_user_id)',
    'CREATE INDEX IF NOT EXISTS idx_audit_logs_target_user_id ON audit_logs(target_user_id)',
    'CREATE INDEX IF NOT EXISTS idx_audit_logs_action_type ON audit_logs(action_type)',
    'CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)',
    'CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created ON audit_logs(organization_id, created_at)',
    '''
    CREATE TABLE IF NOT EXISTS organizations (
        organization_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        external_provider TEXT,
        external_org_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_organizations_slug ON organizations(slug)',
    '''
    CREATE TABLE IF NOT EXISTS organization_memberships (
        organization_membership_id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        membership_role TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(organization_id, user_id),
        FOREIGN KEY(organization_id) REFERENCES organizations(organization_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_org_memberships_org_id ON organization_memberships(organization_id)',
    'CREATE INDEX IF NOT EXISTS idx_org_memberships_user_id ON organization_memberships(user_id)',
    'CREATE INDEX IF NOT EXISTS idx_org_memberships_user_org ON organization_memberships(user_id, organization_id)',
    'CREATE INDEX IF NOT EXISTS idx_org_memberships_org_role_user ON organization_memberships(organization_id, membership_role, user_id)',
    '''
    CREATE TABLE IF NOT EXISTS cohorts (
        cohort_id TEXT PRIMARY KEY,
        organization_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_by_user_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(organization_id) REFERENCES organizations(organization_id) ON DELETE CASCADE,
        FOREIGN KEY(created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_cohorts_org_status ON cohorts(organization_id, status)',
    '''
    CREATE TABLE IF NOT EXISTS cohort_memberships (
        cohort_membership_id TEXT PRIMARY KEY,
        cohort_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(cohort_id, user_id),
        FOREIGN KEY(cohort_id) REFERENCES cohorts(cohort_id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_cohort_memberships_cohort_id ON cohort_memberships(cohort_id)',
    'CREATE INDEX IF NOT EXISTS idx_cohort_memberships_user_id ON cohort_memberships(user_id)',
    'CREATE INDEX IF NOT EXISTS idx_cohort_memberships_user_cohort ON cohort_memberships(user_id, cohort_id)',
    '''
    CREATE TABLE IF NOT EXISTS signup_invite_batches (
        batch_id TEXT PRIMARY KEY,
        created_by_user_id TEXT,
        organization_id TEXT,
        role TEXT NOT NULL,
        membership_role TEXT NOT NULL DEFAULT \'member\',
        label TEXT,
        requested_count INTEGER NOT NULL DEFAULT 0,
        created_count INTEGER NOT NULL DEFAULT 0,
        failed_count INTEGER NOT NULL DEFAULT 0,
        email_delivery_queued_count INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(organization_id) REFERENCES organizations(organization_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_signup_invite_batches_org_created ON signup_invite_batches(organization_id, created_at)',
    '''
    CREATE TABLE IF NOT EXISTS signup_invites (
        invite_id TEXT PRIMARY KEY,
        invite_code TEXT NOT NULL UNIQUE,
        batch_id TEXT,
        created_by_user_id TEXT,
        email TEXT,
        role TEXT NOT NULL,
        organization_id TEXT,
        membership_role TEXT NOT NULL DEFAULT \'member\',
        expires_at TEXT,
        consumed_at TEXT,
        consumed_by_user_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT \'{}\',
        created_at TEXT NOT NULL,
        FOREIGN KEY(batch_id) REFERENCES signup_invite_batches(batch_id) ON DELETE SET NULL,
        FOREIGN KEY(created_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(consumed_by_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
        FOREIGN KEY(organization_id) REFERENCES organizations(organization_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_signup_invites_email ON signup_invites(email)',
    'CREATE INDEX IF NOT EXISTS idx_signup_invites_batch_id ON signup_invites(batch_id)',
    'CREATE INDEX IF NOT EXISTS idx_signup_invites_org_id ON signup_invites(organization_id)',
    'CREATE INDEX IF NOT EXISTS idx_signup_invites_expires_at ON signup_invites(expires_at)',
    'CREATE INDEX IF NOT EXISTS idx_signup_invites_org_consumed_expires ON signup_invites(organization_id, consumed_at, expires_at)',
    '''
    CREATE TABLE IF NOT EXISTS analytics_snapshots (
        scope_type TEXT NOT NULL,
        scope_key TEXT NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        generated_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY(scope_type, scope_key)
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_expires_at ON analytics_snapshots(expires_at)',
    '''
    CREATE TABLE IF NOT EXISTS data_delivery_preferences (
        user_id TEXT PRIMARY KEY,
        cadence TEXT NOT NULL DEFAULT 'weekly',
        include_member_summary INTEGER NOT NULL DEFAULT 0,
        include_cohort_summary INTEGER NOT NULL DEFAULT 1,
        include_org_summary INTEGER NOT NULL DEFAULT 0,
        cohort_id TEXT,
        last_sent_at TEXT,
        next_send_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
        FOREIGN KEY(cohort_id) REFERENCES cohorts(cohort_id) ON DELETE SET NULL
    )
    ''',
    'CREATE INDEX IF NOT EXISTS idx_data_delivery_next_send ON data_delivery_preferences(next_send_at, user_id)',
    'CREATE INDEX IF NOT EXISTS idx_data_delivery_enabled_next_send ON data_delivery_preferences(include_member_summary, include_cohort_summary, include_org_summary, next_send_at)',
)


def _translate_sql(sql: str) -> str:
    return sql.replace('?', '%s')



def _connect_sqlite() -> sqlite3.Connection:
    if not SQLITE_DB_PATH:
        raise RuntimeError('SQLite database path is not configured')
    conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn



def _get_postgres_pool() -> ConnectionPool:
    global _POSTGRES_POOL
    if _POSTGRES_POOL is None:
        if ConnectionPool is None or dict_row is None:
            raise RuntimeError(
                'PostgreSQL support requires psycopg[binary,pool]. Install backend requirements first.'
            )
        min_size = max(1, int(os.getenv('VRT_DB_POOL_MIN_SIZE', '1')))
        max_size = max(min_size, int(os.getenv('VRT_DB_POOL_MAX_SIZE', '8')))
        _POSTGRES_POOL = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=min_size,
            max_size=max_size,
            kwargs={'row_factory': dict_row},
            open=True,
        )
    return _POSTGRES_POOL



def close_database() -> None:
    global _POSTGRES_POOL
    if _POSTGRES_POOL is not None:
        _POSTGRES_POOL.close()
        _POSTGRES_POOL = None


@contextmanager
def get_connection() -> Iterator[DatabaseConnection]:
    if DATABASE_BACKEND == _DATABASE_BACKEND_POSTGRESQL:
        pool = _get_postgres_pool()
        with pool.connection() as raw_conn:
            wrapped = DatabaseConnection(DATABASE_BACKEND, raw_conn)
            try:
                yield wrapped
                raw_conn.commit()
            except Exception:
                raw_conn.rollback()
                raise
    else:
        raw_conn = _connect_sqlite()
        wrapped = DatabaseConnection(DATABASE_BACKEND, raw_conn)
        try:
            yield wrapped
            raw_conn.commit()
        except Exception:
            raw_conn.rollback()
            raise
        finally:
            raw_conn.close()



def _table_columns(conn: DatabaseConnection, table_name: str) -> set[str]:
    if conn.backend == _DATABASE_BACKEND_POSTGRESQL:
        rows = conn.execute(
            '''
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            ''',
            (table_name,),
        ).fetchall()
        return {str(row['column_name']) for row in rows}

    rows = conn.execute(f'PRAGMA table_info({table_name})').fetchall()
    return {str(row['name']) for row in rows}



def _ensure_column(conn: DatabaseConnection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}')



def init_db() -> None:
    with get_connection() as conn:
        table_statements: list[str] = []
        index_statements: list[str] = []
        for statement in SCHEMA_STATEMENTS:
            normalized = statement.strip().upper()
            if normalized.startswith('CREATE INDEX'):
                index_statements.append(statement)
            else:
                table_statements.append(statement)

        for statement in table_statements:
            conn.execute(statement)

        _ensure_column(conn, 'users', 'deactivated_at', 'TEXT')
        _ensure_column(conn, 'users', 'metadata_json', "TEXT NOT NULL DEFAULT '{}'" )
        _ensure_column(conn, 'signup_invites', 'batch_id', 'TEXT')
        _ensure_column(conn, 'assignments', 'organization_id', 'TEXT')
        _ensure_column(conn, 'hand_results', 'review_flagged', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'hand_results', 'review_sent_to_coaches', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(conn, 'data_delivery_preferences', 'last_sent_at', 'TEXT')
        _ensure_column(conn, 'data_delivery_preferences', 'next_send_at', 'TEXT')
        conn.execute(
            '''
            UPDATE hand_results
            SET review_flagged = CASE WHEN metadata_json LIKE ? THEN 1 ELSE 0 END,
                review_sent_to_coaches = CASE WHEN metadata_json LIKE ? THEN 1 ELSE 0 END
            ''',
            ('%"flagged":true%', '%"sent_to_coaches":true%'),
        )

        for statement in index_statements:
            conn.execute(statement)



def json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(',', ':'), sort_keys=True)



def json_loads(payload_json: str) -> dict[str, Any]:
    data = json.loads(payload_json)
    if not isinstance(data, dict):
        raise ValueError('Expected JSON object payload')
    return data
