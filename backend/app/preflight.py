"""Safe startup checks for local and managed SmartWealth environments."""
import argparse
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

from backend.app.config import PROJECT_ROOT, get_settings
from backend.app.rag.versioning import chroma_release_path


def run_preflight() -> tuple[list[str], list[str]]:
    settings = get_settings()
    errors = settings.provider_errors()
    warnings: list[str] = []
    if sys.version_info[:2] < (3, 11):
        warnings.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} has not "
            "been exercised with the current dependency set; continue only "
            "after dependency installation and the full test suite pass."
        )
    if not settings.checkpoint_database_url:
        parent = settings.checkpoint_path.parent
        if not parent.exists() or not os.access(parent, os.W_OK):
            errors.append(f"Checkpoint directory is missing or not writable: {parent}")
    demo_csv = PROJECT_ROOT / "data" / "demo" / "smartwealth_demo.csv"
    if not demo_csv.is_file():
        errors.append(f"Canonical demo CSV is missing: {demo_csv}")
    if settings.offline_demo_mode:
        warnings.append("Offline demo mode enabled; providers and Chroma are bypassed.")
    else:
        if settings.vector_backend == 'pgvector':
            if not settings.vector_database_url:
                errors.append('VECTOR_DATABASE_URL is required for pgvector.')
        else:
            release = chroma_release_path(
                settings.chroma_path,
                settings.tax_corpus_version,
            )
            if not release.exists():
                errors.append(f"Versioned Chroma index is missing: {release}")
        if not settings.pdf_dir.exists():
            warnings.append(f"Tax PDF directory is missing: {settings.pdf_dir}")
    if settings.environment == 'production':
        if not settings.run_database_url:
            errors.append('RUN_DATABASE_URL is required in production.')
        if not settings.checkpoint_database_url:
            errors.append('CHECKPOINT_DATABASE_URL is required in production.')
        if settings.vector_backend != 'pgvector':
            errors.append('VECTOR_BACKEND must be pgvector in production.')
    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SmartWealth startup prerequisites.")
    parser.add_argument("--env-file", type=Path, help="Optional env file; values are never printed.")
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=False)
    errors, warnings = run_preflight()
    for warning in warnings:
        print(f"[WARN] {warning}")
    for error in errors:
        print(f"[ERROR] {error}")
    if errors:
        print(f"Preflight failed with {len(errors)} error(s).")
        return 1
    print("Preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
