import { useState } from 'react';
import { ShieldCheck, Sparkles } from 'lucide-react';
import { post } from './api';
import { useAction } from './queries';
import { useAIAction } from './retention-hooks';
import { useWorkspaceStore } from './store';
import type { Task } from './types';
import { Badge, Button, Card, Confirm, Notice } from './ui';
import { cn } from './style';

/** Explicit provider consent; nothing reaches Nebius until this is on. */
export function ProviderConsent({ personal = false }: { personal?: boolean }) {
  const accepted = useWorkspaceStore((s) => s.providerConsent);
  const consent = useWorkspaceStore((s) => s.consent);
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-3 rounded-xl p-3.5 text-[13px] leading-relaxed ring-1 transition-colors',
        accepted
          ? 'bg-brand-50/60 text-slate-700 ring-brand-200'
          : 'bg-slate-50 text-slate-600 ring-slate-200',
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 accent-brand-600"
        checked={accepted}
        onChange={(e) => consent(e.target.checked)}
      />
      <span>
        <span className="font-medium text-slate-900">
          Allow AI processing.{' '}
        </span>
        Nemotron on Nebius may see this request’s schema, computed results and
        instructions.
        {personal
          ? ' Drafting also sends the feature values you select below for up to five customers; names and IDs stay here.'
          : ' Raw customer rows are never sent.'}
      </span>
    </label>
  );
}

export interface SchemaResult {
  id: string;
  task_id: string;
  summary: string;
  proposed_features: string[];
  questions: string[];
  findings: { column: string; decision: string; reason: string }[];
  warning: string;
}

export function SchemaReview({
  taskId,
  onApplied,
}: {
  taskId: string;
  onApplied: (id: string) => void;
}) {
  return (
    <SchemaReviewForm key={taskId} taskId={taskId} onApplied={onApplied} />
  );
}

function SchemaReviewForm({
  taskId,
  onApplied,
}: {
  taskId: string;
  onApplied: (id: string) => void;
}) {
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const review = useAIAction<SchemaResult>('/api/v1/retention/schema-review');
  const [confirmed, setConfirmed] = useState(false);
  const apply = useAction<Task, string>((review_id) =>
    post('/api/v1/retention/apply-schema', {
      review_id,
      features_available_at_prediction: true,
    }),
  );
  async function confirm() {
    if (!review.data) return;
    try {
      const task = await apply.mutateAsync(review.data.id);
      onApplied(task.id);
    } catch {
      /* rendered */
    }
  }
  return (
    <Card
      title="AI input review"
      description="Optional: catch outcome dates, IDs and ambiguous fields before training."
      icon={Sparkles}
      action={<Badge tone="violet">Optional</Badge>}
    >
      <div className="space-y-4">
        <ProviderConsent />
        <Button
          icon={Sparkles}
          disabled={!consent}
          loading={review.isPending}
          onClick={() => review.mutate({ task_id: taskId })}
        >
          {review.isPending
            ? 'Reviewing inputs…'
            : 'Review inputs with Nemotron'}
        </Button>
        <Notice error={review.error || apply.error} />
        {review.data && (
          <div className="space-y-4" aria-live="polite">
            <p className="text-sm leading-relaxed text-slate-700">
              {review.data.summary}
            </p>
            <div className="divide-y divide-slate-100 rounded-xl ring-1 ring-slate-200">
              {review.data.findings.map((f) => (
                <div key={f.column} className="flex items-start gap-3 p-3">
                  <Badge
                    tone={
                      f.decision === 'keep'
                        ? 'success'
                        : f.decision === 'exclude'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {f.decision}
                  </Badge>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">
                      {f.column}
                    </p>
                    <p className="text-[13px] text-slate-500">{f.reason}</p>
                  </div>
                </div>
              ))}
            </div>
            {review.data.questions.length > 0 && (
              <ul className="ml-5 list-disc space-y-1 text-[13px] text-slate-600">
                {review.data.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            )}
            <p className="text-xs text-slate-500">{review.data.warning}</p>
            <Confirm checked={confirmed} onChange={setConfirmed}>
              I reviewed these exclusions and confirm the remaining inputs exist
              before the outcome.
            </Confirm>
            <Button
              variant="primary"
              icon={ShieldCheck}
              disabled={!confirmed || !review.data.proposed_features.length}
              loading={apply.isPending}
              onClick={() => void confirm()}
            >
              Use reviewed inputs
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
