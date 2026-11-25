'''Provider-free deterministic decisions for a reliable offline demo.'''
from hashlib import sha256

from backend.app.config import get_settings
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


def _document_id(filename: str) -> str:
    # Same derivation as rag/ingest.py, so IDs match the versioned corpus.
    version = get_settings().tax_corpus_version
    return sha256(f'{version}:{filename}'.encode('utf-8')).hexdigest()[:20]


# Verbatim passages from the versioned tax corpus. Offline mode selects them by
# a fixed category rule instead of similarity search, and says so in reasoning;
# test_offline_evidence checks them against the corpus PDFs when present.
SECTION_37_1 = {
    'file': 'ita_core_business_deductions.pdf',
    'title': 'ita_core_business_deductions',
    'page': 13,
    'chunk': 'p13:s0:c114',
    'section': 'Section 37(1)',
    'passage': (
        '37. (1) Any expenditure (not being expenditure of the nature described in '
        'sections 30 to 36 and not being in the nature of capital expenditure or '
        'personal expenses of the assessee), laid out or expended wholly and '
        'exclusively for the purposes of the business or profession shall be '
        'allowed in computing the income chargeable under the head "Profits and '
        'gains of business or profession".'
    ),
}
SECTION_32_1 = {
    'file': 'ita_core_business_deductions.pdf',
    'title': 'ita_core_business_deductions',
    'page': 1,
    'chunk': 'p1:s0:c0',
    'section': 'Section 32(1)',
    'passage': (
        '32. (1) In respect of depreciation of— (i) buildings, machinery, plant or '
        'furniture, being tangible assets; (ii) know-how, patents, copyrights, '
        'trade marks, licences, franchises or any other business or commercial '
        'rights of similar nature, being intangible assets acquired on or after '
        'the 1st day of April, 1998, not being goodwill of a business or '
        'profession, owned, wholly or partly, by the assessee and used for the '
        'purposes of the business or profession, the following deductions shall '
        'be allowed—'
    ),
}
SELECTION_NOTE = (
    ' Offline demo mode: this statute passage was selected by a fixed category '
    'rule, not by similarity search, and the same passage supports every '
    'transaction in this category.'
)
DEDUCTIBLE_REASONS = {
    'Software Subscriptions': 'Recurring software and cloud subscriptions are revenue expenditure used in running the business, not capital assets.',
    'Travel & Transit': 'Travel for client meetings and business trips is revenue expenditure incurred for the business.',
    'Business Meals': 'Meals with clients or for work meetings are treated as business expenditure when the business purpose is documented.',
    'Office Supplies': 'Consumable office supplies are revenue expenditure used up in the ordinary course of business.',
    'Professional Fees': 'Fees for tax, audit, and compliance services are incurred wholly for the business.',
    'Telephone & Internet': 'Business broadband and phone lines are recurring revenue expenditure for the business.',
}


def evaluate_category(category: str) -> dict:
    if category == 'Entertainment':
        return _result(
            TaxTreatment.NON_DEDUCTIBLE,
            'The demo rule treats leisure entertainment (films, concerts) as not '
            'wholly and exclusively for the business, so it is excluded from the '
            'draft total; an accountant may decide otherwise with evidence.',
            SECTION_37_1,
        )
    if category == 'Hardware & Equipment':
        return _result(
            TaxTreatment.DEPRECIABLE,
            'Computers and equipment are tangible capital assets: they are '
            'depreciated under Section 32 (Appendix I lists computers including '
            'software at 40%), not deducted in full this period. The depreciation '
            'basis, rate, and period need transaction-specific review.',
            SECTION_32_1,
        )
    if category in DEDUCTIBLE_REASONS:
        return _result(
            TaxTreatment.DEDUCTIBLE,
            DEDUCTIBLE_REASONS[category]
            + ' Section 37(1) allows such expenditure when it is not capital or personal.',
            SECTION_37_1,
        )
    return {
        'treatment': TaxTreatment.UNDETERMINED.value,
        'reasoning': 'Retrieval could not support a tax treatment.',
        'evidence': None,
        'allowed_fraction': None,
        'error': None,
    }


def _result(treatment: TaxTreatment, reasoning: str, source: dict) -> dict:
    document_id = _document_id(source['file'])
    return {
        'treatment': treatment.value,
        'reasoning': reasoning + SELECTION_NOTE,
        'evidence': {
            'corpus_version': get_settings().tax_corpus_version,
            'document_id': document_id,
            'title': source['title'],
            'page': source['page'],
            'chunk_id': f"{document_id}:{source['chunk']}",
            'section': source['section'],
            'passage': source['passage'],
            'retrieval_score': 1.0,
        },
        'allowed_fraction': 1.0 if treatment == TaxTreatment.DEDUCTIBLE else None,
        'error': None,
    }
