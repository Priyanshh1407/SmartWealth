import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import UploadZone from './UploadZone';

afterEach(cleanup);

describe('UploadZone', () => {
  it('previews a valid CSV and starts only after consent', async () => {
    const user = userEvent.setup();
    const onStartAudit = vi.fn().mockResolvedValue(true);
    render(<UploadZone onStartAudit={onStartAudit} />);
    const file = new File([
      'date,merchant,amount,description\n2025-01-01,"Office, Inc",150,Paper',
    ], 'ledger.csv', { type: 'text/csv' });

    await user.upload(screen.getByLabelText('Choose ledger CSV'), file);
    expect(await screen.findByText('Office, Inc')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: /start validated audit/i });
    expect(start).toBeDisabled();
    await user.click(screen.getByRole('checkbox'));
    await user.click(start);

    expect(onStartAudit).toHaveBeenCalledWith([
      expect.objectContaining({ merchant: 'Office, Inc', amount: 150 }),
    ]);
  });

  it('shows row-specific errors and has no detectable accessibility violations', async () => {
    const user = userEvent.setup();
    const { container } = render(<UploadZone onStartAudit={vi.fn()} />);
    const file = new File([
      'date,merchant,amount,description\nnot-a-date,,0,Invalid',
    ], 'invalid.csv', { type: 'text/csv' });

    await user.upload(screen.getByLabelText('Choose ledger CSV'), file);
    expect(await screen.findByText(/Row 2, date/i)).toBeInTheDocument();
    expect(screen.getByText(/Row 2, merchant/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /start validated audit/i })).toBeDisabled();

    const results = await axe.run(container, {
      rules: { 'color-contrast': { enabled: false } },
    });
    expect(results.violations).toEqual([]);
  });
});

