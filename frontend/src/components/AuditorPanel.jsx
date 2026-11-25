import React, { useEffect, useState } from 'react';
import useRunStore from '../store/useRunStore';

const CATEGORY_OPTIONS = [
  'Software Subscriptions',
  'Travel & Transit',
  'Business Meals',
  'Entertainment',
  'Office Supplies',
  'Hardware & Equipment',
  'Professional Fees',
  'Telephone & Internet',
];

const AuditorPanel = ({ transaction, onResolved, samePendingMerchantCount = 0 }) => {
  const [isResolving, setIsResolving] = useState(false);
  const [category, setCategory] = useState("");
  const [submitError, setSubmitError] = useState('');
  const resolveTransaction = useRunStore(state => state.resolveTransaction);
  const reviseCategory = useRunStore(state => state.reviseCategory);
  const cancelAudit = useRunStore(state => state.cancelAudit);
  const isRevise = transaction?.mode === 'revise';

  useEffect(() => {
    // Changing a category starts from the current one; a review starts empty.
    setCategory(
      isRevise && CATEGORY_OPTIONS.includes(transaction?.category) ? transaction.category : '',
    );
    setSubmitError('');
    setIsResolving(false);
  }, [isRevise, transaction?.category, transaction?.id, transaction?.transaction_id]);

  // If no transaction is selected, show an empty state or hidden state
  if (!transaction) {
    return (
      <aside className="min-h-[180px] shrink-0 bg-background/40 backdrop-blur-md rounded-xl flex flex-col shadow-2xl relative overflow-hidden border border-white/5 items-center justify-center">
        <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 rounded-full blur-[80px] z-0 pointer-events-none"></div>
        <div className="w-16 h-16 rounded-full bg-white/5 flex items-center justify-center mb-4">
          <span className="material-symbols-outlined text-outline text-[32px]">task_alt</span>
        </div>
        <p className="text-outline font-body-sm text-center px-8">All clear. Click on a transaction requiring action to resolve it.</p>
      </aside>
    );
  }

  const handleResolve = async () => {
    if (!category || isResolving) return;
    setIsResolving(true);
    setSubmitError('');
    const submit = isRevise ? reviseCategory : resolveTransaction;
    const result = await submit(
      transaction.transaction_id || transaction.id,
      category,
    );
    setIsResolving(false);
    if (result.ok) {
      setCategory('');
      onResolved();
    } else {
      setSubmitError(result.error);
    }
  };

  return (
    <aside aria-labelledby="clarification-title" className="shrink-0 bg-background/40 backdrop-blur-md ai-border rounded-xl flex flex-col shadow-2xl relative overflow-hidden border border-white/5">
      {/* decorative background elements for depth */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 rounded-full blur-[80px] z-0 pointer-events-none"></div>
      
      <div className="relative z-10 flex flex-col h-full overflow-y-auto p-sm">
        
        <div className="flex items-center gap-sm mb-sm border-b border-white/10 pb-sm shrink-0">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center border border-primary/30 shadow-[0_0_10px_rgba(76,215,246,0.2)]">
            <span className="material-symbols-outlined text-primary text-[18px]">psychology</span>
          </div>
          <h3 id="clarification-title" className="font-title-md text-[18px] text-on-surface">
            {isRevise ? 'Change category' : 'Human-in-the-Loop'}
          </h3>
          <div className="ml-auto w-2 h-2 rounded-full bg-tertiary shadow-[0_0_8px_rgba(255,185,95,0.8)] animate-pulse shrink-0"></div>
        </div>

        <div className="bg-black/40 rounded-lg p-sm border border-tertiary/30 mb-sm relative overflow-hidden shadow-inner shrink-0">
          <div className="absolute top-0 left-0 w-1 h-full bg-tertiary shadow-[0_0_10px_rgba(255,185,95,0.6)]"></div>
          <div className="flex justify-between items-center mb-xs">
            <span className="font-label-caps text-tertiary block">{isRevise ? 'Selected transaction' : 'Active Alert'}</span>
            <span className="font-mono text-[10px] text-on-surface-variant border border-white/10 px-2 py-0.5 rounded bg-black/50">{transaction.transaction_id || transaction.id}</span>
          </div>
          <p className="font-body-sm text-[13px] text-on-surface break-words">
            Charge of <span className="font-mono text-tertiary">₹{transaction.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span> from <span className="font-mono text-on-surface font-semibold">{transaction.merchant}</span>
          </p>
          {transaction.description && (
            <p className="mt-xs font-mono text-[11px] text-on-surface-variant break-words">{transaction.description}</p>
          )}
        </div>

        {isRevise ? (
          <div className="mb-sm shrink-0">
            <span className="font-label-caps text-outline mb-xs flex items-center gap-xs">
              <span className="material-symbols-outlined text-[14px]">history_edu</span> Current decision
            </span>
            <p className="font-body-sm text-[13px] text-on-surface-variant leading-snug p-sm bg-white/5 rounded-lg border border-white/5">
              <span className="font-semibold text-on-surface">{transaction.category}</span>
              {transaction.memoryResolved
                ? ', applied from reviewer memory.'
                : transaction.humanOverridden
                  ? ', set by a reviewer.'
                  : `, predicted by the model at ${Math.round((transaction.confidence || 0) * 100)}% confidence.`}
              {' '}Changing it recalculates the tax treatment and report, is recorded in the
              audit trail, and is remembered for future audits of this merchant.
            </p>
          </div>
        ) : (
          <div className="mb-sm shrink-0">
            <span className="font-label-caps text-outline mb-xs flex items-center gap-xs">
              <span className="material-symbols-outlined text-[14px]">troubleshoot</span> AI Reasoning
            </span>
            <p className="font-body-sm text-[13px] text-on-surface-variant leading-snug p-sm bg-white/5 rounded-lg border border-white/5">
              {transaction.clarificationQuestion || "AI confidence below threshold. Manual review required."}
            </p>
            {samePendingMerchantCount > 0 && (
              <p className="mt-xs rounded-lg border border-primary/20 bg-primary/5 p-xs text-[12px] text-primary">
                Your answer also applies to {samePendingMerchantCount} other flagged
                transaction{samePendingMerchantCount > 1 ? 's' : ''} from {transaction.merchant};{' '}
                {samePendingMerchantCount > 1 ? 'they' : 'it'} will be marked as resolved from
                reviewer memory.
              </p>
            )}
          </div>
        )}

        <div className="mt-auto shrink-0 pt-sm">
          <label htmlFor="clarification-category" className="font-label-caps text-primary mb-xs block text-[10px]">{isRevise ? 'New category' : 'Please confirm category'}</label>
          <div className="relative mb-md">
            <select
              id="clarification-category"
              value={category} 
              onChange={(e) => setCategory(e.target.value)} 
              className="w-full bg-black/50 border border-white/10 border-b-primary focus:ring-0 focus:border-b-primary text-body-sm text-on-surface py-sm px-sm rounded-t-lg appearance-none cursor-pointer hover:bg-black/70 transition-colors"
            >
              <option className="bg-surface" disabled value="">Select category...</option>
              <option className="bg-surface" value="Software Subscriptions">Software Subscriptions</option>
              <option className="bg-surface" value="Travel & Transit">Travel & Transit</option>
              <option className="bg-surface" value="Business Meals">Business Meals</option>
              <option className="bg-surface" value="Entertainment">Entertainment (Non-Deductible)</option>
              <option className="bg-surface" value="Office Supplies">Office Supplies</option>
              <option className="bg-surface" value="Hardware & Equipment">Hardware & Equipment</option>
              <option className="bg-surface" value="Professional Fees">Professional Fees</option>
              <option className="bg-surface" value="Telephone & Internet">Telephone & Internet</option>
            </select>
            <span className="material-symbols-outlined absolute right-sm top-1/2 -translate-y-1/2 text-primary pointer-events-none">expand_more</span>
          </div>
          
          {submitError && (
            <div role="alert" className="mb-sm rounded-lg border border-error/30 bg-error/10 p-sm text-sm text-error">
              {submitError} {isRevise ? 'The category was not changed' : 'Your clarification is still open'}; retry when ready.
            </div>
          )}

          <div className="grid grid-cols-2 gap-sm">
            {isRevise ? (
              <button
                type="button"
                onClick={onResolved}
                disabled={isResolving}
                className="py-sm border border-white/15 text-on-surface-variant hover:bg-white/10 rounded-lg font-label-caps disabled:opacity-50"
              >
                Close
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void cancelAudit()}
                disabled={isResolving}
                className="py-sm border border-error/30 text-error hover:bg-error/10 rounded-lg font-label-caps disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error"
              >
                Cancel audit
              </button>
            )}
            <button
              type="button"
              onClick={handleResolve}
              disabled={isResolving || !category || (isRevise && category === transaction.category)}
              className="py-sm bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 rounded-lg font-label-caps flex items-center justify-center gap-xs disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {isResolving
                ? 'Submitting…'
                : submitError
                  ? 'Retry submission'
                  : isRevise ? 'Apply change' : 'Resolve'}
            </button>
          </div>
        </div>

      </div>
    </aside>
  );
};

export default AuditorPanel;
