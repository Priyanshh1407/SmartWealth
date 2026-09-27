import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

const OUTCOMES = {
  deductible: 'deductible treatment',
  non_deductible: 'non-deductible treatment',
  depreciable: 'depreciable treatment',
  partially_deductible: 'partially deductible treatment',
  undetermined: 'an undetermined outcome',
};

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
                ['Retrieval score', `${Math.round(evidence.retrieval_score * 100)}%`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-white/10 bg-black/20 p-sm">
                  <dt className="font-label-caps text-[9px] text-outline">{label}</dt>
                  <dd className="mt-1 break-words text-xs text-on-surface">{value}</dd>
                </div>
              ))}
            </dl>
            <section className="mt-md">
              <h3 className="font-label-caps text-[10px] text-primary">Retrieved passage</h3>
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
