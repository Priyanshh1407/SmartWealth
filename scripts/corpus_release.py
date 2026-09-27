"""Inspect or verify an immutable corpus release before deploy/rollback."""
import argparse
from pathlib import Path

from backend.app.config import get_settings
from backend.app.rag.versioning import chroma_release_path, collection_name


def target_for(version: str) -> str:
    settings = get_settings()
    if settings.vector_backend == 'pgvector':
        return collection_name(settings.vector_collection, version)
    return str(chroma_release_path(settings.chroma_path, version))


def verify_release(version: str) -> str:
    settings = get_settings()
    target = target_for(version)
    if settings.vector_backend == 'pgvector':
        if not settings.vector_database_url:
            raise RuntimeError('VECTOR_DATABASE_URL is required for pgvector verification.')
        import psycopg
        url = settings.vector_database_url.replace(
            'postgresql+psycopg://',
            'postgresql://',
            1,
        )
        with psycopg.connect(url) as connection:
            row = connection.execute(
                'SELECT 1 FROM langchain_pg_collection WHERE name = %s',
                (target,),
            ).fetchone()
        if row is None:
            raise RuntimeError(f'Corpus collection does not exist: {target}')
    elif not Path(target).is_dir():
        raise RuntimeError(f'Chroma corpus release does not exist: {target}')
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    target = verify_release(args.version) if args.verify else target_for(args.version)
    print(f'Corpus target: {target}')
    print(f'Rollback by deploying with TAX_CORPUS_VERSION={args.version}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
