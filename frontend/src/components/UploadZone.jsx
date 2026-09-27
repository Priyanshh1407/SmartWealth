import React, { useCallback, useRef, useState } from 'react';
import { MAX_CSV_BYTES, parseLedgerFile } from '../lib/csv';

const EMPTY_RESULT = { rows: [], preview: [], errors: [] };

const UploadZone = ({ onStartAudit }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [consent, setConsent] = useState(false);
  const [fileName, setFileName] = useState('');
  const [result, setResult] = useState(EMPTY_RESULT);
  const [isParsing, setIsParsing] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const fileInputRef = useRef(null);

  const handleFile = useCallback(async (file) => {
    setIsParsing(true);
    setFileName(file?.name || '');
    try {
      setResult(await parseLedgerFile(file));
    } catch {
      setResult({
        rows: [],
        preview: [],
        errors: [{ row: null, field: 'file', message: 'The CSV file could not be read. Try selecting it again.' }],
      });
    } finally {
      setIsParsing(false);
    }
  }, []);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    if (event.dataTransfer.files?.length) void handleFile(event.dataTransfer.files[0]);
  }, [handleFile]);

  const startAudit = async () => {
    if (!consent || result.errors.length || !result.rows.length || isStarting) return;
    setIsStarting(true);
    try {
      await onStartAudit(result.rows);
    } finally {
      setIsStarting(false);
    }
  };

  const handleDownloadTemplate = () => {
    const content = 'date,merchant,amount,description\n2025-01-01,Office Depot,150.00,Office supplies';
    const url = window.URL.createObjectURL(new Blob([content], { type: 'text/csv' }));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'smartwealth_template.csv';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  };

  const ready = Boolean(
    consent && result.rows.length && !result.errors.length && !isParsing,
  );

  return (
    <section
      className={`glass-card rounded-xl flex-1 min-h-0 overflow-y-auto animate-fade-scale transition-all duration-300 ${
        isDragging ? 'border-primary bg-primary/5' : 'border-white/5'
      }`}
      aria-labelledby="upload-title"
      onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
      onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
    >
      <div className="flex justify-between items-center p-md border-b border-white/5">
        <div>
          <h2 id="upload-title" className="font-title-md text-on-surface">Validate Ledger</h2>
          <p className="text-xs text-on-surface-variant mt-1">
            Preview and fix row errors before any data is sent.
          </p>
        </div>
        <span className="text-xs text-outline">Maximum {MAX_CSV_BYTES.toLocaleString()} bytes</span>
      </div>

      <div className="p-md md:p-lg space-y-md">
        <div className="rounded-xl border border-dashed border-white/20 bg-black/20 p-lg text-center">
          <span className="material-symbols-outlined text-primary text-[44px]" aria-hidden="true">
            upload_file
          </span>
          <p className="text-on-surface mt-sm">Drop one CSV here or browse from your device.</p>
          <p className="text-xs text-outline mt-xs">Required columns: date, merchant, amount, description</p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            aria-label="Choose ledger CSV"
            onChange={(event) => {
              if (event.target.files?.length) void handleFile(event.target.files[0]);
            }}
          />
          <div className="mt-md flex flex-wrap justify-center gap-sm">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-md py-sm bg-primary text-on-primary rounded-lg font-label-caps focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              {fileName ? 'Choose another CSV' : 'Browse CSV'}
            </button>
            <button
              type="button"
              onClick={handleDownloadTemplate}
              className="px-md py-sm bg-white/5 text-on-surface rounded-lg border border-white/10 font-label-caps focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              Download template
            </button>
          </div>
          {fileName && <p className="mt-sm text-sm text-secondary">Selected: {fileName}</p>}
          {isParsing && <p role="status" className="mt-sm text-sm text-primary">Validating CSV…</p>}
        </div>

        {result.errors.length > 0 && (
          <div role="alert" aria-live="assertive" className="rounded-lg border border-error/30 bg-error/10 p-md">
            <h3 className="font-semibold text-error">Fix {result.errors.length} validation issue{result.errors.length === 1 ? '' : 's'}</h3>
            <ul className="mt-sm max-h-36 overflow-y-auto space-y-xs text-sm text-on-error-container">
              {result.errors.map((error, index) => (
                <li key={`${error.row}-${error.field}-${index}`}>
                  {error.row ? `Row ${error.row}, ${error.field}: ` : ''}{error.message}
                </li>
              ))}
            </ul>
          </div>
        )}

        {result.preview.length > 0 && (
          <div aria-live="polite">
            <div className="flex items-center justify-between mb-sm">
              <h3 className="font-semibold text-on-surface">Preview</h3>
              <span className="text-xs text-secondary">{result.rows.length} valid row{result.rows.length === 1 ? '' : 's'}</span>
            </div>
            <div className="overflow-x-auto rounded-lg border border-white/10">
              <table className="w-full min-w-[600px] text-sm">
                <thead className="bg-black/30 text-outline">
                  <tr>
                    <th scope="col" className="p-sm text-left">Row</th>
                    <th scope="col" className="p-sm text-left">Date</th>
                    <th scope="col" className="p-sm text-left">Merchant</th>
                    <th scope="col" className="p-sm text-right">Amount</th>
                    <th scope="col" className="p-sm text-left">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {result.preview.map((row, index) => (
                    <tr key={`${row.date}-${row.merchant}-${index}`} className="border-t border-white/5">
                      <td className="p-sm text-outline">{index + 2}</td>
                      <td className="p-sm text-on-surface-variant">{row.date}</td>
                      <td className="p-sm text-on-surface">{row.merchant}</td>
                      <td className="p-sm text-right font-mono">₹{Number(row.amount).toLocaleString()}</td>
                      <td className="p-sm text-on-surface-variant">{row.description || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.rows.length > result.preview.length && (
              <p className="mt-xs text-xs text-outline">Showing the first {result.preview.length} rows.</p>
            )}
          </div>
        )}

        <label className="flex items-start gap-sm text-sm text-on-surface-variant">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            className="mt-1"
          />
          <span>
            I have authority to process this financial data and consent to the configured AI providers and retention policy.
          </span>
        </label>

        <button
          type="button"
          onClick={startAudit}
          disabled={!ready || isStarting}
          className="w-full rounded-lg bg-secondary px-md py-sm font-bold text-on-secondary transition disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary"
        >
          {isStarting ? 'Starting audit…' : 'Start validated audit'}
        </button>
      </div>
    </section>
  );
};

export default UploadZone;
