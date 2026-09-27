import os

os.environ.setdefault('OFFLINE_DEMO_MODE', 'true')

from backend.app.graph.nodes.corrective_rag import _evaluate_category
from backend.app.graph.state import TaxTreatment


def test_unsupported_category_is_undetermined_without_evidence():
    result = _evaluate_category(
        'New Vegas County Hyper-Loop Commuter Passes',
        max_retries=1,
    )

    assert result['treatment'] == TaxTreatment.UNDETERMINED
    assert result['evidence'] is None
    assert result['allowed_fraction'] is None
