import Papa from 'papaparse';

export const MAX_CSV_BYTES = 1_000_000;
export const MAX_CSV_ROWS = 500;
const MAX_TEXT_LENGTH = 500;
const REQUIRED_HEADERS = ['date', 'merchant', 'amount', 'description'];
const ALLOWED_HEADERS = new Set([...REQUIRED_HEADERS, 'transaction_id', 'category']);

function canonicalDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.valueOf())
    && parsed.toISOString().slice(0, 10) === value;
}

function issue(row, field, message) {
  return { row, field, message };
}

export function parseLedgerCsv(text) {
  if (!text || !text.trim()) {
    return { rows: [], preview: [], errors: [issue(null, 'file', 'CSV file is empty.')] };
  }

  const parsed = Papa.parse(text, {
    header: true,
    skipEmptyLines: 'greedy',
    transformHeader: (header) => header.trim().toLowerCase(),
  });
  const errors = parsed.errors.map((error) => issue(
    error.row == null ? null : error.row + 2,
    'csv',
    error.message,
  ));
  const headers = parsed.meta.fields || [];
  for (const header of REQUIRED_HEADERS) {
    if (!headers.includes(header)) {
      errors.push(issue(1, header, `Missing required column: ${header}.`));
    }
  }
  for (const header of headers) {
    if (!ALLOWED_HEADERS.has(header)) {
      errors.push(issue(1, header, `Unexpected column: ${header}.`));
    }
  }
  if (parsed.data.length > MAX_CSV_ROWS) {
    errors.push(issue(null, 'file', `CSV cannot exceed ${MAX_CSV_ROWS} rows.`));
  }

  const rows = parsed.data.slice(0, MAX_CSV_ROWS).map((record, index) => {
    const rowNumber = index + 2;
    const date = String(record.date || '').trim();
    const merchant = String(record.merchant || '').trim();
    const description = String(record.description || '').trim();
    const amountText = String(record.amount || '').trim();
    const amount = Number(amountText);
    if (!canonicalDate(date)) {
      errors.push(issue(rowNumber, 'date', 'Use a real date in YYYY-MM-DD format.'));
    }
    if (!merchant) {
      errors.push(issue(rowNumber, 'merchant', 'Merchant is required.'));
    } else if (merchant.length > MAX_TEXT_LENGTH) {
      errors.push(issue(rowNumber, 'merchant', `Merchant exceeds ${MAX_TEXT_LENGTH} characters.`));
    }
    if (!amountText || !Number.isFinite(amount) || amount <= 0 || amount > 1_000_000_000) {
      errors.push(issue(rowNumber, 'amount', 'Amount must be greater than 0 and at most 1,000,000,000.'));
    }
    if (description.length > MAX_TEXT_LENGTH) {
      errors.push(issue(rowNumber, 'description', `Description exceeds ${MAX_TEXT_LENGTH} characters.`));
    }
    return { date, merchant, amount, description };
  });
  if (!rows.length && !errors.some((error) => error.message.includes('empty'))) {
    errors.push(issue(null, 'file', 'CSV must contain at least one transaction row.'));
  }
  return { rows, preview: rows.slice(0, 10), errors };
}

export async function parseLedgerFile(file) {
  if (!file) return { rows: [], preview: [], errors: [issue(null, 'file', 'Select a CSV file.')] };
  if (!file.name.toLowerCase().endsWith('.csv')) {
    return { rows: [], preview: [], errors: [issue(null, 'file', 'Only .csv files are accepted.')] };
  }
  if (file.size > MAX_CSV_BYTES) {
    return {
      rows: [],
      preview: [],
      errors: [issue(null, 'file', `CSV cannot exceed ${MAX_CSV_BYTES.toLocaleString()} bytes.`)],
    };
  }
  let text;
  if (typeof file.text === 'function') {
    text = await file.text();
  } else {
    text = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('Unable to read the CSV file.'));
      reader.readAsText(file);
    });
  }
  return parseLedgerCsv(text);
}
