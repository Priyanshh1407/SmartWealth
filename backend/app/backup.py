"""Backup and restore helpers for local SQLite and production PostgreSQL."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import subprocess


def sqlite_backup(source: Path, destination: Path) -> Path:
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise FileNotFoundError(f'SQLite source does not exist: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(destination) as target_db:
        source_db.backup(target_db)
    return destination


def sqlite_restore(backup: Path, destination: Path) -> Path:
    return sqlite_backup(backup, destination)


def postgres_backup(database_url: str, destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['pg_dump', '--format=custom', '--file', str(destination), database_url],
        check=True,
    )
    return destination


def postgres_restore(database_url: str, backup: Path) -> None:
    backup = backup.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f'PostgreSQL backup does not exist: {backup}')
    subprocess.run(
        [
            'pg_restore',
            '--clean',
            '--if-exists',
            '--no-owner',
            '--dbname',
            database_url,
            str(backup),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'restore'))
    parser.add_argument('--database-url', default='')
    parser.add_argument('--sqlite-path', type=Path)
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    default_name = (
        'smartwealth-'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        + ('.dump' if args.database_url else '.sqlite')
    )
    artifact = args.file or (Path('backups') / default_name)
    if args.database_url:
        if args.action == 'backup':
            postgres_backup(args.database_url, artifact)
        else:
            postgres_restore(args.database_url, artifact)
    elif args.sqlite_path:
        if args.action == 'backup':
            sqlite_backup(args.sqlite_path, artifact)
        else:
            sqlite_restore(artifact, args.sqlite_path)
    else:
        parser.error('--database-url or --sqlite-path is required.')
    print(f'{args.action.title()} completed: {artifact}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
