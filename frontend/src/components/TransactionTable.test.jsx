import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import TransactionTable from './TransactionTable';

afterEach(cleanup);

const row = (overrides) => ({
  id: 'TXN-1',
  date: '2025-01-01',
  merchant: 'Example',
  amount: 100,
  category: 'Office Supplies',
  confidence: 0.99,
  status: 'awaiting_analysis',
  treatment: undefined,
  evidence: undefined,
  humanOverridden: false,
  ...overrides,
});

function renderRows(transactions, props = {}) {
  render(
    <TransactionTable
      transactions={transactions}
      onResolve={vi.fn()}
      onViewEvidence={vi.fn()}
      {...props}
    />,
  );
  return screen.getAllByRole('row').slice(1);
}

describe('TransactionTable row states', () => {
  it('shows rows awaiting tax analysis without claiming evidence is missing', () => {
    const [tableRow] = renderRows([row({})]);

    expect(within(tableRow).getAllByText('Awaiting tax analysis')).toHaveLength(2);
    expect(within(tableRow).queryByText(/No supporting passage/)).toBeNull();
  });

  it('offers review only for rows the paused run is waiting on', () => {
    const [pending, undetermined] = renderRows([
      row({ id: 'TXN-1', status: 'unresolved', category: 'Unknown', confidence: 0.2 }),
      row({ id: 'TXN-2', status: 'accountant_review', treatment: 'undetermined' }),
    ]);

    expect(within(pending).getByRole('button', { name: 'Review transaction' })).toBeInTheDocument();
    expect(within(pending).getByText('Needs your review')).toBeInTheDocument();
    expect(within(undetermined).queryByRole('button')).toBeNull();
    expect(within(undetermined).getByText('Undetermined')).toBeInTheDocument();
    expect(
      within(undetermined).getByText('No supporting passage · accountant review'),
    ).toBeInTheDocument();
  });
});

describe('TransactionTable reviewer decisions', () => {
  it('marks rows resolved from reviewer memory', () => {
    const [tableRow] = renderRows([row({ memoryResolved: true, treatment: 'deductible' })]);

    expect(within(tableRow).getByText('From reviewer memory')).toBeInTheDocument();
    expect(within(tableRow).queryByText('Human override')).toBeNull();
  });

  it('offers a category change only when the run allows it', () => {
    const onChangeCategory = vi.fn();
    const [withChange] = renderRows(
      [row({ treatment: 'deductible' })],
      { onChangeCategory },
    );
    within(withChange).getByRole('button', { name: /Change category for Example/ }).click();
    expect(onChangeCategory).toHaveBeenCalledWith(expect.objectContaining({ id: 'TXN-1' }));
    cleanup();

    const [withoutChange] = renderRows([row({ treatment: 'deductible' })]);
    expect(within(withoutChange).queryByRole('button', { name: /Change category/ })).toBeNull();
  });
});
