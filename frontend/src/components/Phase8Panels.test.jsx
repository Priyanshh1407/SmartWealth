import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import EvidenceDrawer from './EvidenceDrawer';
import EvaluationDashboard from './EvaluationDashboard';
import RunTimeline from './RunTimeline';

const transaction = {
  id: 'TXN-1',
  merchant: 'GitHub',
  treatment: 'deductible',
  reasoning: 'The rule applies to this controlled example.',
  evidence: {
    title: 'Demo rules',
    document_id: 'demo-rules',
    corpus_version: 'v1',
    section: '37(1)',
    page: 2,
    chunk_id: 'demo-rules:1',
    retrieval_score: 0.91,
    passage: 'A sufficiently long controlled passage for evidence display.',
  },
};

describe('Phase 8 interview panels', () => {
  it('opens an accessible evidence dialog and closes with Escape', () => {
    const onClose = vi.fn();
    render(<EvidenceDrawer transaction={transaction} onClose={onClose} />);

    expect(screen.getByRole('dialog', { name: /github/i })).toBeInTheDocument();
    expect(screen.getByText(/supports the deductible treatment/i)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('renders durable timeline and override impact', () => {
    render(
      <RunTimeline
        events={[{
          event_id: 'event-1',
          stage: 'extraction',
          message: 'Controlled fallback succeeded.',
          occurred_at: '2026-09-27T00:00:00Z',
          details: { simulated: true },
        }]}
        auditTrail={[{
          event_id: 'audit-1',
          transaction_id: 'TXN-1',
          prior_prediction: 'Unknown',
          answer: 'Office Supplies',
          downstream_impact: 'Report recalculated.',
          actor: 'local-workspace',
          event_hash: '1234567890abcdef',
          occurred_at: '2026-09-27T00:00:01Z',
        }]}
      />,
    );

    expect(screen.getByText('Controlled simulation')).toBeInTheDocument();
    expect(screen.getByText(/report recalculated/i)).toBeInTheDocument();
  });

  it('labels the evaluation fixture as controlled, not live accuracy', () => {
    const summary = {
      before: {
        label: 'Historical baseline',
        scope: 'Historical result',
        source: 'report',
        categorization_accuracy: 0.2,
        treatment_accuracy: 0.3,
        coverage: null,
        retrieval_faithfulness: null,
        categorization_macro_f1: null,
        treatment_macro_f1: null,
        latency_seconds: null,
        estimated_cost_usd: null,
      },
      after: {
        label: 'Controlled fixture',
        scope: 'This is not a live-model accuracy claim.',
        source: 'fixture',
        categorization_accuracy: 0.8,
        treatment_accuracy: 0.9,
        coverage: 0.75,
        retrieval_faithfulness: { faithfulness: 1 },
        categorization_macro_f1: 0.7,
        treatment_macro_f1: 0.8,
        latency_seconds: 0,
        estimated_cost_usd: 0,
        confusion_matrix: { labels: ['A'], matrix: [[1]] },
      },
    };
    render(<EvaluationDashboard summary={summary} error="" onClose={vi.fn()} />);

    expect(screen.getByText(/not a live-model accuracy claim/i)).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
  });
});
