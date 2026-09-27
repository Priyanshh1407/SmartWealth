import React from 'react';

const OUTCOME_LABELS = {
  deductible: 'Deductible',
  non_deductible: 'Non-deductible',
  depreciable: 'Depreciable',
  partially_deductible: 'Partially deductible',
  undetermined: 'Undetermined',
};

const TransactionTable = ({ transactions, onResolve, onViewEvidence }) => (
  <table className="w-full text-left border-collapse min-w-[920px]">
    <thead className="sticky top-0 bg-background/95 backdrop-blur-sm z-10">
      <tr className="border-b border-white/10 text-outline font-label-caps">
        <th scope="col" className="py-sm pr-md font-normal">Date</th>
        <th scope="col" className="py-sm pr-md font-normal">Merchant</th>
        <th scope="col" className="py-sm pr-md font-normal text-right">Amount</th>
        <th scope="col" className="py-sm pr-md font-normal">Predicted category</th>
        <th scope="col" className="py-sm pr-md font-normal">Model confidence</th>
        <th scope="col" className="py-sm pr-md font-normal">Outcome</th>
        <th scope="col" className="py-sm font-normal">Evidence / action</th>
      </tr>
    </thead>
    <tbody className="text-[14px]">
      {transactions.map((transaction) => {
        const needsAction = transaction.status === 'unresolved';
        const outcome = OUTCOME_LABELS[transaction.treatment]
          || (transaction.status === 'processing' ? 'Processing' : 'Pending review');
        return (
          <tr
            key={transaction.id}
            className={`border-b border-white/5 ${needsAction ? 'bg-tertiary/5' : 'hover:bg-white/[0.04]'}`}
          >
            <td className="py-sm pr-md text-on-surface-variant whitespace-nowrap">{transaction.date}</td>
            <td className="py-sm pr-md font-semibold text-on-surface">{transaction.merchant}</td>
            <td className="py-sm pr-md text-right font-mono text-on-surface">₹{transaction.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
            <td className={`py-sm pr-md ${needsAction ? 'text-tertiary' : 'text-on-surface-variant'}`}>
              {transaction.category}
              {transaction.humanOverridden && (
                <span className="ml-xs inline-flex rounded-full border border-secondary/30 bg-secondary/10 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wide text-secondary">
                  Human override
                </span>
              )}
            </td>
            <td className="py-sm pr-md">
              <div
                role="progressbar"
                aria-label={`Model confidence ${Math.round(transaction.confidence * 100)} percent`}
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={Math.round(transaction.confidence * 100)}
                className="w-24 bg-black/30 rounded-full h-1.5"
              >
                <div
                  className={`h-1.5 rounded-full ${needsAction ? 'bg-tertiary' : 'bg-primary'}`}
                  style={{ width: `${Math.max(0, Math.min(100, transaction.confidence * 100))}%` }}
                />
              </div>
            </td>
            <td className="py-sm pr-md">
              <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-bold ${
                needsAction
                  ? 'border-tertiary/30 bg-tertiary/10 text-tertiary'
                  : 'border-white/10 bg-white/5 text-on-surface-variant'
              }`}>
                {outcome}
              </span>
            </td>
            <td className="py-sm">
              {needsAction ? (
                <button
                  type="button"
                  onClick={() => onResolve(transaction)}
                  className="rounded-md border border-tertiary/30 bg-tertiary/10 px-2 py-1 text-[10px] font-bold text-tertiary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-tertiary"
                >
                  Review transaction
                </button>
              ) : transaction.evidence ? (
                <button
                  type="button"
                  onClick={() => onViewEvidence(transaction)}
                  className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] font-bold text-primary hover:bg-primary/20"
                >
                  Open evidence drawer
                </button>
              ) : (
                <span className="text-xs text-outline">No supporting passage</span>
              )}
            </td>
          </tr>
        );
      })}
    </tbody>
  </table>
);

export default TransactionTable;
