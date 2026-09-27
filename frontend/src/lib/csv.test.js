import { describe, expect, it } from 'vitest';
import { MAX_CSV_BYTES, parseLedgerCsv, parseLedgerFile } from './csv';

describe('ledger CSV validation', () => {
  it('parses quoted commas with the mature parser', () => {
    const result = parseLedgerCsv(
      'date,merchant,amount,description\n2025-01-02,"Office, Inc",125.50,"Paper, pens"',
    );

    expect(result.errors).toEqual([]);
    expect(result.rows).toEqual([{
      date: '2025-01-02',
      merchant: 'Office, Inc',
      amount: 125.5,
      description: 'Paper, pens',
    }]);
  });

  it('reports exact rows and fields for invalid data', () => {
    const result = parseLedgerCsv(
      'date,merchant,amount,description\n2025-02-31,,zero,test',
    );

    expect(result.errors).toEqual(expect.arrayContaining([
      expect.objectContaining({ row: 2, field: 'date' }),
      expect.objectContaining({ row: 2, field: 'merchant' }),
      expect.objectContaining({ row: 2, field: 'amount' }),
    ]));
  });

  it('rejects empty and oversized files before upload', async () => {
    expect(parseLedgerCsv(' ').errors[0].message).toMatch(/empty/i);
    const oversized = new File(
      [new Uint8Array(MAX_CSV_BYTES + 1)],
      'large.csv',
      { type: 'text/csv' },
    );

    const result = await parseLedgerFile(oversized);
    expect(result.errors[0].message).toMatch(/cannot exceed/i);
  });
});

