import React, { useState, useEffect, useCallback, useMemo } from 'react';
import MetricCard from './MetricCard';
import TransactionTable from './TransactionTable';
import AuditorPanel from './AuditorPanel';
import UploadZone from './UploadZone';
import EvidenceDrawer from './EvidenceDrawer';
import EvaluationDashboard from './EvaluationDashboard';
import RunTimeline from './RunTimeline';
import useRunStore from '../store/useRunStore';
import { healthCheck } from '../api/client';

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
    deductibilityResults,
    pendingClarifications,
    totalTransactions,
    totalDeductible,
    averageModelConfidence,
    humanOverrideIds,
    runTimeline,
    auditTrail,
    evaluationSummary,
    evaluationError,
    progress,
    errors,
    finalReport,
    runAudit,
    resetAudit,
    cancelAudit,
    streamState,
    reconnectAttempt,
    retryStream,
    runFailureDemo,
    loadEvaluation,
  } = useRunStore();

  const [selectedTxn, setSelectedTxn] = useState(null);
  const [showErrors, setShowErrors] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [showEvaluation, setShowEvaluation] = useState(false);
  const [evidenceTxn, setEvidenceTxn] = useState(null);
  const [backendStatus, setBackendStatus] = useState('checking'); // 'checking' | 'online' | 'offline'
  const isActiveRun = ['queued', 'running', 'waiting_for_input', 'loading']
    .includes(status);

  // Check backend health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
        
        await healthCheck({ signal: controller.signal });
        clearTimeout(timeoutId);
        setBackendStatus('online');
      } catch {
        setBackendStatus('offline');
      }
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 3000);
    return () => clearInterval(interval);
  }, []);

  // Failures remain visible until explicitly dismissed.
  useEffect(() => {
    setShowErrors(errors.length > 0);
  }, [errors.length]);

  // Show report panel when final report arrives
  useEffect(() => {
    if (finalReport && status === 'completed') {
      setShowReport(true);
    }
  }, [finalReport, status]);

  useEffect(() => {
    if (showEvaluation && !evaluationSummary && !evaluationError) {
      void loadEvaluation();
    }
  }, [evaluationError, evaluationSummary, loadEvaluation, showEvaluation]);

  const dismissErrors = useCallback(() => {
    setShowErrors(false);
  }, []);

  const transactionById = useMemo(
    () => new Map(transactions.map((item) => [item.transaction_id, item])),
    [transactions],
  );

  // Automatically select the first pending clarification if none is selected
  useEffect(() => {
    if (status === 'waiting_for_input' && pendingClarifications.length > 0 && !selectedTxn) {
      const firstPending = pendingClarifications[0];
      const tId = firstPending.transaction_id || firstPending;
      const originalTxn = transactionById.get(tId);
      if (originalTxn) {
        setSelectedTxn({
          ...originalTxn,
          status: 'unresolved',
          clarificationQuestion: firstPending.question || "AI confidence below threshold. Manual review required."
        });
      }
    } else if (pendingClarifications.length === 0) {
      setSelectedTxn(null);
    }
  }, [pendingClarifications, selectedTxn, status, transactionById]);

  const tableData = useMemo(() => {
    const categoryById = new Map(categorized.map((item) => [item.transaction_id, item]));
    const pendingById = new Map(pendingClarifications.map(
      (item) => [item.transaction_id || item, item],
    ));
    const resultById = new Map(deductibilityResults.map(
      (item) => [item.transaction_id, item],
    ));
    const overrideIds = new Set(humanOverrideIds);

    return transactions.map((txn) => {
      const cat = categoryById.get(txn.transaction_id);
      const isPending = pendingById.get(txn.transaction_id);
      const ded = resultById.get(txn.transaction_id);

    let txnStatus = 'processing';
    if (isPending || (cat && cat.predicted_category === 'Unknown')) {
      txnStatus = 'unresolved';
    } else if (ded) {
      const statusByTreatment = {
        deductible: 'deductible',
        non_deductible: 'not_deductible',
        depreciable: 'depreciable',
        partially_deductible: 'partial',
        undetermined: 'unresolved',
      };
      txnStatus = statusByTreatment[ded.treatment] || 'unresolved';
      if (
        ded.requires_accountant_review &&
        ded.allowed_current_period_amount === 0 &&
        ded.treatment !== 'depreciable'
      ) {
        txnStatus = 'unresolved';
      }
    }

      return {
        ...txn,
        id: txn.transaction_id,
        category: cat ? cat.predicted_category : 'Processing…',
        confidence: cat ? cat.confidence_score : 0,
        status: txnStatus,
        treatment: ded?.treatment,
        evidence: ded?.evidence,
        reasoning: ded?.reasoning,
        humanOverridden: overrideIds.has(txn.transaction_id),
        clarificationQuestion: isPending?.question || 'Model confidence is below the review threshold.',
      };
    });
  }, [categorized, deductibilityResults, humanOverrideIds, pendingClarifications, transactions]);

  // Progress bar percentage
  const progressPercent = progress && progress.total > 0
    ? Math.round((progress.processed / progress.total) * 100)
    : 0;

  // Current node display name
  const currentNodeLabel = progress
    ? (NODE_LABELS[progress.current_node] || progress.current_node)
    : '';

  // Check if we hit a hard rate limit
  const hasRateLimitError = errors.some(err => 
    err.toLowerCase().includes('retries exhausted') || 
    err.toLowerCase().includes('rate limit') || 
    err.toLowerCase().includes('quota') ||
    err.toLowerCase().includes('429')
  );

  return (
    <div
      data-testid="dashboard-shell"
      className="w-full max-w-[1600px] min-h-[calc(100dvh-32px)] mx-auto glass-panel rounded-2xl shadow-[0_0_80px_rgba(0,0,0,0.8)] relative flex flex-col p-sm sm:p-md md:p-lg gap-md overflow-visible"
    >
      {/* Top Branding & Action Header */}
      <header className="z-10 border-b border-white/10 pb-sm mb-sm shrink-0">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-sm">
            <span className="material-symbols-outlined text-[32px] text-primary">robot_2</span>
            <div className="flex flex-col">
              <span className="font-headline-lg text-[20px] md:text-[24px] font-bold tracking-tighter leading-none text-primary">Smart Wealth</span>
              <div className="flex items-center gap-2 mt-1">
                <span className="font-label-caps text-[10px] text-primary/70">AI Tax Auditor</span>
                {/* Backend Status Light */}
                <div 
                  className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${
                    backendStatus === 'online' ? 'bg-green-500/10 border-green-500/30' :
                    backendStatus === 'offline' ? 'bg-red-500/10 border-red-500/30' :
                    'bg-yellow-500/10 border-yellow-500/30'
                  }`}
                  title={
                    backendStatus === 'online' ? 'Backend Connected' :
                    backendStatus === 'offline' ? 'Backend Offline - Start it with python -m backend.app.main' :
                    'Connecting to Backend...'
                  }
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    backendStatus === 'online' ? 'bg-green-500 shadow-[0_0_5px_#22c55e]' :
                    backendStatus === 'offline' ? 'bg-red-500 shadow-[0_0_5px_#ef4444]' :
                    'bg-yellow-500 shadow-[0_0_5px_#eab308] animate-pulse'
                  }`}></span>
                  <span className={`text-[8px] font-bold uppercase tracking-wider ${
                    backendStatus === 'online' ? 'text-green-500' :
                    backendStatus === 'offline' ? 'text-red-500' :
                    'text-yellow-500'
                  }`}>
                    {backendStatus === 'online' ? 'API Online' : backendStatus === 'offline' ? 'API Offline' : 'Connecting'}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-sm">
            <button
              type="button"
              onClick={() => setShowEvaluation((visible) => !visible)}
              className="flex items-center justify-center px-sm py-xs bg-primary/10 border border-primary/30 text-primary rounded-lg font-label-caps hover:bg-primary/20 text-[11px]"
            >
              <span className="material-symbols-outlined mr-xs text-[16px]">monitoring</span>
              Evaluation
            </button>
            {status === 'idle' && (
              <button
                type="button"
                onClick={() => void runFailureDemo()}
                className="flex items-center justify-center px-sm py-xs bg-tertiary/10 border border-tertiary/30 text-tertiary rounded-lg font-label-caps hover:bg-tertiary/20 text-[11px]"
                title="Runs the normal audit workflow with a simulated provider 429 and a checkpointed human-review pause."
              >
                <span className="material-symbols-outlined mr-xs text-[16px]">experiment</span>
                Failure demo
              </button>
            )}
            {/* Reset Button — visible unless loading */}
            {isActiveRun && status !== 'loading' && (
              <button
                onClick={cancelAudit}
                className="flex items-center justify-center px-sm py-xs bg-error/10 border border-error/30 text-error rounded-lg font-label-caps hover:bg-error/20 transition-all text-[11px]"
              >
                <span className="material-symbols-outlined mr-xs text-[16px]">cancel</span>
                Cancel
              </button>
            )}
            {status !== 'loading' && (
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
            {/* Run Audit / Status Button — only visible after upload */}
            {status !== 'idle' && (
              <div
                role="status"
                className="flex items-center justify-center px-md py-xs bg-primary/20 text-primary rounded-lg font-label-caps shrink-0 text-[11px]"
              >
                <span className="material-symbols-outlined mr-xs text-[16px]">
                  {isActiveRun ? 'autorenew' : 'check_circle'}
                </span>
                {status === 'queued' ? 'Queued...' : status === 'running' ? 'Running...' : status === 'waiting_for_input' ? 'Waiting for Input' : status === 'loading' ? 'Starting...' : status === 'completed' ? 'Audit Complete' : status === 'failed' ? 'Failed' : status === 'cancelled' ? 'Cancelled' : status === 'error' ? 'Error' : 'Run Audit'}
              </div>
            )}
          </div>
        </div>

        {/* Active Status Indicator — ALWAYS visible in header when running or paused */}
        {isActiveRun && (
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
        {(status === 'failed' || status === 'cancelled') && (
          <div className="flex items-center gap-xs mt-sm pt-sm border-t border-white/5">
            <span className="material-symbols-outlined text-error text-[14px]">
              {status === 'failed' ? 'error' : 'cancel'}
            </span>
            <span className="font-label-caps text-error text-[10px]">
              {status === 'failed' ? 'Audit Failed' : 'Audit Cancelled'}
            </span>
          </div>
        )}
      </header>

      {streamState === 'reconnecting' && (
        <div role="status" className="shrink-0 z-10 rounded-lg border border-tertiary/30 bg-tertiary/10 p-sm text-sm text-tertiary flex items-center justify-between gap-sm">
          <span>Live updates disconnected. Reconnection attempt {reconnectAttempt} is scheduled.</span>
          <button
            type="button"
            onClick={retryStream}
            className="rounded-md border border-tertiary/40 px-sm py-xs font-bold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-tertiary"
          >
            Retry now
          </button>
        </div>
      )}

      {/* Persistent Rate Limit Exhausted Banner */}
      {hasRateLimitError && (
        <div className="shrink-0 z-10 animate-fade-slide-down mb-sm">
          <div className="rounded-xl p-md bg-error/20 border border-error/50 flex flex-col md:flex-row items-start md:items-center justify-between gap-sm shadow-[0_0_20px_rgba(255,84,73,0.3)]">
            <div className="flex items-center gap-sm">
              <span className="material-symbols-outlined text-[32px] text-error">hourglass_disabled</span>
              <div>
                <h3 className="font-title-md text-error font-bold">API Rate Limits Exhausted</h3>
                <p className="text-[12px] text-on-surface-variant mt-1">
                  You have hit the maximum number of free tier requests. Please wait a few minutes before trying again. 
                  Some transactions may be marked as 'Unknown'.
                </p>
              </div>
            </div>
            <button
              onClick={resetAudit}
              className="shrink-0 px-md py-xs bg-error text-on-error rounded-lg font-label-caps hover:bg-error/80 transition-colors shadow-lg"
            >
              Reset Audit
            </button>
          </div>
        </div>
      )}

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
                    <p key={i} className="font-body-sm text-[11px] text-on-error-container/80 break-words">
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
                type="button"
                onClick={dismissErrors}
                aria-label="Dismiss errors"
                className="shrink-0 w-6 h-6 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors"
              >
                <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {showEvaluation && (
        <EvaluationDashboard
          summary={evaluationSummary}
          error={evaluationError}
          onClose={() => setShowEvaluation(false)}
        />
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
                type="button"
                onClick={() => setShowReport(false)}
                aria-label="Close final report"
                className="w-6 h-6 rounded-full bg-white/5 hover:bg-white/10 flex items-center justify-center transition-colors"
              >
                <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
              </button>
            </div>

            <p role="note" className="mb-md rounded-lg border border-tertiary/30 bg-tertiary/10 p-sm text-xs leading-5 text-on-surface-variant">
              This is an evidence-backed draft for accountant review, not tax advice or a filed return. Verify transaction facts, legal applicability, and current law before relying on any amount.
            </p>

            {/* Report Summary Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-sm mb-md">
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Transactions</p>
                <p className="text-xl font-bold text-on-surface">{finalReport.total_transactions_processed}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Allowed This Period</p>
                <p className="text-xl font-bold text-secondary">₹{finalReport.total_allowed_current_period_deductions_inr?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
              </div>
              <div className="bg-black/30 rounded-lg p-sm text-center">
                <p className="font-label-caps text-outline text-[9px] mb-xs">Draft Claims</p>
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
                  <span className="material-symbols-outlined text-[14px]">summarize</span>
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
                          acc[claim.category].amount += claim.allowed_current_period_amount;
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
      <main className="flex-1 grid grid-cols-1 xl:grid-cols-12 gap-gutter overflow-visible z-10 min-h-0">
        {status === 'idle' && transactions.length === 0 ? (
          <div className="xl:col-span-12 h-full flex flex-col animate-fade-scale">
            <UploadZone onStartAudit={runAudit} />
          </div>
        ) : (
          <>
            {/* Left Column: Metrics & Ledger */}
            <div className="xl:col-span-8 flex flex-col gap-gutter min-h-0">

              {/* Hero Metrics Grid */}
              <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-md shrink-0">
                <MetricCard
                  title="Total Transactions Scanned"
                  value={categorized.length.toLocaleString() + (totalTransactions > 0 ? ` / ${totalTransactions}` : '')}
                  icon="list_alt"
                  colorClass="text-outline-variant"
                  delayClass="stagger-1"
                />
                <MetricCard
                  title="Current-Period Draft Amount"
                  value={`₹${totalDeductible.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                  icon="account_balance_wallet"
                  colorClass="text-secondary"
                  delayClass="stagger-2"
                />
                <MetricCard
                  title="Average Model Confidence"
                  value={`${averageModelConfidence}%`}
                  isCircular={true}
                  delayClass="stagger-3"
                />
                <MetricCard
                  title="Human Overrides"
                  value={humanOverrideIds.length.toLocaleString()}
                  icon="person_check"
                  colorClass="text-tertiary"
                  delayClass="stagger-4"
                  isWarning={humanOverrideIds.length > 0}
                />
              </section>

              {/* Ledger Table */}
              <section className="glass-card rounded-xl flex-1 flex flex-col min-h-0 overflow-hidden animate-fade-scale ledger-anim">
                <div className="flex justify-between items-center p-md border-b border-white/5 shrink-0">
                  <h2 className="font-title-md text-on-surface">Transaction Ledger</h2>
                  {(status === 'queued' || status === 'running') && (
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
                <div
                  role="region"
                  aria-label="Scrollable transaction ledger"
                  tabIndex={0}
                  className="flex-1 min-h-0 max-h-[65vh] overflow-auto p-md pt-0 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary"
                >
                  <TransactionTable
                    transactions={tableData}
                    onResolve={(txn) => setSelectedTxn(txn)}
                    onViewEvidence={(txn) => setEvidenceTxn(txn)}
                  />
                </div>
              </section>
            </div>

            {/* Right Column: AI Auditor Panel */}
            <div className="xl:col-span-4 flex min-h-0 flex-col gap-gutter">
              <AuditorPanel transaction={selectedTxn} onResolved={() => setSelectedTxn(null)} />
              <RunTimeline events={runTimeline} auditTrail={auditTrail} />
            </div>
          </>
        )}
      </main>
      <EvidenceDrawer transaction={evidenceTxn} onClose={() => setEvidenceTxn(null)} />
    </div>
  );
};

export default Dashboard;
