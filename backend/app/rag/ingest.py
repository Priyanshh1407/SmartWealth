"""Build and atomically replace the local tax-corpus vector index."""
import logging
import os
import shutil
import uuid
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.app.config import get_settings
from backend.app.rag.versioning import chroma_release_path, collection_name

load_dotenv()
settings = get_settings()
logger = logging.getLogger(__name__)


def validated_managed_path(target: Path, allowed_root: Path) -> Path:
    """Return a resolved managed path, rejecting roots and path escapes."""
    resolved_root = allowed_root.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_root or not resolved_target.is_relative_to(
        resolved_root
    ):
        raise ValueError('Managed index path must be a child of ALLOWED_DATA_ROOT.')
    return resolved_target


def _safe_remove(target: Path, allowed_root: Path) -> None:
    managed = validated_managed_path(target, allowed_root)
    if managed.exists():
        shutil.rmtree(managed)


def _prepare_chunks(pdf_dir: Path):
    documents = PyPDFDirectoryLoader(pdf_dir).load()
    if not documents:
        raise RuntimeError('No tax-corpus documents were found.')
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    for index, chunk in enumerate(chunks):
        source = Path(str(chunk.metadata.get('source', 'document')))
        document_id = sha256(
            f'{settings.tax_corpus_version}:{source.name}'.encode('utf-8')
        ).hexdigest()[:20]
        page_number = int(chunk.metadata.get('page', 0)) + 1
        start_index = int(chunk.metadata.get('start_index', 0))
        chunk.metadata.update({
            'corpus_version': settings.tax_corpus_version,
            'document_id': document_id,
            'title': source.stem,
            'page_number': page_number,
            'chunk_id': (
                f'{document_id}:p{page_number}:s{start_index}:c{index}'
            ),
        })
    return chunks


def ingest_tax_documents(
    *,
    chroma_path: Path | None = None,
    pdf_dir: Path | None = None,
    allowed_data_root: Path | None = None,
) -> None:
    """Stage a complete index and swap it in without deleting the live index."""
    allowed_root = (allowed_data_root or settings.allowed_data_root).resolve()
    vector_root = chroma_path or settings.chroma_path
    destination = validated_managed_path(
        chroma_release_path(vector_root, settings.tax_corpus_version),
        allowed_root,
    )
    source_dir = (pdf_dir or settings.pdf_dir).resolve()
    if not source_dir.is_relative_to(allowed_root):
        raise ValueError('PDF_DIR must be inside ALLOWED_DATA_ROOT.')

    token = uuid.uuid4().hex
    staging = validated_managed_path(
        destination.parent / f'.{destination.name}.staging-{token}',
        allowed_root,
    )
    backup = validated_managed_path(
        destination.parent / f'.{destination.name}.backup-{token}',
        allowed_root,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    chunks = _prepare_chunks(source_dir)
    embeddings = HuggingFaceEmbeddings(model_name=settings.embedding_model)

    if settings.vector_backend == 'pgvector':
        if not settings.vector_database_url:
            raise RuntimeError('VECTOR_DATABASE_URL is required for pgvector.')
        from langchain_postgres import PGVector
        PGVector.from_documents(
            documents=chunks,
            embedding=embeddings,
            collection_name=collection_name(
                settings.vector_collection,
                settings.tax_corpus_version,
            ),
            connection=settings.vector_database_url,
            use_jsonb=True,
            pre_delete_collection=True,
        )
        logger.info(
            'Versioned pgvector corpus release created.',
            extra={'corpus_version': settings.tax_corpus_version},
        )
        return

    try:
        Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=str(staging),
        )
        if not staging.exists():
            raise RuntimeError('Staged vector index was not created.')
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
        _safe_remove(backup, allowed_root)
        logger.info(
            'Versioned Chroma corpus release atomically replaced.',
            extra={'corpus_version': settings.tax_corpus_version},
        )
    finally:
        _safe_remove(staging, allowed_root)


if __name__ == '__main__':
    ingest_tax_documents()
