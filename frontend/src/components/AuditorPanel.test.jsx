import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const resolveTransaction = vi.fn();
const reviseCategory = vi.fn();
const cancelAudit = vi.fn();

vi.mock('../store/useRunStore', () => ({
  default: (selector) => selector({ resolveTransaction, reviseCategory, cancelAudit }),
}));

import AuditorPanel from './AuditorPanel';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AuditorPanel', () => {
  it('keeps the clarification open and offers retry after failure', async () => {
    const user = userEvent.setup();
    resolveTransaction.mockResolvedValue({ ok: false, error: 'Temporary outage' });
    const onResolved = vi.fn();
    render(<AuditorPanel
      transaction={{
        id: 'txn-1',
        transaction_id: 'txn-1',
        amount: 20,
        merchant: 'Unknown',
        clarificationQuestion: 'Choose a category',
      }}
      onResolved={onResolved}
    />);

    await user.selectOptions(screen.getByLabelText(/confirm category/i), 'Office Supplies');
    await user.click(screen.getByRole('button', { name: 'Resolve' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Temporary outage');
    expect(screen.getByRole('button', { name: /retry submission/i })).toBeEnabled();
    expect(onResolved).not.toHaveBeenCalled();
  });
});

describe('AuditorPanel reviewer memory and category changes', () => {
  const nalli = {
    id: 'txn-2',
    transaction_id: 'txn-2',
    amount: 3250,
    merchant: 'Nalli Silks Stationery',
    category: 'Office Supplies',
    confidence: 0.2,
    clarificationQuestion: 'Model confidence 20% is below the 70% review threshold.',
  };

  it('tells the reviewer when one answer covers other rows from the same merchant', () => {
    render(<AuditorPanel transaction={nalli} samePendingMerchantCount={2} onResolved={vi.fn()} />);

    expect(screen.getByText(/also applies to 2 other flagged transactions from Nalli Silks Stationery; they will/))
      .toBeInTheDocument();
    cleanup();

    render(<AuditorPanel transaction={nalli} samePendingMerchantCount={1} onResolved={vi.fn()} />);
    expect(screen.getByText(/1 other flagged transaction from Nalli Silks Stationery; it will/))
      .toBeInTheDocument();
  });

  it('changes a completed row starting from its current category', async () => {
    const user = userEvent.setup();
    reviseCategory.mockResolvedValue({ ok: true });
    const onResolved = vi.fn();
    render(<AuditorPanel
      transaction={{ ...nalli, mode: 'revise', memoryResolved: true }}
      onResolved={onResolved}
    />);

    expect(screen.getByRole('heading', { name: 'Change category' })).toBeInTheDocument();
    expect(screen.getByText(/applied from reviewer memory/)).toBeInTheDocument();
    expect(screen.getByLabelText('New category')).toHaveValue('Office Supplies');
    // Re-submitting the same category is pointless, so it is disabled.
    expect(screen.getByRole('button', { name: 'Apply change' })).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Cancel audit' })).toBeNull();

    await user.selectOptions(screen.getByLabelText('New category'), 'Entertainment');
    await user.click(screen.getByRole('button', { name: 'Apply change' }));

    expect(reviseCategory).toHaveBeenCalledWith('txn-2', 'Entertainment');
    expect(resolveTransaction).not.toHaveBeenCalled();
    expect(onResolved).toHaveBeenCalled();
  });
});
