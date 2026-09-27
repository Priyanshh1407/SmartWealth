import React, { useEffect, useState } from 'react';
import useRunStore from '../store/useRunStore';

const AuditorPanel = ({ transaction, onResolved }) => {
  const [isResolving, setIsResolving] = useState(false);
  const [category, setCategory] = useState("");
  const [submitError, setSubmitError] = useState('');
  const resolveTransaction = useRunStore(state => state.resolveTransaction);
  const cancelAudit = useRunStore(state => state.cancelAudit);

  useEffect(() => {
    setCategory('');
    setSubmitError('');
    setIsResolving(false);
  }, [transaction?.id, transaction?.transaction_id]);

  // If no transaction is selected, show an empty state or hidden state
  if (!transaction) {
    return (
      <aside className="min-h-[240px] flex-1 bg-background/40 backdrop-blur-md rounded-xl flex flex-col shadow-2xl relative overflow-hidden border border-white/5 items-center justify-center">
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
    const result = await resolveTransaction(
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
    <aside aria-labelledby="clarification-title" className="min-h-[320px] flex-1 bg-background/40 backdrop-blur-md ai-border rounded-xl flex flex-col shadow-2xl relative overflow-hidden border border-white/5">
      {/* decorative background elements for depth */}
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary/10 rounded-full blur-[80px] z-0 pointer-events-none"></div>
      
      <div className="relative z-10 flex flex-col h-full overflow-y-auto p-sm">
        
        <div className="flex items-center gap-sm mb-sm border-b border-white/10 pb-sm shrink-0">
          <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center border border-primary/30 shadow-[0_0_10px_rgba(76,215,246,0.2)]">
            <span className="material-symbols-outlined text-primary text-[18px]">psychology</span>
          </div>
          <h3 id="clarification-title" className="font-title-md text-[18px] text-on-surface">Human-in-the-Loop</h3>
          <div className="ml-auto w-2 h-2 rounded-full bg-tertiary shadow-[0_0_8px_rgba(255,185,95,0.8)] animate-pulse shrink-0"></div>
        </div>

        <div className="bg-black/40 rounded-lg p-sm border border-tertiary/30 mb-sm relative overflow-hidden shadow-inner shrink-0">
          <div className="absolute top-0 left-0 w-1 h-full bg-tertiary shadow-[0_0_10px_rgba(255,185,95,0.6)]"></div>
          <div className="flex justify-between items-center mb-xs">
            <span className="font-label-caps text-tertiary block">Active Alert</span>
            <span className="font-mono text-[10px] text-on-surface-variant border border-white/10 px-2 py-0.5 rounded bg-black/50">{transaction.transaction_id || transaction.id}</span>
          </div>
          <p className="font-body-sm text-[13px] text-on-surface break-words">
            MISC charge of <span className="font-mono text-tertiary">₹{transaction.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span> from <span className="font-mono text-on-surface font-semibold">{transaction.merchant}</span>
          </p>
        </div>

        <div className="mb-sm shrink-0">
          <span className="font-label-caps text-outline mb-xs flex items-center gap-xs">
            <span className="material-symbols-outlined text-[14px]">troubleshoot</span> AI Reasoning
          </span>
          <p className="font-body-sm text-[13px] text-on-surface-variant leading-snug p-sm bg-white/5 rounded-lg border border-white/5">
            {transaction.clarificationQuestion || "AI confidence below threshold. Manual review required."}
          </p>
        </div>

        <div className="mt-auto shrink-0 pt-sm">
          <label htmlFor="clarification-category" className="font-label-caps text-primary mb-xs block text-[10px]">Please confirm category</label>
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
              {submitError} Your clarification is still open; retry when ready.
            </div>
          )}

          <div className="grid grid-cols-2 gap-sm">
            <button
              type="button"
              onClick={() => void cancelAudit()}
              disabled={isResolving}
              className="py-sm border border-error/30 text-error hover:bg-error/10 rounded-lg font-label-caps disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-error"
            >
              Cancel audit
            </button>
            <button
              type="button"
              onClick={handleResolve}
              disabled={isResolving || !category}
              className="py-sm bg-primary/10 border border-primary/30 text-primary hover:bg-primary/20 rounded-lg font-label-caps flex items-center justify-center gap-xs disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {isResolving ? 'Submitting…' : submitError ? 'Retry submission' : 'Resolve'}
            </button>
          </div>
        </div>

      </div>
    </aside>
  );
};

export default AuditorPanel;
