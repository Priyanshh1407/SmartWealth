import React from 'react';

const TransactionTable = ({ transactions, onResolve }) => {
  return (
    <table className="w-full text-left border-collapse min-w-[700px]">
      <thead className="sticky top-0 bg-background/90 backdrop-blur-sm z-10">
        <tr className="border-b border-white/10 text-outline font-label-caps">
          <th className="py-sm pr-md font-normal">Date</th>
          <th className="py-sm pr-md font-normal">Merchant</th>
          <th className="py-sm pr-md font-normal text-right">Amount</th>
          <th className="py-sm pr-md font-normal">AI Predicted Category</th>
          <th className="py-sm pr-md font-normal">Confidence</th>
          <th className="py-sm font-normal">Status</th>
        </tr>
      </thead>
      <tbody className="text-[15px]">
        {transactions.map((txn, index) => {
          const isWarning = txn.status === 'unresolved';
          const isPartial = txn.status === 'partial';
          const isDeductible = txn.status === 'deductible';
          
          return (
            <tr 
              key={txn.id} 
              className={`border-b border-white/5 ledger-row-transition cursor-pointer ${isWarning ? 'bg-tertiary/5 hover:bg-tertiary/15' : 'hover:bg-white/[0.06]'}`}
              onClick={() => isWarning && onResolve(txn)}
            >
              <td className="py-sm pr-md text-on-surface-variant whitespace-nowrap">{txn.date}</td>
              <td className="py-sm pr-md font-semibold text-on-surface">{txn.merchant}</td>
              <td className="py-sm pr-md text-right font-mono text-on-surface">₹{txn.amount.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
              <td className={`py-sm pr-md ${isWarning ? 'text-tertiary' : 'text-on-surface-variant'}`}>{txn.category}</td>
              
              <td className="py-sm pr-md">
                <div className="w-24 bg-black/30 rounded-full h-1.5 flex items-center">
                  <div 
                    className={`h-1.5 rounded-full ${isWarning ? 'bg-tertiary drop-shadow-[0_0_3px_rgba(255,185,95,0.8)]' : 'bg-primary drop-shadow-[0_0_3px_rgba(76,215,246,0.8)]'}`} 
                    style={{ width: `${txn.confidence * 100}%` }}
                  ></div>
                </div>
              </td>
              
              <td className="py-sm">
                {isWarning && (
                  <span className="inline-flex items-center gap-xs px-2 py-1 rounded-full bg-tertiary/10 text-tertiary font-label-caps text-[10px] border border-tertiary/20 whitespace-nowrap">
                    <span className="material-symbols-outlined text-[12px]">warning</span> Action Req
                  </span>
                )}
                {isDeductible && (
                  <span className="inline-flex items-center px-2 py-1 rounded-full bg-secondary/10 text-secondary font-label-caps text-[10px] border border-secondary/20 whitespace-nowrap">
                    Fully Deductible
                  </span>
                )}
                {isPartial && (
                  <span className="inline-flex items-center px-2 py-1 rounded-full bg-outline-variant/30 text-outline font-label-caps text-[10px] border border-outline-variant/50 whitespace-nowrap">
                    Partial Deductible
                  </span>
                )}
                {!isWarning && !isDeductible && !isPartial && (
                  <span className="inline-flex items-center px-2 py-1 rounded-full bg-outline-variant/30 text-outline font-label-caps text-[10px] border border-outline-variant/50 whitespace-nowrap">
                    Not Deductible
                  </span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  );
};

export default TransactionTable;
