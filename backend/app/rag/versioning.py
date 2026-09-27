"""Stable names for immutable vector-index releases."""
from pathlib import Path
import re


VERSION_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')


def validate_corpus_version(version: str) -> str:
    value = version.strip()
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError('Corpus version must be a safe 1-80 character identifier.')
    return value


def collection_name(base: str, version: str) -> str:
    safe_version = validate_corpus_version(version).replace('.', '_').replace('-', '_')
    safe_base = re.sub(r'[^A-Za-z0-9_]', '_', base.strip())
    if not safe_base:
        raise ValueError('Vector collection base name is required.')
    return f'{safe_base}_{safe_version}'


def chroma_release_path(root: Path, version: str) -> Path:
    return root.resolve() / validate_corpus_version(version)
