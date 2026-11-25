import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

const OUTCOMES = {
  deductible: 'deductible treatment',
  non_deductible: 'non-deductible treatment',
  depreciable: 'depreciable treatment',
  partially_deductible: 'partially deductible treatment',
  undetermined: 'an undetermined outcome',
};

// Matches the note backend/app/demo/offline.py appends to offline reasoning.
const OFFLINE_SELECTION_MARKER = 'selected by a fixed category rule';

function categorySource(transaction) {
  if (transaction.memoryResolved) return 'Applied from reviewer memory for this merchant';
  if (transaction.humanOverridden) return 'Set by a reviewer';
  return `Predicted by the model at ${Math.round((transaction.confidence || 0) * 100)}% confidence`;
}

const EvidenceDrawer = ({ transaction, onClose }) => {
  const closeRef = useRef(null);

  useEffect(() => {
    if (!transaction) return undefined;
    closeRef.current?.focus();
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose, transaction]);

  if (!transaction) return null;
  const { evidence } = transaction;
  const supports = Boolean(evidence);
  // Offline mode picks statute passages by category, not by similarity search,
  // so a "retrieval score" would be meaningless there.
  const selectedByRule = Boolean(transaction.reasoning?.includes(OFFLINE_SELECTION_MARKER));

  const drawer = (
    <div className="fixed inset-0 z-[100] flex justify-end bg-black/60 backdrop-blur-sm" role="presentation">
      <button
        type="button"
        aria-label="Close evidence drawer"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-title"
        className="relative h-full w-full max-w-[36rem] overflow-y-auto overscroll-contain border-l border-white/10 bg-background/95 p-lg text-on-surface shadow-2xl"
      >
        <div className="flex items-start justify-between gap-md border-b border-white/10 pb-md">
          <div>
            <p className="font-label-caps text-primary text-[10px]">Evidence provenance</p>
            <h2 id="evidence-title" className="mt-xs text-2xl font-bold text-on-surface">
              {transaction.merchant}
            </h2>
            <p className="mt-xs font-mono text-xs text-outline">{transaction.id}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 p-xs text-on-surface-variant hover:bg-white/10"
          >
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
            <span className="sr-only">Close</span>
          </button>
        </div>

        <section aria-labelledby="evidence-transaction-title" className="mt-md rounded-xl border border-white/10 bg-black/20 p-md">
          <h3 id="evidence-transaction-title" className="font-label-caps text-[10px] text-primary">This transaction</h3>
          <dl className="mt-sm grid grid-cols-2 gap-x-md gap-y-xs text-xs">
            <dt className="text-outline">Date</dt>
            <dd className="text-on-surface">{transaction.date}</dd>
            <dt className="text-outline">Amount</dt>
            <dd className="font-mono text-on-surface">₹{Number(transaction.amount).toLocaleString(undefined, { minimumFractionDigits: 2 })}</dd>
            <dt className="text-outline">Description</dt>
            <dd className="break-words font-mono text-on-surface">{transaction.description || '—'}</dd>
            <dt className="text-outline">Category</dt>
            <dd className="text-on-surface">
              {transaction.category}
              <span className="block text-outline">
                {categorySource(transaction)}
              </span>
            </dd>
            {transaction.allowedAmount != null && (
              <>
                <dt className="text-outline">Allowed this period</dt>
                <dd className="font-mono text-on-surface">₹{Number(transaction.allowedAmount).toLocaleString(undefined, { minimumFractionDigits: 2 })}</dd>
              </>
            )}
          </dl>
          {transaction.reviewReasons?.length > 0 && (
            <ul className="mt-sm list-disc pl-md text-xs text-tertiary">
              {transaction.reviewReasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          )}
        </section>

        <div className="my-md rounded-xl border border-white/10 bg-white/5 p-md">
          <p className="font-label-caps text-[9px] text-outline">Decision relationship</p>
          <p className={`mt-xs text-sm font-semibold ${supports ? 'text-secondary' : 'text-tertiary'}`}>
            {supports
              ? `The validated passage supports the ${OUTCOMES[transaction.treatment] || 'recorded outcome'}.`
              : 'No passage met the evidence contract; the system does not present a positive legal claim.'}
          </p>
          <p className="mt-sm text-sm leading-6 text-on-surface-variant">
            {transaction.reasoning || 'No model reasoning was recorded.'}
          </p>
        </div>

        {evidence ? (
          <>
            <dl className="grid grid-cols-1 gap-sm sm:grid-cols-2">
              {[
                ['Document', evidence.title],
                ['Document ID', evidence.document_id],
                ['Corpus release', evidence.corpus_version],
                ['Section', evidence.section],
                ['Page', evidence.page],
                ['Chunk', evidence.chunk_id],
                selectedByRule
                  ? ['Selection', 'Fixed category rule (offline mode)']
                  : ['Retrieval score', `${Math.round(evidence.retrieval_score * 100)}%`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-white/10 bg-black/20 p-sm">
                  <dt className="font-label-caps text-[9px] text-outline">{label}</dt>
                  <dd className="mt-1 break-words text-xs text-on-surface">{value}</dd>
                </div>
              ))}
            </dl>
            <section className="mt-md">
              <h3 className="font-label-caps text-[10px] text-primary">
                {selectedByRule ? 'Statute passage' : 'Retrieved passage'}
              </h3>
              {transaction.rowsSharingRule > 1 && (
                <p className="mt-xs text-xs text-outline">
                  Category rule: the same passage supports all {transaction.rowsSharingRule}{' '}
                  {transaction.category} transactions in this audit. The facts above are
                  specific to this one.
                </p>
              )}
              <blockquote className="mt-sm border-l-2 border-primary/40 pl-md text-sm leading-7 text-on-surface-variant">
                {evidence.passage}
              </blockquote>
            </section>
          </>
        ) : (
          <div className="rounded-xl border border-tertiary/30 bg-tertiary/10 p-md text-sm text-on-surface-variant">
            Retrieval provenance is unavailable for this transaction. It remains pending review or non-positive.
          </div>
        )}

        <p role="note" className="mt-lg text-xs leading-5 text-outline">
          Evidence is a traceability aid for accountant review, not a substitute for verifying current law and transaction facts.
        </p>
      </aside>
    </div>
  );

  // Render outside the filtered dashboard shell. CSS filters establish a
  // containing block for fixed descendants, which can place drawer content
  // above the viewport when the transaction ledger has been scrolled.
  return createPortal(drawer, document.body);
};

export default EvidenceDrawer;
