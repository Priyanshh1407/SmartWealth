import React from 'react';

const percent = (value) => (
  value == null ? 'Not measured' : `${Math.round(value * 1000) / 10}%`
);

const Metric = ({ label, before, after }) => (
  <div className="rounded-lg border border-white/10 bg-black/20 p-sm">
    <p className="font-label-caps text-[9px] text-outline">{label}</p>
    <div className="mt-xs grid grid-cols-2 gap-xs text-sm">
      <span className="text-on-surface-variant">{before}</span>
      <span className="font-semibold text-secondary">{after}</span>
    </div>
  </div>
);

const EvaluationDashboard = ({ summary, error, onClose }) => {
  const before = summary?.before;
  const after = summary?.after;
  const matrix = after?.confusion_matrix;
  return (
    <section className="shrink-0 z-10 max-h-[55vh] overflow-y-auto rounded-xl border border-white/10 bg-background/95 p-md shadow-2xl">
      <div className="flex items-start justify-between gap-md border-b border-white/10 pb-sm">
        <div>
          <p className="font-label-caps text-primary text-[9px]">Versioned evaluation evidence</p>
          <h2 className="font-title-md">Before / after evaluation</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Close evaluation dashboard" className="rounded-full p-xs hover:bg-white/10">
          <span className="material-symbols-outlined">close</span>
        </button>
      </div>

      {error && <p role="alert" className="mt-md rounded-lg border border-error/30 bg-error/10 p-sm text-sm text-error">{error}</p>}
      {!summary && !error && <p role="status" className="mt-md text-sm text-outline">Loading evaluation artifact…</p>}

      {summary && (
        <>
          <div className="mt-md grid gap-sm md:grid-cols-2">
            {[before, after].map((item, index) => (
              <article key={item.label} className="rounded-xl border border-white/10 bg-white/5 p-sm">
                <div className="flex items-center justify-between gap-xs">
                  <h3 className="text-sm font-bold text-on-surface">{item.label}</h3>
                  <span className={`rounded-full px-2 py-1 text-[8px] uppercase ${index ? 'bg-secondary/10 text-secondary' : 'bg-tertiary/10 text-tertiary'}`}>
                    {index ? 'Controlled' : 'Historical'}
                  </span>
                </div>
                <p className="mt-xs text-[10px] leading-4 text-outline">{item.scope}</p>
                <p className="mt-xs font-mono text-[9px] text-outline">{item.source}</p>
              </article>
            ))}
          </div>

          <div className="mt-sm grid gap-sm sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Category accuracy" before={percent(before.categorization_accuracy)} after={percent(after.categorization_accuracy)} />
            <Metric label="Treatment accuracy" before={percent(before.treatment_accuracy)} after={percent(after.treatment_accuracy)} />
            <Metric label="Abstention coverage" before={percent(before.coverage)} after={percent(after.coverage)} />
            <Metric
              label="Retrieval faithfulness"
              before={percent(before.retrieval_faithfulness)}
              after={percent(after.retrieval_faithfulness.faithfulness)}
            />
            <Metric label="Category macro F1" before={percent(before.categorization_macro_f1)} after={percent(after.categorization_macro_f1)} />
            <Metric label="Treatment macro F1" before={percent(before.treatment_macro_f1)} after={percent(after.treatment_macro_f1)} />
            <Metric
              label="Latency"
              before={before.latency_seconds == null ? 'Not measured' : `${before.latency_seconds}s`}
              after={`${after.latency_seconds.toFixed(4)}s`}
            />
            <Metric
              label="Provider cost"
              before={before.estimated_cost_usd == null ? 'Not measured' : `$${before.estimated_cost_usd}`}
              after={`$${after.estimated_cost_usd.toFixed(2)} (provider-free)`}
            />
          </div>

          {matrix && (
            <div className="mt-md overflow-x-auto">
              <h3 className="font-label-caps text-[10px] text-primary">Current categorization confusion matrix</h3>
              <table className="mt-sm min-w-full border-collapse text-center text-[10px]">
                <thead>
                  <tr>
                    <th className="p-xs text-left text-outline">Actual \ predicted</th>
                    {matrix.labels.map((label) => <th key={label} className="p-xs text-outline">{label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {matrix.matrix.map((row, rowIndex) => (
                    <tr key={matrix.labels[rowIndex]} className="border-t border-white/5">
                      <th className="p-xs text-left font-normal text-on-surface-variant">{matrix.labels[rowIndex]}</th>
                      {row.map((value, columnIndex) => (
                        <td key={matrix.labels[columnIndex]} className={`p-xs ${rowIndex === columnIndex ? 'bg-secondary/10 text-secondary' : 'text-outline'}`}>{value}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
};

export default EvaluationDashboard;
