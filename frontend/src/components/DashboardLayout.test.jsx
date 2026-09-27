import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Dashboard from './Dashboard';

vi.mock('../api/client', () => ({
  healthCheck: vi.fn().mockResolvedValue({ status: 'ok' }),
}));

vi.mock('../store/useRunStore', () => ({
  default: () => ({
    status: 'completed',
    transactions: [{
      transaction_id: 'TXN-1',
      date: '2025-01-01',
      merchant: 'Example',
      amount: 100,
      description: 'Office supplies',
    }],
    categorized: [{
      transaction_id: 'TXN-1',
      predicted_category: 'Office Supplies',
      confidence_score: 0.99,
    }],
    deductibilityResults: [{
      transaction_id: 'TXN-1',
      treatment: 'deductible',
      allowed_current_period_amount: 100,
      requires_accountant_review: false,
      reasoning: 'The documented office-expense rule applies.',
      evidence: {
        title: 'Controlled tax rules',
        document_id: 'controlled-tax-rules',
        corpus_version: 'offline-demo-v1',
        section: 'Section 37',
        page: 2,
        chunk_id: 'controlled-tax-rules:office-supplies',
        retrieval_score: 0.99,
        passage: 'Office supplies used for business are supported by this controlled passage.',
      },
    }],
    pendingClarifications: [],
    totalTransactions: 1,
    totalDeductible: 0,
    averageModelConfidence: 99,
    humanOverrideIds: [],
    runTimeline: [],
    auditTrail: [],
    evaluationSummary: null,
    evaluationError: null,
    progress: { processed: 1, total: 1, message: 'Complete' },
    errors: [],
    finalReport: null,
    runAudit: vi.fn(),
    resetAudit: vi.fn(),
    cancelAudit: vi.fn(),
    streamState: 'connected',
    reconnectAttempt: 0,
    retryStream: vi.fn(),
    runFailureDemo: vi.fn(),
    loadEvaluation: vi.fn(),
  }),
}));

afterEach(cleanup);

describe('Dashboard loaded-ledger layout', () => {
  it('allows document scrolling and provides a keyboard-focusable ledger scroller', () => {
    render(<Dashboard />);

    const shell = screen.getByTestId('dashboard-shell');
    expect(shell.className).not.toContain('lg:h-[');
    expect(shell.className).not.toContain('lg:overflow-hidden');

    const ledger = screen.getByRole('region', {
      name: 'Scrollable transaction ledger',
    });
    expect(ledger).toHaveAttribute('tabindex', '0');
    expect(ledger).toHaveClass('flex-1', 'min-h-0', 'max-h-[65vh]', 'overflow-auto');
  });

  it('opens populated evidence in a viewport-level portal from the ledger button', async () => {
    const user = userEvent.setup();
    render(<Dashboard />);

    await user.click(screen.getByRole('button', { name: 'Open evidence drawer' }));

    const dialog = screen.getByRole('dialog', { name: 'Example' });
    expect(dialog).toBeVisible();
    expect(dialog).toHaveClass('w-full', 'max-w-[36rem]');
    expect(dialog).not.toHaveClass('max-w-xl');
    expect(screen.getByText('Controlled tax rules')).toBeVisible();
    expect(screen.getByText('Section 37')).toBeVisible();
    expect(screen.getByText(/Office supplies used for business/)).toBeVisible();
    expect(dialog.parentElement?.parentElement).toBe(document.body);
  });
});
