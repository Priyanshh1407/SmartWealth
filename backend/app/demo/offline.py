'''Provider-free deterministic decisions for a reliable offline demo.'''
from backend.app.graph.state import CategorizedTransaction, TaxTreatment, Transaction
from backend.app.tools.categorizer_tools import VALID_CATEGORIES


MERCHANT_CATEGORIES = {
    'github': 'Software Subscriptions',
    'aws': 'Software Subscriptions',
    'zoho': 'Software Subscriptions',
    'ola': 'Travel & Transit',
    'uber': 'Travel & Transit',
    'indigo': 'Travel & Transit',
    'swiggy': 'Business Meals',
    'zomato': 'Business Meals',
    'chai point': 'Business Meals',
    'amazon': 'Office Supplies',
    'flipkart': 'Office Supplies',
    'croma': 'Hardware & Equipment',
    'apple': 'Hardware & Equipment',
    'reliance digital': 'Hardware & Equipment',
    'deloitte': 'Professional Fees',
    'kpmg': 'Professional Fees',
    'indiafilings': 'Professional Fees',
    'jio': 'Telephone & Internet',
    'airtel': 'Telephone & Internet',
    'bsnl': 'Telephone & Internet',
    'pvr': 'Entertainment',
    'bookmyshow': 'Entertainment',
}


def categorize_transaction(transaction: Transaction) -> CategorizedTransaction:
    merchant = transaction.merchant.strip().lower()
    original = transaction.category.strip()
    if merchant in {'', 'unknown', 'pos debit', 'pos purchase'}:
        return CategorizedTransaction(
            transaction_id=transaction.transaction_id,
            predicted_category='Unknown',
            confidence_score=0.20,
        )
    if original in VALID_CATEGORIES:
        return CategorizedTransaction(
            transaction_id=transaction.transaction_id,
            predicted_category=original,
            confidence_score=0.99,
        )
    predicted = next(
        (category for key, category in MERCHANT_CATEGORIES.items() if key in merchant),
        'Unknown',
    )
    return CategorizedTransaction(
        transaction_id=transaction.transaction_id,
        predicted_category=predicted,
        confidence_score=0.99 if predicted != 'Unknown' else 0.20,
    )


def evaluate_category(category: str) -> dict:
    if category == 'Entertainment':
        return _result(
            TaxTreatment.NON_DEDUCTIBLE,
            'Excluded from the deterministic demo deduction total.',
            'Section 37',
            category,
        )
    if category == 'Hardware & Equipment':
        return _result(
            TaxTreatment.DEPRECIABLE,
            'Capital equipment requires transaction-specific depreciation analysis.',
            'Section 32',
            category,
        )
    if category in VALID_CATEGORIES:
        return _result(
            TaxTreatment.DEDUCTIBLE,
            'Potential business expense; transaction evidence and accountant review still apply.',
            'Section 37(1)',
            category,
        )
    return {
        'treatment': TaxTreatment.UNDETERMINED.value,
        'reasoning': 'Retrieval could not support a tax treatment.',
        'evidence': None,
        'allowed_fraction': None,
        'error': None,
    }


def _result(treatment: TaxTreatment, reasoning: str, section: str, category: str) -> dict:
    document_id = 'offline-demo-tax-rules'
    slug = category.lower().replace(' ', '-').replace('&', 'and')
    return {
        'treatment': treatment.value,
        'reasoning': reasoning,
        'evidence': {
            'corpus_version': 'offline-demo-v1',
            'document_id': document_id,
            'title': 'Deterministic Offline Demo Rules',
            'page': 1,
            'chunk_id': f'{document_id}:{slug}',
            'section': section,
            'passage': 'Deterministic demo evidence used for workflow testing; it is not tax advice.',
            'retrieval_score': 1.0,
        },
        'allowed_fraction': 1.0 if treatment == TaxTreatment.DEDUCTIBLE else None,
        'error': None,
    }
