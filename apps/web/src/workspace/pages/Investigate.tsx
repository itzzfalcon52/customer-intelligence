import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowUpRight,
  Check,
  CircleAlert,
  FlaskConical,
  History,
  Loader2,
  Search,
  ShieldCheck,
} from 'lucide-react';
import { jobKey, streamPost, type StreamEvent } from '../api';
import { date, model } from '../format';
import { useAction, useAnalyses, useRuns, useScores } from '../queries';
import { useWorkspaceStore } from '../store';
import { TracePanel } from '../trace-ui';
import type { EvidenceItem, Investigation } from '../types';
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Field,
  Notice,
  PageHeader,
  Select,
  Textarea,
  type Tone,
} from '../ui';
import { cn } from '../style';

const SUGGESTIONS = [
  'Which account characteristics are most associated with churn?',
  'Do monthly-billed accounts churn more than annual ones?',
  'Is product usage decline associated with churn?',
];
const STATUS: Record<string, [Tone, string]> = {
  verified: ['success', 'Verified'],
  partial: ['warning', 'Partly verified'],
  unverified: ['danger', 'Unverified'],
};
const pct = (value: unknown) =>
  typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—';
const interval = (value: unknown) =>
  Array.isArray(value) ? `${pct(value[0])} – ${pct(value[1])}` : '—';

/** Live stage timeline built from streamed `stage` events. */
function Timeline({ events }: { events: StreamEvent[] }) {
  const stages = events.filter((e) => e.type === 'stage');
  const last = stages.at(-1);
  const rows: { key: string; text: string; state: 'done' | 'warn' }[] = [];
  for (const e of stages) {
    if (e.name === 'plan' && e.status === 'end')
      for (const h of (e.hypotheses as string[]) ?? [])
        rows.push({
          key: `h-${rows.length}`,
          text: `Hypothesis: ${h}`,
          state: 'done',
        });
    else if (e.name === 'evidence')
      rows.push({
        key: String(e.id),
        text: `${e.id} · ${String(e.tool).replaceAll('_', ' ')}${e.hypothesis ? ` · ${e.hypothesis}` : ''}${e.error ? ` (refused: ${e.error})` : ''}`,
        state: e.error ? 'warn' : 'done',
      });
    else if (e.name === 'follow_up' && e.status !== 'start')
      rows.push({
        key: `f-${rows.length}`,
        text:
          e.status === 'skipped'
            ? 'Follow-up skipped; continuing with gathered evidence'
            : `Follow-up: ${String(e.rationale ?? '')}`,
        state: e.status === 'skipped' ? 'warn' : 'done',
      });
    else if (e.name === 'verify')
      rows.push({
        key: `v-${rows.length}`,
        text: e.passed
          ? 'Verifier: every statement is grounded in evidence'
          : `Verifier objected: ${(e.problems as string[]).join(' · ')}`,
        state: e.passed ? 'done' : 'warn',
      });
  }
  const running =
    last && last.status === 'start'
      ? {
          gather: 'Gathering overview, associations and model summary…',
          plan: 'Planning hypotheses to test…',
          follow_up: 'Deciding whether more checks are needed…',
          write: last.revision ? 'Revising the report…' : 'Writing the report…',
        }[String(last.name)]
      : 'Working…';
  return (
    <ol className="space-y-3" aria-live="polite">
      <AnimatePresence initial={false}>
        {rows.map((row) => (
          <motion.li
            key={row.key}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-start gap-3 text-sm"
          >
            <span
              className={cn(
                'mt-0.5 grid size-5 shrink-0 place-items-center rounded-full',
                row.state === 'warn'
                  ? 'bg-amber-100 text-amber-600'
                  : 'bg-emerald-100 text-emerald-600',
              )}
            >
              {row.state === 'warn' ? (
                <CircleAlert className="size-3" />
              ) : (
                <Check className="size-3" strokeWidth={3} />
              )}
            </span>
            <span className="text-slate-700">{row.text}</span>
          </motion.li>
        ))}
      </AnimatePresence>
      <li className="flex items-center gap-3 text-sm font-medium text-slate-900">
        <Loader2 className="size-5 animate-spin text-brand-600" />
        {running ?? 'Working…'}
      </li>
    </ol>
  );
}

function MiniTable({
  caption,
  head,
  rows,
}: {
  caption: string;
  head: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="overflow-x-auto rounded-xl ring-1 ring-slate-200">
      <p className="border-b border-slate-100 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">
        {caption}
      </p>
      <table className="w-full text-[13px]">
        <thead>
          <tr>
            {head.map((h) => (
              <th
                key={h}
                className="px-3 py-2 text-left text-xs font-medium text-slate-500"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-slate-100">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={cn('px-3 py-2', j > 0 && 'font-mono tabular')}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceTable({ id, item }: { id: string; item: EvidenceItem }) {
  const result = item.result ?? {};
  if (item.error)
    return (
      <p className="text-xs text-rose-600">
        {id}: analysis refused ({item.error})
      </p>
    );
  if (item.tool === 'segment_rates') {
    const rows = (result.segments as Record<string, unknown>[]) ?? [];
    return (
      <MiniTable
        caption={`${id} · churn by ${String(result.column)} (overall ${pct(result.overall_churn_rate)})`}
        head={['Segment', 'Accounts', 'Churn', '95% interval', 'Lift']}
        rows={rows.map((r) => [
          `${String(r.segment)}${r.warning ? ' ⚠' : ''}`,
          String(r.rows),
          pct(r.churn_rate),
          interval(r.churn_rate_95ci),
          r.lift_vs_overall == null ? '—' : `${r.lift_vs_overall}×`,
        ])}
      />
    );
  }
  if (item.tool === 'compare_cohorts') {
    const cohorts = [result.cohort_a, result.cohort_b] as Record<
      string,
      unknown
    >[];
    return (
      <MiniTable
        caption={`${id} · difference ${pct(result.rate_difference)} (95% ${interval(result.rate_difference_95ci)}), p = ${String(result.p_value ?? '—')}`}
        head={['Cohort', 'Accounts', 'Churn', '95% interval']}
        rows={cohorts.map((c) => [
          String(c.label),
          String(c.rows),
          pct(c.churn_rate),
          interval(c.churn_rate_95ci),
        ])}
      />
    );
  }
  if (item.tool === 'rank_associations') {
    const rows = (result.associations as Record<string, unknown>[]) ?? [];
    return (
      <MiniTable
        caption={`${id} · single-feature association strength (Cramér's V)`}
        head={['Feature', 'V', 'Highest churn', 'Lowest churn']}
        rows={rows.map((r) => {
          const high = r.highest_rate_group as
            Record<string, unknown> | undefined;
          const low = r.lowest_rate_group as
            Record<string, unknown> | undefined;
          return [
            String(r.column),
            String(r.cramers_v),
            high ? `${String(high.segment)} · ${pct(high.churn_rate)}` : '—',
            low ? `${String(low.segment)} · ${pct(low.churn_rate)}` : '—',
          ];
        })}
      />
    );
  }
  return (
    <pre className="max-h-64 overflow-auto rounded-xl bg-slate-50 p-3 font-mono text-xs ring-1 ring-slate-200">
      {id} · {item.tool}
      {'\n'}
      {JSON.stringify(result, null, 2)}
    </pre>
  );
}

function Report({ investigation }: { investigation: Investigation }) {
  const [open, setOpen] = useState<string | null>(null);
  const { report, evidence } = investigation;
  const [tone, label] = STATUS[report.status] ?? ['neutral', report.status];
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium text-slate-500">
              {investigation.question}
            </p>
            <h2 className="mt-1 text-xl font-semibold tracking-tight text-balance text-slate-900">
              {report.headline}
            </h2>
          </div>
          <Badge tone={tone} dot>
            <ShieldCheck className="size-3" /> {label}
          </Badge>
        </div>
        <ol className="mt-6 space-y-4">
          {report.findings.map((finding, i) => (
            <li
              key={i}
              className="rounded-xl bg-slate-50/70 p-4 ring-1 ring-slate-200/70"
            >
              <div className="flex gap-3">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-white text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[14.5px] leading-relaxed text-slate-800">
                    {finding.statement}
                  </p>
                  <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    <Badge tone="violet">
                      {finding.kind.replaceAll('_', ' ')}
                    </Badge>
                    {finding.evidence.map((id) => {
                      const key = `${i}:${id}`;
                      return (
                        <button
                          key={id}
                          type="button"
                          aria-expanded={open === key}
                          onClick={() => setOpen(open === key ? null : key)}
                          className={cn(
                            'h-6 cursor-pointer rounded-md px-2 font-mono text-[11px] font-medium ring-1 transition',
                            open === key
                              ? 'bg-slate-900 text-white ring-slate-900'
                              : 'bg-white text-slate-600 ring-slate-200 hover:ring-slate-400',
                          )}
                        >
                          {id}
                        </button>
                      );
                    })}
                  </div>
                  <AnimatePresence>
                    {finding.evidence
                      .filter((id) => open === `${i}:${id}` && evidence[id])
                      .map((id) => (
                        <motion.div
                          key={id}
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="mt-3 overflow-hidden"
                        >
                          <EvidenceTable id={id} item={evidence[id]} />
                        </motion.div>
                      ))}
                  </AnimatePresence>
                </div>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {!!report.caveats.length && (
            <div className="rounded-xl bg-amber-50/70 p-4 ring-1 ring-amber-200/70">
              <p className="text-sm font-semibold text-amber-900">Caveats</p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-[13px] text-amber-900/80">
                {report.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {!!report.next_steps.length && (
            <div className="rounded-xl bg-brand-50/60 p-4 ring-1 ring-brand-200/70">
              <p className="text-sm font-semibold text-brand-900">
                Suggested next steps
              </p>
              <ul className="mt-2 ml-4 list-disc space-y-1 text-[13px] text-brand-900/80">
                {report.next_steps.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {!!report.withheld.length && (
          <details className="mt-4 rounded-xl p-4 ring-1 ring-slate-200">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">
              {report.withheld.length} statement
              {report.withheld.length > 1 ? 's' : ''} withheld by the verifier
            </summary>
            <ul className="mt-3 space-y-2 text-[13px] text-slate-600">
              {report.withheld.map((w, i) => (
                <li key={i}>
                  <span className="line-through decoration-slate-400">
                    {w.statement}
                  </span>
                  <span className="block text-xs text-slate-500">
                    {w.problems.join(' · ')}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
        <p className="mt-4 text-xs text-slate-500">
          {investigation.warning} {investigation.partition}.
        </p>
        <div className="mt-3">
          <TracePanel traceId={investigation.trace_id} />
        </div>
      </Card>
    </motion.div>
  );
}

export function Investigate() {
  const [params] = useSearchParams();
  const runs = useRuns();
  const scores = useScores();
  const usable = runs.data?.filter((r) => !r.error) ?? [];
  const fallback =
    usable.find((r) => r.run_id === scores.data?.[0]?.run_id)?.run_id ??
    usable[0]?.run_id ??
    '';
  const [chosen, setRun] = useState(params.get('run') || '');
  const run = chosen || fallback;
  const [question, setQuestion] = useState('');
  const [selected, setSelected] = useState('');
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const grantConsent = useWorkspaceStore((s) => s.consent);
  const analyses = useAnalyses();
  const past = (analyses.data ?? []).filter(
    (a) => a.kind === 'investigation' && (!run || a.run_id === run),
  ) as unknown as Investigation[];
  const investigate = useAction<Investigation, string>(async (text) => {
    setEvents([]);
    const final = await streamPost(
      '/api/v1/investigations/stream',
      {
        run_id: run,
        question: text,
        provider_consent: true,
        idempotency_key: jobKey(),
      },
      (event) => setEvents((current) => [...current, event]),
    );
    return final.response as Investigation;
  });
  const shown =
    (selected && past.find((p) => p.id === selected)) || investigate.data;
  return (
    <>
      <PageHeader
        eyebrow={
          <Badge tone="violet">
            <FlaskConical className="size-3" /> AI investigation
          </Badge>
        }
        title="Investigate why customers churn"
        description="Ask a question. An agent plans hypotheses, runs statistical analyses on your training data, and a verifier removes any claim the evidence doesn’t support."
      />
      {!usable.length ? (
        <Card>
          <EmptyState
            icon={FlaskConical}
            title="Train a model first"
            description="Investigations analyse the data behind a trained model."
            action={
              <ButtonLink variant="primary" to="/app/models">
                Go to models
              </ButtonLink>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
          <div className="space-y-6">
            <Card title="Your question" icon={Search}>
              <div className="space-y-4">
                <Field label="Data from model">
                  <Select
                    value={run}
                    onChange={(e) => {
                      setRun(e.target.value);
                      setSelected('');
                      investigate.reset();
                    }}
                  >
                    {usable.map((r) => (
                      <option key={r.run_id} value={r.run_id}>
                        {model(r.model)} · {date(r.created_at)}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Textarea
                  value={question}
                  maxLength={1000}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="What do you want to understand about churn?"
                  aria-label="Question"
                />
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-slate-500">
                    Try one of these
                  </p>
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setQuestion(s)}
                      className="flex w-full cursor-pointer items-start gap-2 rounded-lg px-2.5 py-2 text-left text-[13px] text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-slate-900"
                    >
                      <ArrowUpRight className="mt-0.5 size-3.5 shrink-0 text-slate-400" />
                      {s}
                    </button>
                  ))}
                </div>
                {!consent ? (
                  <Button
                    className="w-full"
                    variant="dark"
                    onClick={() => grantConsent()}
                  >
                    Allow sending aggregates to Nebius
                  </Button>
                ) : (
                  <Button
                    className="w-full"
                    variant="primary"
                    icon={FlaskConical}
                    disabled={!run || !question.trim()}
                    loading={investigate.isPending}
                    onClick={() => {
                      setSelected('');
                      void investigate
                        .mutateAsync(question.trim())
                        .catch(() => {});
                    }}
                  >
                    {investigate.isPending ? 'Investigating…' : 'Investigate'}
                  </Button>
                )}
                <p className="text-xs leading-relaxed text-slate-500">
                  Only aggregates (segment rates, column names, model metrics)
                  are sent. The final test rows are never used.
                </p>
              </div>
            </Card>
            {!!past.length && (
              <Card title="Previous investigations" icon={History}>
                <div className="-mx-2 space-y-1">
                  {past.map((p) => {
                    const [tone, label] = STATUS[p.report.status] ?? [
                      'neutral',
                      p.report.status,
                    ];
                    return (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => setSelected(p.id)}
                        className={cn(
                          'flex w-full cursor-pointer flex-col gap-1.5 rounded-lg p-2 text-left transition hover:bg-slate-50',
                          selected === p.id && 'bg-slate-50',
                        )}
                      >
                        <span className="line-clamp-2 text-[13px] font-medium text-slate-800">
                          {p.question}
                        </span>
                        <span className="flex items-center gap-2">
                          <Badge tone={tone}>{label}</Badge>
                          <span className="text-xs text-slate-400">
                            {date(p.created_at)}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </Card>
            )}
          </div>
          <div className="space-y-6">
            <Notice error={investigate.error || runs.error} />
            {investigate.isPending && (
              <Card title="Investigating" description={question}>
                <Timeline events={events} />
              </Card>
            )}
            {shown && !investigate.isPending ? (
              <Report investigation={shown} />
            ) : (
              !investigate.isPending && (
                <Card>
                  <EmptyState
                    icon={FlaskConical}
                    title="Ask a question about churn"
                    description="You’ll see each hypothesis being tested live, then a report where every finding links to the analysis behind it."
                  />
                  <div className="mx-auto grid max-w-2xl gap-3 pb-6 sm:grid-cols-3">
                    {[
                      ['Plan', 'The agent proposes hypotheses to test'],
                      [
                        'Analyse',
                        'Segment rates, cohort comparisons, associations',
                      ],
                      ['Verify', 'Ungrounded or causal claims are withheld'],
                    ].map(([t, d], i) => (
                      <div
                        key={t}
                        className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/70"
                      >
                        <p className="text-xs font-semibold text-brand-700">
                          {i + 1}. {t}
                        </p>
                        <p className="mt-1 text-[13px] text-slate-600">{d}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              )
            )}
          </div>
        </div>
      )}
    </>
  );
}
