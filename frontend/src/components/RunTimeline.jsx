import React from 'react';

const STAGE_LABELS = {
  queued: 'Queued',
  starting: 'Started',
  extraction: 'Classify',
  extraction_node: 'Classified',
  auditor_loop: 'Waiting',
  resume: 'Resumed',
  corrective_rag: 'RAG review',
  report: 'Report',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
};

const timeLabel = (value) => {
  if (!value) return '';
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(value));
};

const RunTimeline = ({ events, auditTrail }) => (
  <section
    aria-labelledby="run-timeline-title"
    className="glass-card rounded-xl p-sm overflow-y-auto max-h-[45%] shrink-0"
  >
    <div className="flex items-center justify-between border-b border-white/10 pb-xs">
      <div>
        <p className="font-label-caps text-primary text-[9px]">Durable events</p>
        <h2 id="run-timeline-title" className="font-title-md text-base">Run timeline</h2>
      </div>
      <span className="rounded-full bg-primary/10 px-2 py-1 text-[9px] text-primary">
        {events.length} events
      </span>
    </div>

    <ol className="mt-sm space-y-sm">
      {events.length === 0 && (
        <li className="text-xs text-outline">Timeline events appear after the run is accepted.</li>
      )}
      {events.map((event, index) => (
        <li key={event.event_id} className="relative pl-md">
          {index < events.length - 1 && (
            <span className="absolute left-[5px] top-3 h-[calc(100%+8px)] w-px bg-white/10" />
          )}
          <span className="absolute left-0 top-1 h-2.5 w-2.5 rounded-full border border-primary/50 bg-primary/20" />
          <div className="flex items-start justify-between gap-xs">
            <div>
              <p className="text-xs font-semibold text-on-surface">
                {STAGE_LABELS[event.stage] || event.stage}
              </p>
              <p className="mt-0.5 text-[10px] leading-4 text-on-surface-variant">
                {event.message}
              </p>
              {event.details?.simulated && (
                <span className="mt-1 inline-flex rounded border border-tertiary/30 bg-tertiary/10 px-1.5 py-0.5 text-[8px] uppercase text-tertiary">
                  Controlled simulation
                </span>
              )}
            </div>
            <time className="shrink-0 font-mono text-[9px] text-outline">
              {timeLabel(event.occurred_at)}
            </time>
          </div>
        </li>
      ))}
    </ol>

    {auditTrail.length > 0 && (
      <div className="mt-md border-t border-white/10 pt-sm">
        <p className="font-label-caps text-secondary text-[9px]">Human override audit</p>
        <div className="mt-xs space-y-xs">
          {auditTrail.map((event) => (
            <article key={event.event_id} className="rounded-lg border border-secondary/20 bg-secondary/5 p-xs">
              <div className="flex justify-between gap-xs text-[10px]">
                <span className="font-mono text-secondary">{event.transaction_id}</span>
                <time className="text-outline">{timeLabel(event.occurred_at)}</time>
              </div>
              <p className="mt-1 text-[10px] text-on-surface-variant">
                <span className="text-outline">{event.prior_prediction}</span>
                {' → '}
                <span className="font-semibold text-on-surface">{event.answer}</span>
              </p>
              <p className="mt-1 text-[9px] leading-4 text-outline">{event.downstream_impact}</p>
              <p className="mt-1 font-mono text-[8px] text-outline">
                Actor: {event.actor} · hash {event.event_hash.slice(0, 10)}…
              </p>
            </article>
          ))}
        </div>
      </div>
    )}
  </section>
);

export default RunTimeline;
