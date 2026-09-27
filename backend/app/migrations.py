"""Apply ordered PostgreSQL schema migrations with an advisory lock."""
import argparse
from hashlib import sha256
from pathlib import Path

from backend.app.config import PROJECT_ROOT, get_settings


MIGRATIONS_DIR = PROJECT_ROOT / 'backend' / 'migrations'


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(directory.glob('[0-9][0-9][0-9]_*.sql'))


def apply_migrations(database_url: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    if not database_url.startswith(('postgresql://', 'postgresql+psycopg://')):
        raise ValueError('Migrations require a PostgreSQL database URL.')
    import psycopg
    from psycopg.rows import dict_row

    url = database_url.replace('postgresql+psycopg://', 'postgresql://', 1)
    applied: list[str] = []
    with psycopg.connect(url, row_factory=dict_row) as connection:
        with connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(7391027)')
            connection.execute(
                '''
                CREATE TABLE IF NOT EXISTS sw_schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                '''
            )
            existing = {
                row['version']: row['checksum']
                for row in connection.execute(
                    'SELECT version, checksum FROM sw_schema_migrations'
                ).fetchall()
            }
            for path in migration_files(directory):
                sql = path.read_text(encoding='utf-8')
                checksum = sha256(sql.encode('utf-8')).hexdigest()
                if path.name in existing:
                    if existing[path.name] != checksum:
                        raise RuntimeError(
                            f'Applied migration checksum changed: {path.name}'
                        )
                    continue
                connection.execute(sql)
                connection.execute(
                    '''
                    INSERT INTO sw_schema_migrations(version, checksum)
                    VALUES (%s, %s)
                    ''',
                    (path.name, checksum),
                )
                applied.append(path.name)
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=get_settings().run_database_url)
    args = parser.parse_args()
    if not args.database_url:
        parser.error('RUN_DATABASE_URL or --database-url is required.')
    applied = apply_migrations(args.database_url)
    print(f'Applied {len(applied)} migration(s).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
