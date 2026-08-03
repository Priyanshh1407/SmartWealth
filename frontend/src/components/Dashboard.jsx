import React, { useState, useEffect, useCallback } from 'react';
import MetricCard from './MetricCard';
import TransactionTable from './TransactionTable';
import AuditorPanel from './AuditorPanel';
import useRunStore from '../store/useRunStore';

// Human-readable names for each pipeline node
const NODE_LABELS = {
  starting: 'Initializing…',
  init: 'Initializing…',
  extraction: 'Extracting & Categorizing',
  corrective_rag: 'Evaluating Tax Deductibility',
  auditor_loop: 'Human Review Required',
  report: 'Generating Final Report',
  report_node: 'Report Complete',
  extraction_node: 'Extraction Complete',
};

const Dashboard = () => {
  const {
    status,
    transactions,
    categorized,
    pendingClarifications,
    totalTransactions,
    totalDeductible,
    accuracyScore,
    progress,
    errors,
    finalReport,
    runAudit,
    resetAudit
  } = useRunStore();

  const [selectedTxn, setSelectedTxn] = useState(null);
  const [showErrors, setShowErrors] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [errorTimerId, setErrorTimerId] = useState(null);

  // Show errors when new ones arrive, auto-dismiss after 5 seconds
  useEffect(() => {
    if (errors.length > 0) {
      setShowErrors(true);
      // Clear any existing timer
      if (errorTimerId) clearTimeout(errorTimerId);
      // Set new auto-dismiss timer (5 seconds)
      const id = setTimeout(() => setShowErrors(false), 5000);
      setErrorTimerId(id);
    } else {
      setShowErrors(false);
    }
    return () => {
      if (errorTimerId) clearTimeout(errorTimerId);
    };
  }, [errors.length]);

  // Show report panel when final report arrives
  useEffect(() => {
    if (finalReport && status === 'completed') {
      setShowReport(true);
    }
  }, [finalReport, status]);

  const dismissErrors = useCallback(() => {
    setShowErrors(false);
    if (errorTimerId) clearTimeout(errorTimerId);
  }, [errorTimerId]);

  // Automatically select the first pending clarification if none is selected
  useEffect(() => {
    if (pendingClarifications.length > 0 && !selectedTxn) {
      const firstPending = pendingClarifications[0];
      const tId = firstPending.transaction_id || firstPending;
      const originalTxn = transactions.find(t => t.transaction_id === tId);
      if (originalTxn) {
        setSelectedTxn({
          ...originalTxn,
          status: 'unresolved'
        });
      }
    } else if (pendingClarifications.length === 0) {
      setSelectedTxn(null);
    }
  }, [pendingClarifications, transactions, selectedTxn]);


  // Format the table data
  const tableData = transactions.map(txn => {
    const cat = categorized.find(c => c.transaction_id === txn.transaction_id);
    const isPending = pendingClarifications.find(p => (p.transaction_id || p) === txn.transaction_id);

    let txnStatus = 'deductible';
    if (isPending) txnStatus = 'unresolved';
    else if (!cat) txnStatus = 'processing';
    else if (cat.predicted_category === 'Unknown') txnStatus = 'unresolved';

    return {
      id: txn.transaction_id,
      date: txn.date,
      merchant: txn.merchant,
      amount: txn.amount,
      category: cat ? cat.predicted_category : 'Processing...',
      confidence: cat ? cat.confidence_score : 0,
      status: txnStatus
    };
  });

  // Progress bar percentage
  const progressPercent = progress && progress.total > 0
    ? Math.round((progress.processed / progress.total) * 100)
    : 0;

  // Current node display name
  const currentNodeLabel = progress
    ? (NODE_LABELS[progress.current_node] || progress.current_node)
    : '';

  return (
    <div className="w-full max-w-[1600px] h-[calc(100vh-64px)] mx-auto glass-panel rounded-2xl shadow-[0_0_80px_rgba(0,0,0,0.8)] relative flex flex-col p-md md:p-lg gap-md overflow-hidden">
      {/* Top Branding & Action Header */}
      <header className="z-10 border-b border-white/10 pb-sm mb-sm shrink-0">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-sm">
            <span className="material-symbols-outlined text-[32px] text-primary">robot_2</span>
            <div className="flex flex-col">
              <span className="font-headline-lg text-[20px] md:text-[24px] font-bold tracking-tighter leading-none text-primary">Smart Wealth</span>
              <span className="font-label-caps text-[10px] text-primary/70 mt-1">AI Tax Auditor</span>
            </div>
          </div>
          <div className="flex items-center gap-sm">
            {/* Reset Button — visible when completed or errored */}
            {(status === 'completed' || status === 'error' || status === 'idle') && status !== 'loading' && (
              <button
                onClick={resetAudit}
                className="flex items-center justify-center px-sm py-xs bg-white/5 border border-white/10 text-on-surface-variant rounded-lg font-label-caps hover:bg-white/10 hover:text-error transition-all text-[11px]"
              >
                <span className="material-symbols-outlined mr-xs text-[16px]">restart_alt</span>
                Reset
              </button>
            )}
            {/* Show Report Button — visible when report is ready */}
            {finalReport && (
              <button
                onClick={() => setShowReport(!showReport)}
                className="flex items-center justify-center px-sm py-xs bg-secondary/10 border border-secondary/30 text-secondary rounded-lg font-label-caps hover:bg-secondary/20 transition-all text-[11px]"
              >
                <span className="material-symbols-outlined mr-xs text-[16px]">summarize</span>
                {showReport ? 'Hide Report' : 'View Report'}
              </button>
            )}
            <button
              onClick={runAudit}
              disabled={status !== 'idle' && status !== 'completed' && status !== 'error'}
              className="flex items-center justify-center px-md py-xs bg-gradient-to-r from-primary to-primary/50 text-on-primary rounded-lg font-label-caps hover:scale-105 transition-all shrink-0 animate-pulse-glow text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="material-symbols-outlined mr-xs text-[16px]">
                {status === 'running' || status === 'loading' ? 'autorenew' : 'play_arrow'}
              </span>
              {status === 'running' ? 'Running...' : status === 'loading' ? 'Starting...' : status === 'completed' ? 'Run Again' : status === 'error' ? 'Retry' : 'Run Audit'}
            </button>
          </div>
        </div>

        {/* Active Status Indicator — ALWAYS visible in header when running or paused */}
        {(status === 'running' || status === 'loading' || status === 'paused') && (
          <div className="flex items-center justify-between mt-sm pt-sm border-t border-white/5">
            <div className="flex items-center gap-xs">
              <span className="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_rgba(76,215,246,0.8)] animate-pulse"></span>
              <span className="font-label-caps text-primary text-[10px]">{currentNodeLabel}</span>
              {progress && progress.message && (
                <span className="text-[11px] text-on-surface-variant ml-xs hidden sm:inline truncate max-w-[300px]">
                  — {progress.message}
                </span>
              )}
            </div>
            {progress && progress.total > 0 && (
              <div className="flex items-center gap-sm">
                <span className="font-label-caps text-outline text-[10px]">
                  {progress.processed}/{progress.total} ({progressPercent}%)
                </span>
                {/* Compact inline progress bar */}
                <div className="w-24 bg-black/40 rounded-full h-1 overflow-hidden hidden sm:block">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-primary to-secondary transition-all duration-700 ease-out"
                    style={{ width: `${Math.max(progressPercent, 3)}%` }}
                  ></div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Completed indicator in header */}
        {status === 'completed' && (
          <div className="flex items-center gap-xs mt-sm pt-sm border-t border-white/5">
            <span className="material-symbols-outlined text-secondary text-[14px]">check_circle</span>
            <span className="font-label-caps text-secondary text-[10px]">Audit Complete</span>
          </div>
        )}
      </header>

      {/* Error Banner — auto-dismisses after 5s, or click close */}
      {showErrors && errors.length > 0 && (
        <div className="shrink-0 z-10 animate-fade-slide-up">
          <div className="rounded-lg p-sm bg-error/10 border border-error/20 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-error shadow-[0_0_8px_rgba(255,180,171,0.6)]"></div>
            <div className="flex items-start gap-xs ml-2">
              <span className="material-symbols-outlined text-error text-[16px] mt-0.5 shrink-0">warning</span>
              <div className="flex-1 min-w-0">
                <span className="font-label-caps text-error text-[10px] block mb-xs">
                  {errors.length} Warning{errors.length > 1 ? 's' : ''}
                </span>
                <div className="max-h-20 overflow-y-auto">
                  {errors.slice(-3).map((err, i) => (
                    <p key={i} className="font-body-sm text-[11px] text-on-error-container/80 truncate">
                      {err}
                    </p>
                  ))}
                  {errors.length > 3 && (
                    <p className="font-body-sm text-[11px] text-outline mt-xs">
                      +{errors.length - 3} more…
                    </p>
                  )}
                </div>
              </div>
              {/* Close button */}
              <button
                onClick={dismissErrors}
                className="shrink-0 w-6 h-6 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors"
              >
                <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Final Report Panel — shown when audit is complete */}
      {showReport && finalReport && (
        <div className="shrink-0 z-10 animate-fade-slide-up max-h-[40vh] overflow-y-auto">
          <div className="glass-card rounded-xl p-md relative overflow-hidden">
            {/* Header */}
            <div className="flex justify-between items-center mb-md border-b border-white/10 pb-sm">
              <div className="flex items-center gap-sm">
                <span className="material-symbols-outlined text-secondary text-[24px]">assessment</span>
                <h2 className="font-title-md text-on-surface">Final Audit Report</h2>
              </div>
              <button
                onClick={() => setShowReport(false)}
                className="w-6 h-6 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors"
              >
                <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
              </button>
            </div>

            {/* Report Summary Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-sm mb-md">
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Transactions</p>
                <p className="text-xl font-bold text-on-surface">{finalReport.total_transactions_processed}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Total Deductible</p>
                <p className="text-xl font-bold text-secondary">₹{finalReport.total_deductions_inr?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Claims Verified</p>
                <p className="text-xl font-bold text-primary">{finalReport.deduction_claims?.length || 0}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Unresolved</p>
                <p className="text-xl font-bold text-tertiary">{finalReport.unresolved_items?.length || 0}</p>
              </div>
            </div>

            {/* Deduction Breakdown by Category */}
            {finalReport.deduction_claims && finalReport.deduction_claims.length > 0 && (
              <div className="mb-md">
                <h3 className="font-label-caps text-primary text-[10px] mb-sm flex items-center gap-xs">
                  <span className="material-symbols-outlined text-[14px]">receipt_long</span>
                  Deduction Breakdown by Category
                </h3>
                <div className="bg-black/20 rounded-lg overflow-hidden">
                  <table className="w-full text-[12px]">
                    <thead>
                      <tr className="border-b border-white/10">
                        <th className="font-label-caps text-outline text-[9px] text-left p-xs px-sm">Category</th>
                        <th className="font-label-caps text-outline text-[9px] text-right p-xs px-sm">Claims</th>
                        <th className="font-label-caps text-outline text-[9px] text-right p-xs px-sm">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(
                        finalReport.deduction_claims.reduce((acc, claim) => {
                          if (!acc[claim.category]) acc[claim.category] = { count: 0, amount: 0 };
                          acc[claim.category].count += 1;
                          acc[claim.category].amount += claim.amount;
                          return acc;
                        }, {})
                      ).sort(([, a], [, b]) => b.amount - a.amount).map(([category, data]) => (
                        <tr key={category} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                          <td className="p-xs px-sm text-on-surface">{category}</td>
                          <td className="p-xs px-sm text-right text-on-surface-variant">{data.count}</td>
                          <td className="p-xs px-sm text-right text-secondary font-mono">₹{data.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Unresolved Items */}
            {finalReport.unresolved_items && finalReport.unresolved_items.length > 0 && (
              <div className="mb-md">
                <h3 className="font-label-caps text-tertiary text-[10px] mb-sm flex items-center gap-xs">
                  <span className="material-symbols-outlined text-[14px]">flag</span>
                  Items Requiring Accountant Review
                </h3>
                <div className="space-y-xs">
                  {finalReport.unresolved_items.map((item, i) => (
                    <div key={i} className="bg-black/20 rounded-lg p-xs px-sm border-l-2 border-l-tertiary">
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-[11px] text-tertiary">{item.transaction_id}</span>
                      </div>
                      <p className="text-[11px] text-on-surface-variant mt-xs truncate">{item.reason_flagged}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Warnings */}
            {finalReport.warnings && finalReport.warnings.length > 0 && (
              <div>
                <h3 className="font-label-caps text-outline text-[10px] mb-sm flex items-center gap-xs">
                  <span className="material-symbols-outlined text-[14px]">info</span>
                  Audit Notes
                </h3>
                <div className="space-y-xs">
                  {finalReport.warnings.map((warning, i) => (
                    <p key={i} className="text-[11px] text-on-surface-variant pl-sm border-l border-white/10">
                      {warning}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-gutter overflow-hidden z-10 min-h-0">
        {/* Left Column: Metrics & Ledger */}
        <div className="xl:col-span-8 flex flex-col gap-gutter min-h-0">

          {/* Hero Metrics Grid */}
          <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-md shrink-0">
            <MetricCard
              title="Total Transactions Scanned"
              value={categorized.length.toLocaleString() + (totalTransactions > 0 ? ` / ${totalTransactions}` : '')}
              icon="receipt_long"
              colorClass="text-outline-variant"
              delayClass="stagger-1"
            />
            <MetricCard
              title="Total Deductible Amount"
              value={`₹${totalDeductible.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
              icon="account_balance_wallet"
              colorClass="text-secondary"
              delayClass="stagger-2"
            />
            <MetricCard
              title="AI Confidence Score"
              value={`${accuracyScore}%`}
              isCircular={true}
              delayClass="stagger-3"
            />
            <MetricCard
              title="Action Required"
              value={pendingClarifications.length.toLocaleString()}
              icon="warning"
              colorClass="text-tertiary drop-shadow-[0_0_5px_rgba(255,185,95,0.5)]"
              delayClass="stagger-4"
              isWarning={pendingClarifications.length > 0}
            />
          </section>

          {/* Ledger Table */}
          <section className="glass-card rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden animate-fade-scale ledger-anim">
            <div className="flex justify-between items-center p-md border-b border-white/5 shrink-0">
              <h2 className="font-title-md text-on-surface">Transaction Ledger</h2>
              {status === 'running' && (
                <span className="text-primary font-label-caps flex items-center gap-xs animate-pulse">
                  <span className="w-2 h-2 rounded-full bg-primary"></span> Processing...
                </span>
              )}
              {status === 'completed' && (
                <span className="text-secondary font-label-caps flex items-center gap-xs">
                  <span className="material-symbols-outlined text-[14px]">check_circle</span> Complete
                </span>
              )}
            </div>
            <div className="overflow-y-auto overflow-x-auto p-md pt-0">
              <TransactionTable
                transactions={tableData}
                onResolve={(txn) => setSelectedTxn(txn)}
              />
            </div>
          </section>
        </div>

        {/* Right Column: AI Auditor Panel */}
        <AuditorPanel transaction={selectedTxn} onResolved={() => setSelectedTxn(null)} />
      </main>
    </div>
  );
};

export default Dashboard;
