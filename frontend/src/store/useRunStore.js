import { create } from 'zustand';
import axios from 'axios';

// The base URL for our FastAPI backend
const API_BASE = 'http://localhost:8000/api';

// --- localStorage Persistence ---
const STORAGE_KEY = 'smart-wealth-audit-state';

function saveToStorage(state) {
  try {
    const snapshot = {
      threadId: state.threadId,
      status: state.status,
      transactions: state.transactions,
      categorized: state.categorized,
      deductibilityResults: state.deductibilityResults,
      pendingClarifications: state.pendingClarifications,
      unresolvedFlags: state.unresolvedFlags,
      totalTransactions: state.totalTransactions,
      totalDeductible: state.totalDeductible,
      accuracyScore: state.accuracyScore,
      progress: state.progress,
      errors: state.errors,
      finalReport: state.finalReport,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch (e) {
    // localStorage might be full or unavailable — silently ignore
  }
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

function clearStorage() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    // ignore
  }
}

// --- Initialize from saved state or defaults ---
const saved = loadFromStorage();
const generateThreadId = () => Math.random().toString(36).substring(2, 10);

const useRunStore = create((set, get) => ({
  threadId: saved?.threadId || generateThreadId(),
  status: saved?.status || 'idle',
  
  // Pipeline Data
  transactions: saved?.transactions || [],
  categorized: saved?.categorized || [],
  deductibilityResults: saved?.deductibilityResults || [],
  pendingClarifications: saved?.pendingClarifications || [],
  unresolvedFlags: saved?.unresolvedFlags || [],
  
  // Dashboard Metrics
  totalTransactions: saved?.totalTransactions || 0,
  totalDeductible: saved?.totalDeductible || 0,
  accuracyScore: saved?.accuracyScore || 0,
  
  // Real-time progress from backend
  progress: saved?.progress || null,
  errors: saved?.errors || [],

  // Final report from backend
  finalReport: saved?.finalReport || null,
  
  // Control interval for polling
  pollInterval: null,

  // Auto-resume polling if we were mid-run when the page was reloaded
  resumeIfNeeded: () => {
    const { status } = get();
    if (status === 'running' || status === 'loading' || status === 'paused') {
      console.log('[SmartWealth] Resuming polling after page reload...');
      get().startPolling();
    }
  },

  // Start the Audit
  runAudit: async (csvText) => {
    try {
      if (!csvText) {
         throw new Error("No CSV data provided");
      }
      // Generate a fresh thread ID for each new run
      const newThreadId = generateThreadId();
      set({ 
        status: 'loading', 
        errors: [], 
        progress: null, 
        finalReport: null,
        threadId: newThreadId,
        transactions: [],
        categorized: [],
        deductibilityResults: [],
        pendingClarifications: [],
        unresolvedFlags: [],
        totalDeductible: 0,
        accuracyScore: 0,
      });
      clearStorage();
      
      // Parse CSV
      const rows = csvText.split('\n').slice(1).filter(r => r.trim().length > 0);
      const parsedTxns = rows.map(row => {
        // Simple CSV parse handling commas inside quotes
        const match = row.match(/(\".*?\"|[^",]+)(?=\s*,|\s*$)/g);
        if (!match) return null;
        const [transaction_id, date, merchant, amount, category, description] = match.map(s => s.replace(/(^"|"$)/g, ''));
        return { transaction_id, date, merchant, amount: parseFloat(amount), category, description };
      }).filter(Boolean);

      // The backend now returns immediately and runs graph in background
      await axios.post(`${API_BASE}/run`, {
        thread_id: newThreadId,
        transactions: parsedTxns
      });

      set({ status: 'running', totalTransactions: parsedTxns.length });
      
      // Start polling
      get().startPolling();

    } catch (error) {
      console.error("Failed to start audit", error);
      set({ status: 'error', errors: [error.message || 'Failed to start audit'] });
    }
  },

  // Start polling the backend state
  startPolling: () => {
    if (get().pollInterval) return;
    
    const interval = setInterval(async () => {
      const threadId = get().threadId;
      try {
        const res = await axios.get(`${API_BASE}/state/${threadId}`);
        const data = res.data;
        
        if (data.status === 'not_found') return;

        // Calculate metrics
        const categorized = data.categorized || [];
        const deductibility = data.deductibility_results || [];
        const transactions = data.transactions || [];
        
        // Calculate Total Deductible Amount from actual transaction amounts
        const totalDeductible = deductibility.reduce((sum, item) => {
           if (item.is_deductible) {
               // Find original transaction to get the amount
               const txn = transactions.find(t => t.transaction_id === item.transaction_id);
               if (txn) return sum + txn.amount;
           }
           return sum;
        }, 0);

        // Calculate real accuracy: average confidence of categorized transactions
        const accuracyScore = categorized.length > 0 
          ? Math.round(
              categorized.reduce((sum, c) => sum + (c.confidence_score || 0), 0) 
              / categorized.length * 100
            )
          : 0;

        // Determine the frontend status from backend data
        let newStatus = 'running';
        if (data.status === 'paused') {
          newStatus = 'paused';
        } else if (data.status === 'completed') {
          newStatus = 'completed';
        } else if (data.progress && data.progress.completed) {
          newStatus = 'completed';
        }

        const newState = {
          status: newStatus,
          transactions: transactions,
          categorized: categorized,
          deductibilityResults: deductibility,
          pendingClarifications: data.pending_clarifications || [],
          unresolvedFlags: data.unresolved_flags || [],
          totalDeductible,
          accuracyScore,
          progress: data.progress || null,
          errors: data.errors || [],
          finalReport: data.final_report || null,
        };

        set(newState);

        // Persist to localStorage so reload doesn't lose data
        saveToStorage({ ...get() });

        // Stop polling if completed
        if (newStatus === 'completed') {
          get().stopPolling();
        }

      } catch (err) {
        console.error("Polling error", err);
      }
    }, 2000);
    
    set({ pollInterval: interval });
  },

  stopPolling: () => {
    const interval = get().pollInterval;
    if (interval) {
      clearInterval(interval);
      set({ pollInterval: null });
    }
  },

  // Resolve a single transaction
  resolveTransaction: async (transactionId, categoryAnswer) => {
    const threadId = get().threadId;
    try {
      await axios.post(`${API_BASE}/resume/${threadId}`, [
        {
          transaction_id: transactionId,
          answer: categoryAnswer
        }
      ]);
      
      // Instantly remove from pending locally to make UI snappy
      set((state) => ({
        pendingClarifications: state.pendingClarifications.filter(p => {
           const tId = p.transaction_id || p;
           return tId !== transactionId;
        })
      }));
      
    } catch (error) {
      console.error("Failed to resume transaction", error);
    }
  },

  // Reset everything — clear backend checkpoints + frontend state
  resetAudit: async () => {
    try {
      // Stop any active polling
      get().stopPolling();

      // Tell backend to clear SQLite checkpoints
      await axios.post(`${API_BASE}/reset`);
      
      // Clear localStorage
      clearStorage();
      
      // Reset all store state
      set({
        threadId: generateThreadId(),
        status: 'idle',
        transactions: [],
        categorized: [],
        deductibilityResults: [],
        pendingClarifications: [],
        unresolvedFlags: [],
        totalTransactions: 0,
        totalDeductible: 0,
        accuracyScore: 0,
        progress: null,
        errors: [],
        finalReport: null,
        pollInterval: null,
      });
      
      console.log('[SmartWealth] Audit reset complete.');
    } catch (error) {
      console.error("Failed to reset audit", error);
    }
  }

}));

export default useRunStore;
