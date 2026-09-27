import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from backend.app.config import get_settings
from backend.app.runs.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    IdempotencyConflictError,
    InvalidTransitionError,
    RunNotFoundError,
    RunProgress,
    RunRecord,
    RunStatus,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """SQLite/PostgreSQL repository for optimistic-locked run records."""

    def __init__(self, database_path: Path | str):
        value = str(database_path)
        self.is_postgres = value.startswith(('postgresql://', 'postgresql+psycopg://'))
        self.database_url = value if self.is_postgres else ''
        self.database_path = None if self.is_postgres else Path(value).resolve()
        if self.database_path is not None:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        if self.is_postgres:
            return _PostgresConnection(self.database_url)
        assert self.database_path is not None
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout = 30000')
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            if not self.is_postgres:
                connection.execute('PRAGMA journal_mode = WAL')
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS sw_runs (
                    run_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    current_node TEXT NOT NULL,
                    progress_message TEXT NOT NULL,
                    progress_processed INTEGER NOT NULL,
                    progress_total INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    warnings_json TEXT NOT NULL DEFAULT '[]',
                    provider_calls INTEGER NOT NULL DEFAULT 0,
                    provider_input_tokens INTEGER NOT NULL DEFAULT 0,
                    provider_output_tokens INTEGER NOT NULL DEFAULT 0,
                    estimated_provider_cost_usd REAL NOT NULL DEFAULT 0,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sw_runs_owner_status
                    ON sw_runs(owner_id, status);
                CREATE TABLE IF NOT EXISTS sw_idempotency (
                    owner_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (owner_id, operation, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS sw_audit_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    prior_prediction TEXT NOT NULL DEFAULT '',
                    downstream_impact TEXT NOT NULL DEFAULT '',
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sw_audit_run
                    ON sw_audit_events(run_id, occurred_at);
                CREATE TABLE IF NOT EXISTS sw_run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}',
                    occurred_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sw_run_event_timeline
                    ON sw_run_events(run_id, occurred_at, event_id);
                '''
            )
            self._ensure_column(
                connection,
                'sw_runs',
                'expires_at',
                "TEXT NOT NULL DEFAULT '1970-01-01T00:00:00+00:00'",
            )
            self._ensure_column(
                connection,
                'sw_runs',
                'provider_calls',
                'INTEGER NOT NULL DEFAULT 0',
            )
            self._ensure_column(
                connection,
                'sw_runs',
                'provider_input_tokens',
                'INTEGER NOT NULL DEFAULT 0',
            )
            self._ensure_column(
                connection,
                'sw_runs',
                'provider_output_tokens',
                'INTEGER NOT NULL DEFAULT 0',
            )
            self._ensure_column(
                connection,
                'sw_runs',
                'estimated_provider_cost_usd',
                'REAL NOT NULL DEFAULT 0',
            )
            self._ensure_column(
                connection,
                'sw_audit_events',
                'prior_prediction',
                "TEXT NOT NULL DEFAULT ''",
            )
            self._ensure_column(
                connection,
                'sw_audit_events',
                'downstream_impact',
                "TEXT NOT NULL DEFAULT ''",
            )

    @staticmethod
    def _append_run_event(
        connection: Any,
        *,
        run_id: str,
        owner_id: str,
        event_type: str,
        stage: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
        occurred_at: str | None = None,
    ) -> None:
        connection.execute(
            '''
            INSERT INTO sw_run_events (
                event_id, run_id, owner_id, event_type, stage, status,
                message, details_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                str(uuid.uuid4()),
                run_id,
                owner_id,
                event_type,
                stage,
                status,
                message,
                json.dumps(details or {}, sort_keys=True, separators=(',', ':')),
                occurred_at or utc_now(),
            ),
        )

    def append_run_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._select_run(connection, run_id)
            self._append_run_event(
                connection,
                run_id=run_id,
                owner_id=row['owner_id'],
                event_type=event_type,
                stage=stage,
                status=row['status'],
                message=message,
                details=details,
            )
            connection.commit()

    @staticmethod
    def _ensure_column(
        connection: Any,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if getattr(connection, 'is_postgres', False):
            columns = {
                row['column_name']
                for row in connection.execute(
                    '''
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = current_schema() AND table_name = ?
                    ''',
                    (table,),
                ).fetchall()
            }
        else:
            columns = {
                row['name']
                for row in connection.execute(f'PRAGMA table_info({table})')
            }
        if column not in columns:
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN {column} {definition}'
            )

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row['run_id'],
            owner_id=row['owner_id'],
            status=RunStatus(row['status']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            expires_at=row['expires_at'],
            started_at=row['started_at'],
            completed_at=row['completed_at'],
            error_code=row['error_code'],
            error_message=row['error_message'],
            progress=RunProgress(
                current_node=row['current_node'],
                message=row['progress_message'],
                processed=row['progress_processed'],
                total=row['progress_total'],
            ),
            version=row['version'],
            cancel_requested=bool(row['cancel_requested']),
            warnings=json.loads(row['warnings_json']),
            provider_calls=row['provider_calls'],
            provider_input_tokens=row['provider_input_tokens'],
            provider_output_tokens=row['provider_output_tokens'],
            estimated_provider_cost_usd=row['estimated_provider_cost_usd'],
            payload=json.loads(row['payload_json']),
        )

    @staticmethod
    def _select_run(
        connection: Any,
        run_id: str,
        owner_id: str | None = None,
    ) -> sqlite3.Row:
        if owner_id is None:
            row = connection.execute(
                'SELECT * FROM sw_runs WHERE run_id = ?',
                (run_id,),
            ).fetchone()
        else:
            row = connection.execute(
                'SELECT * FROM sw_runs WHERE run_id = ? AND owner_id = ?',
                (run_id, owner_id),
            ).fetchone()
        if row is None:
            raise RunNotFoundError('Run not found.')
        return row

    def get(self, run_id: str, owner_id: str | None = None) -> RunRecord:
        with self._connection() as connection:
            return self._row_to_record(
                self._select_run(connection, run_id, owner_id)
            )

    def ping(self) -> bool:
        with self._connection() as connection:
            return connection.execute('SELECT 1').fetchone()[0] == 1

    def find_idempotent(
        self,
        owner_id: str,
        operation: str,
        idempotency_key: str,
        request_hash: str,
    ) -> RunRecord | None:
        with self._connection() as connection:
            row = connection.execute(
                '''
                SELECT request_hash, run_id
                FROM sw_idempotency
                WHERE owner_id = ? AND operation = ? AND idempotency_key = ?
                ''',
                (owner_id, operation, idempotency_key),
            ).fetchone()
            if row is None:
                return None
            if row['request_hash'] != request_hash:
                raise IdempotencyConflictError(
                    'Idempotency key was already used with a different request.'
                )
            return self._row_to_record(
                self._select_run(connection, row['run_id'], owner_id)
            )

    def create_run(
        self,
        *,
        owner_id: str,
        idempotency_key: str,
        request_hash: str,
        payload: dict[str, Any],
        total: int,
        retention_hours: int = 24,
        max_active_runs: int = 1_000_000,
    ) -> tuple[RunRecord, bool]:
        now = utc_now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=retention_hours)
        ).isoformat()
        run_id = str(uuid.uuid4())
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            active_count = connection.execute(
                '''
                SELECT COUNT(*) FROM sw_runs
                WHERE owner_id = ? AND status IN (?, ?, ?)
                ''',
                (
                    owner_id,
                    RunStatus.QUEUED.value,
                    RunStatus.RUNNING.value,
                    RunStatus.WAITING_FOR_INPUT.value,
                ),
            ).fetchone()[0]
            existing = connection.execute(
                '''
                SELECT request_hash, run_id
                FROM sw_idempotency
                WHERE owner_id = ? AND operation = 'start'
                    AND idempotency_key = ?
                ''',
                (owner_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing['request_hash'] != request_hash:
                    connection.rollback()
                    raise IdempotencyConflictError(
                        'Idempotency key was already used with a different request.'
                    )
                record = self._row_to_record(
                    self._select_run(
                        connection,
                        existing['run_id'],
                        owner_id,
                    )
                )
                connection.commit()
                return record, True
            if active_count >= max_active_runs:
                connection.rollback()
                raise InvalidTransitionError(
                    'Owner has reached the active-run limit.'
                )
            connection.execute(
                '''
                INSERT INTO sw_runs (
                    run_id, owner_id, status, created_at, updated_at, expires_at,
                    current_node, progress_message, progress_processed,
                    progress_total, version, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 1, ?)
                ''',
                (
                    run_id,
                    owner_id,
                    RunStatus.QUEUED.value,
                    now,
                    now,
                    expires_at,
                    'queued',
                    'Queued for processing.',
                    total,
                    json.dumps(payload, sort_keys=True, separators=(',', ':')),
                ),
            )
            connection.execute(
                '''
                INSERT INTO sw_idempotency (
                    owner_id, operation, idempotency_key,
                    request_hash, run_id, created_at
                ) VALUES (?, 'start', ?, ?, ?, ?)
                ''',
                (
                    owner_id,
                    idempotency_key,
                    request_hash,
                    run_id,
                    now,
                ),
            )
            self._append_run_event(
                connection,
                run_id=run_id,
                owner_id=owner_id,
                event_type='run_queued',
                stage='queued',
                status=RunStatus.QUEUED.value,
                message='Run accepted and queued.',
                details={'transaction_count': total},
                occurred_at=now,
            )
            record = self._row_to_record(
                self._select_run(connection, run_id, owner_id)
            )
            connection.commit()
            return record, False

    def reserve_resume(
        self,
        *,
        run_id: str,
        owner_id: str,
        idempotency_key: str,
        request_hash: str,
        answers: list[dict[str, str]] | None = None,
        override_context: dict[str, dict[str, str]] | None = None,
        correlation_id: str = 'unassigned',
    ) -> tuple[RunRecord, bool]:
        operation = f'resume:{run_id}'
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._select_run(connection, run_id, owner_id)
            existing = connection.execute(
                '''
                SELECT request_hash, run_id
                FROM sw_idempotency
                WHERE owner_id = ? AND operation = ? AND idempotency_key = ?
                ''',
                (owner_id, operation, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing['request_hash'] != request_hash:
                    connection.rollback()
                    raise IdempotencyConflictError(
                        'Idempotency key was already used with a different request.'
                    )
                connection.commit()
                return self._row_to_record(row), True
            if RunStatus(row['status']) != RunStatus.WAITING_FOR_INPUT:
                connection.rollback()
                raise InvalidTransitionError(
                    'Only a run waiting for input can be resumed.'
                )
            updated = connection.execute(
                '''
                UPDATE sw_runs
                SET status = ?, updated_at = ?, started_at = COALESCE(started_at, ?),
                    current_node = 'resume', progress_message = 'Resuming audit.',
                    version = version + 1
                WHERE run_id = ? AND version = ? AND status = ?
                ''',
                (
                    RunStatus.RUNNING.value,
                    now,
                    now,
                    run_id,
                    row['version'],
                    RunStatus.WAITING_FOR_INPUT.value,
                ),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise InvalidTransitionError(
                    'Run state changed before resume could be accepted.'
                )
            connection.execute(
                '''
                INSERT INTO sw_idempotency (
                    owner_id, operation, idempotency_key,
                    request_hash, run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    owner_id,
                    operation,
                    idempotency_key,
                    request_hash,
                    run_id,
                    now,
                ),
            )
            previous = connection.execute(
                '''
                SELECT event_hash FROM sw_audit_events
                WHERE run_id = ? ORDER BY occurred_at DESC LIMIT 1
                ''',
                (run_id,),
            ).fetchone()
            previous_hash = previous['event_hash'] if previous else 'GENESIS'
            for answer in answers or []:
                context = (override_context or {}).get(
                    str(answer['transaction_id']),
                    {},
                )
                prior_prediction = context.get('prior_prediction', 'Unknown')
                downstream_impact = context.get(
                    'downstream_impact',
                    'Tax treatment and report will be recalculated.',
                )
                occurred_at = utc_now()
                event_id = str(uuid.uuid4())
                material = '|'.join([
                    previous_hash,
                    event_id,
                    run_id,
                    owner_id,
                    str(answer['transaction_id']),
                    str(answer['answer']),
                    prior_prediction,
                    downstream_impact,
                    occurred_at,
                    correlation_id,
                ])
                event_hash = sha256(material.encode('utf-8')).hexdigest()
                connection.execute(
                    '''
                    INSERT INTO sw_audit_events (
                        event_id, run_id, owner_id, event_type,
                        transaction_id, answer, prior_prediction,
                        downstream_impact, occurred_at, correlation_id,
                        previous_hash, event_hash
                    ) VALUES (?, ?, ?, 'human_override', ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        event_id,
                        run_id,
                        owner_id,
                        answer['transaction_id'],
                        answer['answer'],
                        prior_prediction,
                        downstream_impact,
                        occurred_at,
                        correlation_id,
                        previous_hash,
                        event_hash,
                    ),
                )
                previous_hash = event_hash
            self._append_run_event(
                connection,
                run_id=run_id,
                owner_id=owner_id,
                event_type='run_resumed',
                stage='resume',
                status=RunStatus.RUNNING.value,
                message='Human clarification accepted; run resumed.',
                details={'override_count': len(answers or [])},
                occurred_at=now,
            )
            record = self._row_to_record(
                self._select_run(connection, run_id, owner_id)
            )
            connection.commit()
            return record, False

    def transition(
        self,
        run_id: str,
        *,
        expected_statuses: Iterable[RunStatus],
        new_status: RunStatus,
        expected_version: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        current_node: str | None = None,
        message: str | None = None,
    ) -> RunRecord:
        expected = tuple(status.value for status in expected_statuses)
        if not expected:
            raise ValueError('At least one expected status is required.')
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._select_run(connection, run_id)
            if row['status'] not in expected:
                connection.rollback()
                raise InvalidTransitionError(
                    f'Cannot transition {row["status"]} to {new_status.value}.'
                )
            if expected_version is not None and row['version'] != expected_version:
                connection.rollback()
                raise InvalidTransitionError(
                    'Run version changed before transition could be applied.'
                )
            started_at = (
                now
                if new_status == RunStatus.RUNNING and row['started_at'] is None
                else row['started_at']
            )
            completed_at = (
                now if new_status in TERMINAL_STATUSES else row['completed_at']
            )
            updated = connection.execute(
                '''
                UPDATE sw_runs
                SET status = ?, updated_at = ?, started_at = ?,
                    completed_at = ?, error_code = ?, error_message = ?,
                    current_node = ?, progress_message = ?,
                    version = version + 1
                WHERE run_id = ? AND version = ?
                ''',
                (
                    new_status.value,
                    now,
                    started_at,
                    completed_at,
                    error_code,
                    error_message,
                    current_node or row['current_node'],
                    message or row['progress_message'],
                    run_id,
                    row['version'],
                ),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise InvalidTransitionError(
                    'Run version changed before transition could be applied.'
                )
            self._append_run_event(
                connection,
                run_id=run_id,
                owner_id=row['owner_id'],
                event_type=f'run_{new_status.value}',
                stage=current_node or row['current_node'],
                status=new_status.value,
                message=message or row['progress_message'],
                details={'previous_status': row['status']},
                occurred_at=now,
            )
            record = self._row_to_record(
                self._select_run(connection, run_id)
            )
            connection.commit()
            return record

    def update_progress(
        self,
        run_id: str,
        *,
        current_node: str | None = None,
        message: str | None = None,
        processed: int | None = None,
        total: int | None = None,
    ) -> None:
        assignments = ['updated_at = ?', 'version = version + 1']
        values: list[Any] = [utc_now()]
        for column, value in (
            ('current_node', current_node),
            ('progress_message', message),
            ('progress_processed', processed),
            ('progress_total', total),
        ):
            if value is not None:
                assignments.append(f'{column} = ?')
                values.append(value)
        values.extend([
            run_id,
            RunStatus.QUEUED.value,
            RunStatus.RUNNING.value,
            RunStatus.WAITING_FOR_INPUT.value,
        ])
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = self._select_run(connection, run_id)
            except RunNotFoundError:
                connection.rollback()
                return
            connection.execute(
                f'''
                UPDATE sw_runs SET {', '.join(assignments)}
                WHERE run_id = ? AND status IN (?, ?, ?)
                ''',
                values,
            )
            if current_node and current_node != row['current_node']:
                self._append_run_event(
                    connection,
                    run_id=run_id,
                    owner_id=row['owner_id'],
                    event_type='stage_started',
                    stage=current_node,
                    status=row['status'],
                    message=message or f'Entered {current_node}.',
                )
            connection.commit()

    def add_warning(self, run_id: str, warning: str) -> None:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = self._select_run(connection, run_id)
            except RunNotFoundError:
                connection.rollback()
                return
            warnings = json.loads(row['warnings_json'])
            warnings.append(warning)
            connection.execute(
                '''
                UPDATE sw_runs
                SET warnings_json = ?, updated_at = ?, version = version + 1
                WHERE run_id = ? AND version = ?
                ''',
                (
                    json.dumps(warnings),
                    utc_now(),
                    run_id,
                    row['version'],
                ),
            )
            connection.commit()

    def consume_provider_budget(
        self,
        run_id: str,
        *,
        call_count: int,
        estimated_cost_usd: float,
        max_calls: int,
        max_cost_usd: float,
    ) -> bool:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = self._select_run(connection, run_id)
            except RunNotFoundError:
                connection.rollback()
                return False
            next_calls = row['provider_calls'] + call_count
            next_cost = (
                row['estimated_provider_cost_usd'] + estimated_cost_usd
            )
            if next_calls > max_calls or next_cost > max_cost_usd:
                connection.rollback()
                return False
            connection.execute(
                '''
                UPDATE sw_runs
                SET provider_calls = ?, estimated_provider_cost_usd = ?,
                    updated_at = ?, version = version + 1
                WHERE run_id = ? AND version = ?
                ''',
                (
                    next_calls,
                    next_cost,
                    utc_now(),
                    run_id,
                    row['version'],
                ),
            )
            connection.commit()
            return True

    def record_provider_usage(
        self,
        run_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError('Provider token usage cannot be negative.')
        with self._connection() as connection:
            connection.execute(
                '''
                UPDATE sw_runs
                SET provider_input_tokens = provider_input_tokens + ?,
                    provider_output_tokens = provider_output_tokens + ?,
                    updated_at = ?, version = version + 1
                WHERE run_id = ?
                ''',
                (input_tokens, output_tokens, utc_now(), run_id),
            )

    def audit_events(
        self,
        run_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            self._select_run(connection, run_id, owner_id)
            rows = connection.execute(
                '''
                SELECT event_id, event_type, owner_id AS actor,
                    transaction_id, prior_prediction, answer,
                    downstream_impact, occurred_at, correlation_id,
                    previous_hash, event_hash
                FROM sw_audit_events
                WHERE run_id = ? ORDER BY occurred_at
                ''',
                (run_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def timeline_events(
        self,
        run_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            self._select_run(connection, run_id, owner_id)
            rows = connection.execute(
                'SELECT event_id, event_type, stage, status, message, '
                'details_json, occurred_at FROM sw_run_events '
                'WHERE run_id = ? ORDER BY occurred_at, event_id',
                (run_id,),
            ).fetchall()
            return [
                {
                    **dict(row),
                    'details': json.loads(row['details_json']),
                }
                for row in rows
            ]

    def purge_expired(self) -> int:
        now = utc_now()
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT run_id FROM sw_runs
                WHERE expires_at <= ? AND status IN (?, ?, ?)
                ''',
                (
                    now,
                    RunStatus.COMPLETED.value,
                    RunStatus.FAILED.value,
                    RunStatus.CANCELLED.value,
                ),
            ).fetchall()
            for row in rows:
                self._delete_checkpoint_rows(connection, row['run_id'])
                connection.execute(
                    'DELETE FROM sw_audit_events WHERE run_id = ?',
                    (row['run_id'],),
                )
                connection.execute(
                    'DELETE FROM sw_run_events WHERE run_id = ?',
                    (row['run_id'],),
                )
                connection.execute(
                    'DELETE FROM sw_idempotency WHERE run_id = ?',
                    (row['run_id'],),
                )
                connection.execute(
                    'DELETE FROM sw_runs WHERE run_id = ?',
                    (row['run_id'],),
                )
            return len(rows)

    def cancel(self, run_id: str, owner_id: str) -> RunRecord:
        now = utc_now()
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._select_run(connection, run_id, owner_id)
            status = RunStatus(row['status'])
            if status == RunStatus.CANCELLED:
                connection.commit()
                return self._row_to_record(row)
            if status not in ACTIVE_STATUSES:
                connection.rollback()
                raise InvalidTransitionError(
                    f'Cannot cancel a {status.value} run.'
                )
            connection.execute(
                '''
                UPDATE sw_runs
                SET status = ?, cancel_requested = 1, updated_at = ?,
                    completed_at = ?, current_node = 'cancelled',
                    progress_message = 'Audit cancelled.',
                    version = version + 1
                WHERE run_id = ? AND version = ?
                ''',
                (
                    RunStatus.CANCELLED.value,
                    now,
                    now,
                    run_id,
                    row['version'],
                ),
            )
            self._append_run_event(
                connection,
                run_id=run_id,
                owner_id=owner_id,
                event_type='run_cancelled',
                stage='cancelled',
                status=RunStatus.CANCELLED.value,
                message='Audit cancelled.',
                details={'previous_status': status.value},
                occurred_at=now,
            )
            record = self._row_to_record(
                self._select_run(connection, run_id, owner_id)
            )
            connection.commit()
            return record

    def delete(self, run_id: str, owner_id: str) -> None:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = self._select_run(connection, run_id, owner_id)
            status = RunStatus(row['status'])
            if status not in TERMINAL_STATUSES:
                connection.rollback()
                raise InvalidTransitionError(
                    'Active runs must be cancelled before deletion.'
                )
            self._delete_checkpoint_rows(connection, run_id)
            connection.execute(
                'DELETE FROM sw_audit_events WHERE run_id = ?',
                (run_id,),
            )
            connection.execute(
                'DELETE FROM sw_run_events WHERE run_id = ?',
                (run_id,),
            )
            connection.execute(
                'DELETE FROM sw_idempotency WHERE run_id = ?',
                (run_id,),
            )
            connection.execute(
                'DELETE FROM sw_runs WHERE run_id = ?',
                (run_id,),
            )
            connection.commit()

    @staticmethod
    def _delete_checkpoint_rows(
        connection: Any,
        run_id: str,
    ) -> None:
        for table_name in (
            'checkpoint_writes',
            'checkpoint_blobs',
            'checkpoints',
        ):
            exists = RunStore._table_exists(connection, table_name)
            if exists:
                connection.execute(
                    f'DELETE FROM {table_name} WHERE thread_id = ?',
                    (run_id,),
                )

    @staticmethod
    def _table_exists(connection: Any, table_name: str) -> bool:
        if getattr(connection, 'is_postgres', False):
            row = connection.execute(
                '''
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = current_schema() AND table_name = ?
                ''',
                (table_name,),
            ).fetchone()
        else:
            row = connection.execute(
                '''
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = ?
                ''',
                (table_name,),
            ).fetchone()
        return row is not None

    def list_recoverable(self) -> list[RunRecord]:
        statuses = tuple(status.value for status in ACTIVE_STATUSES)
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM sw_runs
                WHERE status IN (?, ?, ?)
                ORDER BY created_at
                ''',
                statuses,
            ).fetchall()
            return [self._row_to_record(row) for row in rows]

    def purge_all(self) -> int:
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            active_count = connection.execute(
                '''
                SELECT COUNT(*) FROM sw_runs
                WHERE status IN (?, ?, ?)
                ''',
                tuple(status.value for status in ACTIVE_STATUSES),
            ).fetchone()[0]
            if active_count:
                connection.rollback()
                raise InvalidTransitionError(
                    'Cannot purge while active runs exist.'
                )
            count = connection.execute(
                'SELECT COUNT(*) FROM sw_runs'
            ).fetchone()[0]
            for table_name in (
                'checkpoint_writes',
                'checkpoint_blobs',
                'checkpoints',
            ):
                exists = self._table_exists(connection, table_name)
                if exists:
                    connection.execute(f'DELETE FROM {table_name}')
            connection.execute('DELETE FROM sw_idempotency')
            connection.execute('DELETE FROM sw_audit_events')
            connection.execute('DELETE FROM sw_run_events')
            connection.execute('DELETE FROM sw_runs')
            connection.commit()
            return count


class _CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount

    @staticmethod
    def _row(value):
        return None if value is None else _CompatRow(value)

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]


class _PostgresConnection:
    is_postgres = True

    def __init__(self, database_url: str):
        import psycopg
        from psycopg.rows import dict_row

        url = database_url.replace('postgresql+psycopg://', 'postgresql://', 1)
        self.connection = psycopg.connect(
            url,
            autocommit=True,
            row_factory=dict_row,
        )

    @staticmethod
    def _query(query: str) -> str:
        normalized = query.strip()
        if normalized.upper() == 'BEGIN IMMEDIATE':
            return 'BEGIN'
        return query.replace('?', '%s')

    def execute(self, query: str, parameters=()):
        return _PostgresCursor(
            self.connection.execute(self._query(query), parameters)
        )

    def executescript(self, script: str) -> None:
        for statement in script.split(';'):
            if statement.strip():
                self.connection.execute(statement)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()


_settings = get_settings()
run_store = RunStore(_settings.run_database_url or _settings.checkpoint_path)
