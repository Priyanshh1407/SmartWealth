import pytest

from backend.app.config import get_settings
from backend.app.demo.offline import evaluate_category
from backend.app.graph.state import LegalEvidence
from backend.app.tools.categorizer_tools import VALID_CATEGORIES


def _normalise(text: str) -> str:
    return ' '.join(text.split())


def test_every_category_gets_valid_versioned_corpus_evidence():
    for category in VALID_CATEGORIES:
        evidence = LegalEvidence.model_validate(evaluate_category(category)['evidence'])
        assert evidence.corpus_version == get_settings().tax_corpus_version
        assert evidence.chunk_id.startswith(f'{evidence.document_id}:')
        assert 'Deterministic demo evidence' not in evidence.passage


def test_capital_and_revenue_categories_cite_different_law():
    hardware = evaluate_category('Hardware & Equipment')
    software = evaluate_category('Software Subscriptions')
    travel = evaluate_category('Travel & Transit')

    assert hardware['evidence']['section'] == 'Section 32(1)'
    assert software['evidence']['section'] == 'Section 37(1)'
    assert hardware['evidence']['passage'] != software['evidence']['passage']
    # Same statute for revenue categories, but the reasoning is category specific.
    assert software['reasoning'] != travel['reasoning']
    assert 'fixed category rule' in software['reasoning']


def test_offline_passages_are_verbatim_from_the_local_corpus():
    pdf_dir = get_settings().pdf_dir
    if not pdf_dir.exists() or not any(pdf_dir.glob('*.pdf')):
        pytest.skip('Tax corpus PDFs are not present (they are not committed).')
    from backend.app.rag.ingest import _prepare_chunks

    chunks = {
        chunk.metadata['chunk_id']: _normalise(chunk.page_content)
        for chunk in _prepare_chunks(pdf_dir)
    }
    for category in ('Hardware & Equipment', 'Software Subscriptions'):
        evidence = evaluate_category(category)['evidence']
        assert evidence['chunk_id'] in chunks
        assert _normalise(evidence['passage']) in chunks[evidence['chunk_id']]
