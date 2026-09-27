import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const resolveTransaction = vi.fn();
const cancelAudit = vi.fn();

vi.mock('../store/useRunStore', () => ({
  default: (selector) => selector({ resolveTransaction, cancelAudit }),
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

