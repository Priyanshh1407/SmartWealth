import { create } from 'zustand';
import { apiRequest, streamRun } from '../api/client';

const STORAGE_KEY = 'smart-wealth-audit-state';
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);

const generateIdempotencyKey = () => (
  globalThis.crypto?.randomUUID?.()
  || `request-${Date.now()}-${Math.random().toString(36).slice(2)}`
);

function saveToStorage(state) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      threadId: state.threadId,
      status: state.status,
      progress: state.progress,
      errors: state.errors,
    }));
  } catch {
    // Session recovery is best-effort; financial records remain server-side.
  }
}

function loadFromStorage() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function clearStorage() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore unavailable browser storage.
  }
}

function waitForReconnect(milliseconds, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, milliseconds);
    signal.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

export function metricsFor(categorized, deductibility, humanOverrideIds) {
  const overrideIds = new Set(humanOverrideIds);
  const modelOnly = categorized.filter((item) => !overrideIds.has(item.transaction_id));
  const averageModelConfidence = modelOnly.length
    ? Math.round(
      modelOnly.reduce((sum, item) => sum + (Number(item.confidence_score) || 0), 0)
      / modelOnly.length * 100,
    )
    : 0;
  const totalDeductible = deductibility.reduce(
    (sum, item) => sum + (Number(item.allowed_current_period_amount) || 0),
    0,
  );
  return { averageModelConfidence, totalDeductible };
}

const saved = loadFromStorage();

const useRunStore = create((set, get) => ({
  threadId: saved?.threadId || null,
  status: saved?.status || 'idle',
  transactions: [],
  categorized: [],
  deductibilityResults: [],
  pendingClarifications: [],
  unresolvedFlags: [],
  humanOverrideIds: [],
  runTimeline: [],
  auditTrail: [],
  evaluationSummary: null,
  evaluationError: '',
  totalTransactions: 0,
  totalDeductible: 0,
  averageModelConfidence: 0,
  progress: saved?.progress || null,
  errors: saved?.errors || [],
  finalReport: null,
  streamController: null,
  streamState: 'disconnected',
  reconnectAttempt: 0,

  applyServerUpdate: (update) => {
    const current = get();
    const categorized = update.categorized ?? current.categorized;
    const deductibilityResults = (
      update.deductibility_results ?? current.deductibilityResults
    );
    const humanOverrideIds = update.human_override_ids ?? current.humanOverrideIds;
    const calculated = metricsFor(
      categorized,
      deductibilityResults,
      humanOverrideIds,
    );
    const next = {
      status: update.status ?? current.status,
      transactions: update.transactions ?? current.transactions,
      categorized,
      deductibilityResults,
      pendingClarifications: (
        update.pending_clarifications ?? current.pendingClarifications
      ),
      unresolvedFlags: update.unresolved_flags ?? current.unresolvedFlags,
      humanOverrideIds,
      runTimeline: update.run_timeline ?? current.runTimeline,
      auditTrail: update.audit_trail ?? current.auditTrail,
      progress: update.progress ?? current.progress,
      errors: update.errors ?? current.errors,
      finalReport: update.final_report ?? current.finalReport,
      totalTransactions: (update.transactions ?? current.transactions).length
        || current.totalTransactions,
      ...calculated,
    };
    set(next);
    saveToStorage({ ...current, ...next });
  },

  resumeIfNeeded: async () => {
    const { status, threadId } = get();
    if (!threadId || status === 'idle') return false;

    try {
      const snapshot = await apiRequest(`/runs/${threadId}`);
      get().applyServerUpdate(snapshot);
      if (!TERMINAL_STATUSES.has(snapshot.status || status)) {
        get().startStream();
      }
      return true;
    } catch (error) {
      // Active runs retain the existing reconnect loop for temporary outages.
      if (!TERMINAL_STATUSES.has(status)) {
        get().startStream();
        return true;
      }
      set({ errors: [error.message || 'Saved audit could not be restored.'] });
      return false;
    }
  },

  runAudit: async (transactions, { demoScenario = null } = {}) => {
    try {
      if (!Array.isArray(transactions) || transactions.length === 0) {
        throw new Error('At least one validated transaction is required.');
      }
      get().stopStream();
      clearStorage();
      set({
        status: 'loading',
        errors: [],
        progress: null,
        finalReport: null,
        threadId: null,
        transactions: [],
        categorized: [],
        deductibilityResults: [],
        pendingClarifications: [],
        unresolvedFlags: [],
        humanOverrideIds: [],
        runTimeline: [],
        auditTrail: [],
        totalTransactions: transactions.length,
        totalDeductible: 0,
        averageModelConfidence: 0,
      });
      const response = await apiRequest('/run', {
        method: 'POST',
        body: {
          transactions,
          data_processing_consent: true,
          ...(demoScenario ? { demo_scenario: demoScenario } : {}),
        },
        headers: { 'Idempotency-Key': generateIdempotencyKey() },
      });
      set({ threadId: response.run_id, status: response.status });
      saveToStorage({ ...get() });
      get().startStream();
      return true;
    } catch (error) {
      set({ status: 'error', errors: [error.message || 'Failed to start audit.'] });
      return false;
    }
  },

  startStream: () => {
    if (get().streamController || !get().threadId) return;
    const controller = new AbortController();
    set({ streamController: controller, streamState: 'connecting' });

    const connect = async () => {
      let attempt = 0;
      while (!controller.signal.aborted) {
        const runId = get().threadId;
        if (!runId || TERMINAL_STATUSES.has(get().status)) break;
        set({
          streamState: attempt ? 'reconnecting' : 'connecting',
          reconnectAttempt: attempt,
        });
        let receivedEvent = false;
        try {
          await streamRun(runId, {
            signal: controller.signal,
            onEvent: ({ event, data }) => {
              receivedEvent = true;
              attempt = 0;
              set({ streamState: 'connected', reconnectAttempt: 0 });
              if (event === 'snapshot' || event === 'delta') {
                get().applyServerUpdate(data);
              } else if (event === 'error') {
                set({ errors: [data.detail || 'State stream failed.'] });
              }
            },
          });
          if (TERMINAL_STATUSES.has(get().status)) break;
          if (!receivedEvent) throw new Error('State stream ended before sending data.');
          throw new Error('State stream disconnected.');
        } catch (error) {
          if (error.name === 'AbortError' || controller.signal.aborted) break;
          if (error.status === 401 || error.status === 404) {
            set({
              status: 'error',
              streamState: 'disconnected',
              errors: [error.message],
            });
            break;
          }
          attempt += 1;
          const delay = Math.min(1000 * (2 ** (attempt - 1)), 10_000);
          set({
            streamState: 'reconnecting',
            reconnectAttempt: attempt,
            errors: [`Live updates disconnected. Retrying in ${delay / 1000}s.`],
          });
          try {
            await waitForReconnect(delay, controller.signal);
          } catch {
            break;
          }
        }
      }
      if (get().streamController === controller) {
        set({ streamController: null, streamState: 'disconnected' });
      }
    };
    void connect();
  },

  stopStream: () => {
    get().streamController?.abort();
    set({ streamController: null, streamState: 'disconnected', reconnectAttempt: 0 });
  },

  retryStream: () => {
    get().stopStream();
    get().startStream();
  },

  resolveTransaction: async (transactionId, categoryAnswer) => {
    try {
      const response = await apiRequest(`/resume/${get().threadId}`, {
        method: 'POST',
        body: [{ transaction_id: transactionId, answer: categoryAnswer }],
        headers: { 'Idempotency-Key': generateIdempotencyKey() },
      });
      set((state) => ({
        status: response.status,
        pendingClarifications: state.pendingClarifications.filter(
          (item) => (item.transaction_id || item) !== transactionId,
        ),
      }));
      return { ok: true };
    } catch (error) {
      const message = error.message || 'Failed to submit clarification.';
      set((state) => ({ errors: [...state.errors, message] }));
      return { ok: false, error: message };
    }
  },

  cancelAudit: async () => {
    if (!get().threadId) return false;
    try {
      const response = await apiRequest(`/runs/${get().threadId}/cancel`, {
        method: 'POST',
      });
      get().applyServerUpdate(response);
      get().stopStream();
      return true;
    } catch (error) {
      set({ errors: [error.message || 'Failed to cancel audit.'] });
      return false;
    }
  },

  runFailureDemo: async () => get().runAudit(
    [
      {
        date: '2025-03-14',
        merchant: 'GitHub',
        amount: 2499,
        description: 'Team development subscription',
      },
      {
        date: '2025-03-15',
        merchant: 'Unknown Counterparty',
        amount: 1800,
        description: 'Ambiguous business expense requiring review',
      },
    ],
    { demoScenario: 'provider_429_fallback' },
  ),

  loadEvaluation: async () => {
    try {
      const summary = await apiRequest('/evaluation/summary');
      set({ evaluationSummary: summary, evaluationError: '' });
      return summary;
    } catch (error) {
      const message = error.message || 'Evaluation summary is unavailable.';
      set({ evaluationError: message });
      return null;
    }
  },

  resetAudit: async () => {
    const { threadId, status } = get();
    try {
      if (threadId) {
        const active = ['queued', 'running', 'waiting_for_input'].includes(status);
        if (active) await apiRequest(`/runs/${threadId}/cancel`, { method: 'POST' });
        await apiRequest(`/runs/${threadId}`, { method: 'DELETE' });
      }
      get().stopStream();
      clearStorage();
      set({
        threadId: null,
        status: 'idle',
        transactions: [],
        categorized: [],
        deductibilityResults: [],
        pendingClarifications: [],
        unresolvedFlags: [],
        humanOverrideIds: [],
        runTimeline: [],
        auditTrail: [],
        totalTransactions: 0,
        totalDeductible: 0,
        averageModelConfidence: 0,
        progress: null,
        errors: [],
        finalReport: null,
      });
      return true;
    } catch (error) {
      set({ errors: [error.message || 'Failed to reset audit. Retry shortly.'] });
      return false;
    }
  },
}));

export default useRunStore;
