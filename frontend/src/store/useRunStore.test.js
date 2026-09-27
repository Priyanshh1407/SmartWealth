import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../api/client', () => ({
  apiRequest: vi.fn(),
  streamRun: vi.fn(),
}));

import { apiRequest, streamRun } from '../api/client';
import useRunStore, { metricsFor } from './useRunStore';

const transaction = {
  date: '2025-01-01',
  merchant: 'Office Depot',
  amount: 100,
  description: 'Paper',
};

describe('run store reliability', () => {
  beforeEach(() => {
    useRunStore.getState().stopStream();
    useRunStore.setState(useRunStore.getInitialState(), true);
    sessionStorage.clear();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it('labels model confidence without inflating human-overridden rows', () => {
    const metrics = metricsFor(
      [
        { transaction_id: 'a', confidence_score: 0.8 },
        { transaction_id: 'b', confidence_score: 1 },
      ],
      [{ allowed_current_period_amount: 25 }],
      ['b'],
    );

    expect(metrics).toEqual({ averageModelConfidence: 80, totalDeductible: 25 });
  });

  it('keeps a clear loading state during a slow start request', async () => {
    let finishRequest;
    apiRequest.mockReturnValueOnce(new Promise((resolve) => { finishRequest = resolve; }));
    streamRun.mockImplementation((_runId, { signal }) => new Promise((resolve) => {
      signal.addEventListener('abort', resolve, { once: true });
    }));

    const starting = useRunStore.getState().runAudit([transaction]);
    expect(useRunStore.getState().status).toBe('loading');
    finishRequest({ run_id: 'run-slow', status: 'queued' });
    await starting;

    expect(useRunStore.getState().status).toBe('queued');
    expect(useRunStore.getState().threadId).toBe('run-slow');
    useRunStore.getState().stopStream();
  });

  it('surfaces offline start failures', async () => {
    apiRequest.mockRejectedValueOnce(new Error('Network unavailable'));

    expect(await useRunStore.getState().runAudit([transaction])).toBe(false);
    expect(useRunStore.getState().status).toBe('error');
    expect(useRunStore.getState().errors).toContain('Network unavailable');
  });

  it('rehydrates a completed run from the backend after a browser reload', async () => {
    useRunStore.setState({ threadId: 'run-complete', status: 'completed' });
    apiRequest.mockResolvedValueOnce({
      status: 'completed',
      transactions: [{ transaction_id: 'TXN-1', ...transaction }],
      categorized: [{
        transaction_id: 'TXN-1',
        predicted_category: 'Office Supplies',
        confidence_score: 0.99,
      }],
      deductibility_results: [{
        transaction_id: 'TXN-1',
        treatment: 'deductible',
        allowed_current_period_amount: 100,
      }],
      final_report: { total_transactions_processed: 1 },
    });

    expect(await useRunStore.getState().resumeIfNeeded()).toBe(true);
    expect(apiRequest).toHaveBeenCalledWith('/runs/run-complete');
    expect(useRunStore.getState().transactions).toHaveLength(1);
    expect(useRunStore.getState().totalDeductible).toBe(100);
    expect(useRunStore.getState().finalReport).toEqual({
      total_transactions_processed: 1,
    });
    expect(streamRun).not.toHaveBeenCalled();
  });

  it('runs the controlled failure demo through the normal run endpoint', async () => {
    apiRequest.mockResolvedValueOnce({ run_id: 'demo-run', status: 'queued' });
    streamRun.mockImplementation((_runId, { signal }) => new Promise((resolve) => {
      signal.addEventListener('abort', resolve, { once: true });
    }));

    expect(await useRunStore.getState().runFailureDemo()).toBe(true);
    expect(apiRequest).toHaveBeenCalledWith('/run', expect.objectContaining({
      method: 'POST',
      body: expect.objectContaining({
        demo_scenario: 'provider_429_fallback',
        data_processing_consent: true,
        transactions: expect.any(Array),
      }),
    }));
    useRunStore.getState().stopStream();
  });

  it('keeps clarification pending when submission fails', async () => {
    useRunStore.setState({
      threadId: 'run-1',
      pendingClarifications: [{ transaction_id: 'txn-1', question: 'Choose category' }],
    });
    apiRequest.mockRejectedValueOnce(new Error('Temporary outage'));

    const result = await useRunStore.getState().resolveTransaction('txn-1', 'Office Supplies');

    expect(result).toEqual({ ok: false, error: 'Temporary outage' });
    expect(useRunStore.getState().pendingClarifications).toHaveLength(1);
  });

  it('reconnects the state stream with exponential backoff', async () => {
    vi.useFakeTimers();
    streamRun
      .mockRejectedValueOnce(new Error('connection lost'))
      .mockImplementationOnce(async (_runId, { onEvent }) => {
        onEvent({ event: 'snapshot', data: { status: 'completed', progress: { completed: true } } });
      });
    useRunStore.setState({ threadId: 'run-1', status: 'running' });

    useRunStore.getState().startStream();
    await vi.waitFor(() => expect(useRunStore.getState().streamState).toBe('reconnecting'));
    await vi.advanceTimersByTimeAsync(1000);
    await vi.waitFor(() => expect(streamRun).toHaveBeenCalledTimes(2));

    expect(useRunStore.getState().status).toBe('completed');
    expect(useRunStore.getState().streamController).toBeNull();
  });
});
