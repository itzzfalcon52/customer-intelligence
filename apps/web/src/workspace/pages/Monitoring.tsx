import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  Activity,
  CalendarClock,
  Crown,
  Gauge,
  OctagonPause,
  Play,
  Radar,
  RotateCcw,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { post, request } from '../api';
import { date, metric, model, number } from '../format';
import { useAction, useIdentity, useResource, useRuns } from '../queries';
import type { Job, RunSummary } from '../types';
import { Bars } from '../charts';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Select,
  Stat,
  type Tone,
} from '../ui';

interface Report {
  id: string;
  kind: 'drift' | 'performance' | 'lift';
  run_id: string;
  score_id: string | null;
  status: 'stable' | 'watch' | 'alert';
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}
interface Autonomy {
  level: 'observe' | 'recommend' | 'act_with_approval';
  paused: boolean;
  daily_token_budget: number | null;
  daily_action_quota: number;
  ai_briefs: boolean;
  usage: {
    tokens_today: number;
    daily_token_budget: number | null;
    proposals_last_24h: number;
    daily_action_quota: number;
  };
}
interface Schedule {
  enabled: boolean;
  cadence_hours: number;
  connection_id: string | null;
  source_id: string | null;
  horizon_days: number;
  contact_count: number;
  holdout_rate: number;
  next_run_at: string | null;
  last_run_at: string | null;
}
interface Registry {
  run_id: string | null;
  history: { run_id: string | null; action: string; at: string }[];
}

const STATUS: Record<Report['status'], [string, Tone]> = {
  stable: ['Stable', 'success'],
  watch: ['Watch', 'warning'],
  alert: ['Alert', 'danger'],
};
const LEVELS: [Autonomy['level'], string, string][] = [
  [
    'observe',
    'Just report',
    'Re-score, check for changes and write a summary to your Inbox.',
  ],
  [
    'recommend',
    'Suggest',
    'Also name the accounts to look at first and a matching playbook passage.',
  ],
  [
    'act_with_approval',
    'Ask me before acting',
    'Also propose retraining when something changes a lot. Nothing runs until you approve.',
  ],
];
const KIND_TITLE: Record<Report['kind'], string> = {
  drift: 'Did customers change?',
  performance: 'How did predictions hold up?',
  lift: 'Did outreach work?',
};
const HEADLINE: Record<Report['status'], string> = {
  stable: 'Customers look like the ones the model learned from.',
  watch: 'Some customer traits have shifted. Keep an eye on results.',
  alert:
    'Customers have changed noticeably since the model was trained. Consider retraining it on newer data.',
};

export function Monitoring() {
  const registry = useResource<Registry>('/api/v1/registry');
  const runs = useRuns();
  const reports = useResource<Report[]>('/api/v1/monitoring');
  const rollback = useAction<Registry, undefined>(() =>
    post('/api/v1/registry/rollback', {}),
  );
  const active = runs.data?.find((r) => r.run_id === registry.data?.run_id);
  return (
    <div className="space-y-6">
      <PageHeader
        title="Results"
        description="What happened after scoring: whether your customers changed since the model was trained, and how well its predictions held up once real outcomes came in."
      />
      {reports.data?.[0] && (
        <Alert
          tone={
            reports.data[0].status === 'stable'
              ? 'success'
              : reports.data[0].status === 'watch'
                ? 'info'
                : 'warning'
          }
          title={HEADLINE[reports.data[0].status]}
          action={
            <ButtonLink size="sm" to={`/app/monitoring/${reports.data[0].id}`}>
              See why
            </ButtonLink>
          }
        >
          Latest check {date(reports.data[0].created_at)}.
        </Alert>
      )}
      <Notice error={registry.error || reports.error || rollback.error} />
      <div className="grid gap-4 md:grid-cols-3">
        <ActiveModel
          registry={registry.data}
          active={active}
          onRollback={() => rollback.mutate(undefined)}
          rolling={rollback.isPending}
        />
        <Stat
          label="Latest check"
          icon={Radar}
          value={
            reports.data?.[0] ? (
              <Badge tone={STATUS[reports.data[0].status][1]} dot>
                {STATUS[reports.data[0].status][0]}
              </Badge>
            ) : (
              '—'
            )
          }
          hint={
            reports.data?.[0]
              ? date(reports.data[0].created_at)
              : 'No checks have run yet'
          }
        />
        <Stat
          label="Checks recorded"
          icon={Activity}
          value={number(reports.data?.length ?? 0)}
          hint="Change checks and outcome reports"
        />
      </div>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-6">
          <OutreachResult
            report={reports.data?.find((r) => r.kind === 'lift')}
          />
          <ScheduleCard hasModel={Boolean(registry.data?.run_id)} />
          <Card
            title="Checks"
            icon={Gauge}
            description="Every check asks whether customers changed. Once outcomes for an earlier batch are known, a second report shows how the predictions held up."
          >
            {reports.isPending ? (
              <Loading label="Loading reports" />
            ) : reports.data?.length ? (
              <ul className="-my-2 divide-y divide-slate-100">
                {reports.data.map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/app/monitoring/${r.id}`}
                      className="flex items-start gap-3 rounded-lg py-3 transition-colors hover:bg-slate-50"
                    >
                      <Badge tone={STATUS[r.status][1]} dot>
                        {STATUS[r.status][0]}
                      </Badge>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium text-slate-900">
                          {KIND_TITLE[r.kind]}
                        </span>
                        <span className="line-clamp-2 block text-xs text-slate-500">
                          {r.summary}
                        </span>
                      </span>
                      <span className="shrink-0 text-xs text-slate-400">
                        {date(r.created_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                compact
                icon={Radar}
                title="No checks yet"
                description="Choose an active model and a data source, then run a check."
              />
            )}
          </Card>
        </div>
        <AutonomyCard />
      </div>
    </div>
  );
}

function ActiveModel({
  registry,
  active,
  onRollback,
  rolling,
}: {
  registry?: Registry;
  active?: RunSummary;
  onRollback: () => void;
  rolling: boolean;
}) {
  const canRollBack = (registry?.history ?? []).some(
    (h) => h.action === 'promoted' && h.run_id && h.run_id !== registry?.run_id,
  );
  return (
    <Stat
      label="Active model"
      icon={Crown}
      tone="brand"
      value={
        registry?.run_id ? (
          <Link
            className="hover:text-brand-700"
            to={`/app/models/${registry.run_id}`}
          >
            {active ? model(active.model) : registry.run_id.slice(0, 8)}
          </Link>
        ) : (
          'None'
        )
      }
      hint={
        registry?.run_id ? (
          <span className="flex items-center gap-2">
            Used by scheduled scoring
            {canRollBack && (
              <button
                className="inline-flex items-center gap-1 font-medium text-brand-700 hover:underline disabled:opacity-50"
                onClick={onRollback}
                disabled={rolling}
              >
                <RotateCcw className="size-3" /> Roll back
              </button>
            )}
          </span>
        ) : (
          <Link className="font-medium text-brand-700" to="/app/models">
            Open a model and choose “Make active”
          </Link>
        )
      }
    />
  );
}

function ScheduleCard({ hasModel }: { hasModel: boolean }) {
  const navigate = useNavigate();
  const schedule = useResource<Schedule>('/api/v1/schedule');
  const sources =
    useResource<{ id: string; name: string; kind: string }[]>(
      '/api/v1/sources',
    );
  const connections = useResource<{
    connections: { id: string; provider: string; label: string }[];
  }>('/api/v1/connections');
  const identity = useIdentity();
  const canManage = identity.data?.can_manage ?? false;
  const [draft, setForm] = useState<Schedule | null>(null);
  const form = draft ?? schedule.data ?? null;
  const save = useAction<Schedule, Schedule>((value) =>
    request('/api/v1/schedule', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: value.enabled,
        cadence_hours: value.cadence_hours,
        connection_id: value.connection_id,
        source_id: value.source_id,
        horizon_days: value.horizon_days,
        contact_count: value.contact_count,
        holdout_rate: value.holdout_rate,
      }),
    }),
  );
  const run = useAction<Job, undefined>(() => post('/api/v1/schedule/run', {}));
  if (!form) return <Loading label="Loading schedule" />;
  const origin = form.connection_id
    ? `c:${form.connection_id}`
    : form.source_id
      ? `s:${form.source_id}`
      : '';
  const ready = hasModel && Boolean(origin);
  async function runNow() {
    try {
      await save.mutateAsync(form!);
      await run.mutateAsync(undefined);
      navigate('/app/jobs');
    } catch {
      /* rendered */
    }
  }
  return (
    <Card
      title="Automatic check"
      icon={CalendarClock}
      description="Re-scores your latest data with the active model, looks for changes and posts a summary to your Inbox."
      action={
        schedule.data?.enabled ? (
          <Badge tone="success" dot>
            On
          </Badge>
        ) : (
          <Badge>Off</Badge>
        )
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Data to check"
          hint="Each check re-scores this data source with the active model."
        >
          <Select
            value={origin}
            onChange={(e) => {
              const v = e.target.value;
              setForm({
                ...form,
                connection_id: v.startsWith('c:') ? v.slice(2) : null,
                source_id: v.startsWith('s:') ? v.slice(2) : null,
              });
            }}
          >
            <option value="">Choose…</option>
            {Boolean(connections.data?.connections.length) && (
              <optgroup label="Live connections (fresh data every check)">
                {connections.data?.connections.map((c) => (
                  <option key={c.id} value={`c:${c.id}`}>
                    {c.label} ({c.provider === 'stripe' ? 'Stripe' : 'HubSpot'})
                  </option>
                ))}
              </optgroup>
            )}
            <optgroup label="Saved sources (the same data each time)">
              {sources.data
                ?.filter(
                  (s) =>
                    !['stripe', 'hubspot', 'stripe+hubspot'].includes(s.kind),
                )
                .map((s) => (
                  <option key={s.id} value={`s:${s.id}`}>
                    {s.name}
                  </option>
                ))}
            </optgroup>
          </Select>
        </Field>
        <Field label="How often">
          <Select
            value={form.cadence_hours}
            onChange={(e) =>
              setForm({ ...form, cadence_hours: Number(e.target.value) })
            }
          >
            <option value={24}>Daily</option>
            <option value={168}>Weekly</option>
            <option value={720}>Every 30 days</option>
          </Select>
        </Field>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-600 select-none hover:text-slate-900">
          Customize: {form.horizon_days}-day window, {form.contact_count}{' '}
          accounts per check
        </summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <Field
            label="Prediction horizon (days)"
            hint="Match the horizon the active model was trained for."
          >
            <Input
              type="number"
              min={14}
              max={365}
              value={form.horizon_days}
              onChange={(e) =>
                setForm({ ...form, horizon_days: Number(e.target.value) })
              }
            />
          </Field>
          <Field label="Accounts to contact per check">
            <Input
              type="number"
              min={1}
              max={50000}
              value={form.contact_count}
              onChange={(e) =>
                setForm({ ...form, contact_count: Number(e.target.value) })
              }
            />
          </Field>
          <div className="sm:col-span-2">
            <Checkbox
              checked={form.holdout_rate > 0}
              onChange={(on) =>
                setForm({ ...form, holdout_rate: on ? 0.2 : 0 })
              }
              description="A random 20% of each contact list is marked “don’t contact”, so later checks can measure whether outreach worked."
            >
              Hold back 20% for comparison
            </Checkbox>
          </div>
        </div>
      </details>
      <div className="mt-4">
        <Checkbox
          checked={form.enabled}
          onChange={(enabled) => setForm({ ...form, enabled })}
          description={
            schedule.data?.next_run_at
              ? `Next check ${date(schedule.data.next_run_at)}. The worker (pnpm worker:api) must be running.`
              : 'The worker (pnpm worker:api) must be running.'
          }
        >
          Run on a schedule
        </Checkbox>
      </div>
      {form.connection_id ? (
        <p className="mt-4 text-[13px] text-slate-600">
          Each check pulls the latest data from this connection, re-scores every
          account and writes the brief. Retraining waits for an admin’s
          approval.
        </p>
      ) : (
        form.source_id && (
          <p className="mt-4 text-[13px] text-slate-600">
            A saved source never changes, so every check scores the same
            accounts. Connect Stripe on the Data sources page for daily data.
          </p>
        )
      )}
      {!hasModel && (
        <Alert tone="info" className="mt-4">
          Choose an active model first. Scheduled checks only ever score with
          the model you made active.
        </Alert>
      )}
      <Notice error={save.error || run.error} />
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        {canManage && (
          <Button
            loading={save.isPending && !run.isPending}
            onClick={() => save.mutate(form)}
          >
            Save schedule
          </Button>
        )}
        <Button
          variant="primary"
          icon={Play}
          disabled={!ready}
          loading={run.isPending}
          onClick={() => void runNow()}
        >
          Run a check now
        </Button>
      </div>
    </Card>
  );
}

function AutonomyCard() {
  const current = useResource<Autonomy>('/api/v1/autonomy');
  const [draft, setForm] = useState<Autonomy | null>(null);
  const form = draft ?? current.data ?? null;
  const identity = useIdentity();
  const canManage = identity.data?.can_manage ?? false;
  const save = useAction<Autonomy, Partial<Autonomy>>((value) =>
    request('/api/v1/autonomy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level: value.level,
        paused: value.paused,
        daily_token_budget: value.daily_token_budget,
        daily_action_quota: value.daily_action_quota,
        ai_briefs: value.ai_briefs,
      }),
    }),
  );
  if (!form || !current.data) return <Loading label="Loading guardrails" />;
  const usage = current.data.usage;
  async function apply(change: Partial<Autonomy>) {
    const next = { ...form!, ...change };
    setForm(next);
    try {
      await save.mutateAsync(next);
    } catch {
      /* rendered */
    }
  }
  return (
    <div className="h-fit space-y-6">
      <Card
        title="Automation"
        icon={ShieldCheck}
        description="How much the scheduled check may do on its own. It never contacts customers, whatever the setting."
      >
        {!canManage && (
          <p className="mb-3 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500 ring-1 ring-slate-200">
            Only team owners and admins can change automation.
          </p>
        )}
        <fieldset disabled={!canManage} className="disabled:opacity-60">
          <div
            className="space-y-2"
            role="radiogroup"
            aria-label="Autonomy level"
          >
            {LEVELS.map(([value, label, hint]) => (
              <button
                key={value}
                role="radio"
                aria-checked={form.level === value}
                onClick={() => void apply({ level: value })}
                className={
                  'block w-full rounded-xl p-3 text-left ring-1 transition ' +
                  (form.level === value
                    ? 'bg-brand-50/70 ring-brand-300'
                    : 'ring-slate-200 hover:ring-slate-300')
                }
              >
                <span className="block text-sm font-semibold text-slate-900">
                  {label}
                </span>
                <span className="block text-xs text-slate-500">{hint}</span>
              </button>
            ))}
          </div>
          <details className="mt-5">
            <summary className="cursor-pointer text-sm font-medium text-slate-600 select-none hover:text-slate-900">
              Limits: {form.daily_action_quota} proposals a day
              {form.daily_token_budget
                ? `, ${number(form.daily_token_budget)} AI tokens a day`
                : ', no AI token limit'}
            </summary>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Field
                label="Daily AI tokens"
                hint={`${number(usage.tokens_today)} used today`}
              >
                <Input
                  type="number"
                  min={1000}
                  placeholder="No limit"
                  value={form.daily_token_budget ?? ''}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      daily_token_budget: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                  onBlur={() => void apply({})}
                />
              </Field>
              <Field
                label="Proposals per day"
                hint={`${usage.proposals_last_24h} in the last 24 h`}
              >
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={form.daily_action_quota}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      daily_action_quota: Number(e.target.value),
                    })
                  }
                  onBlur={() => void apply({})}
                />
              </Field>
            </div>
          </details>
          <Notice error={save.error} />
          <div
            className={
              'mt-5 flex items-center gap-3 rounded-xl p-3 ring-1 ' +
              (form.paused
                ? 'bg-rose-50 ring-rose-200'
                : 'bg-slate-50 ring-slate-200')
            }
          >
            <OctagonPause
              className={
                'size-5 shrink-0 ' +
                (form.paused ? 'text-rose-600' : 'text-slate-400')
              }
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">
                {form.paused ? 'Paused' : 'Kill switch'}
              </p>
              <p className="text-xs text-slate-500">
                Stops AI calls, scheduled checks and new proposals immediately.
              </p>
            </div>
            <Button
              size="sm"
              variant={form.paused ? 'primary' : 'danger'}
              onClick={() => void apply({ paused: !form.paused })}
            >
              {form.paused ? 'Resume' : 'Pause all'}
            </Button>
          </div>
          <div className="mt-4">
            <Checkbox
              checked={form.ai_briefs}
              onChange={(on) => void apply({ ai_briefs: on })}
              description="After every automatic check, Nemotron writes a checked brief and notes for the top accounts. It sees computed results and pseudonymous labels, never raw rows or real IDs."
            >
              Nemotron brief after each check
            </Checkbox>
          </div>
        </fieldset>
      </Card>
      <div className="flex items-center gap-3 rounded-2xl bg-white p-5 shadow-card ring-1 ring-slate-200/80">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">Email digest</p>
          <p className="text-xs text-slate-500">
            Each person turns it on for themselves in Settings. Slack is coming
            soon.
          </p>
        </div>
        <ButtonLink size="sm" to="/app/settings#email">
          Email settings
        </ButtonLink>
      </div>
    </div>
  );
}

interface Feature {
  feature: string;
  psi: number;
  band: Report['status'];
  reference_missing: number;
  current_missing: number;
}

export function MonitorReportDetail() {
  const { id = '' } = useParams();
  const report = useResource<Report>(`/api/v1/monitoring/${id}`);
  if (report.isPending) return <Loading label="Loading report" />;
  if (!report.data) return <Notice error={report.error} />;
  const r = report.data;
  const p = r.payload as Record<string, never>;
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/app/monitoring', label: 'Results' }}
        title={
          <span className="flex items-center gap-3">
            {KIND_TITLE[r.kind]}
            {r.kind !== 'lift' && (
              <Badge tone={STATUS[r.status][1]} dot>
                {STATUS[r.status][0]}
              </Badge>
            )}
          </span>
        }
        description={`${r.summary} Recorded ${date(r.created_at)}.`}
        actions={
          <>
            <ButtonLink variant="ghost" to={`/app/models/${r.run_id}`}>
              Model
            </ButtonLink>
            {r.score_id && (
              <ButtonLink variant="secondary" to={`/app/scores/${r.score_id}`}>
                Scores
              </ButtonLink>
            )}
          </>
        }
      />
      {r.kind === 'drift' ? (
        <Drift p={p} />
      ) : r.kind === 'lift' ? (
        <Lift p={p} />
      ) : (
        <Performance p={p} />
      )}
    </div>
  );
}

function Drift({ p }: { p: Record<string, never> }) {
  const features = (p.features ?? []) as Feature[];
  const shift = p.score_shift as {
    psi: number;
    band: Report['status'];
    previous_median: number;
    current_median: number;
    previous_score_id: string;
  } | null;
  const reference = p.reference as { rows: number };
  const current = p.current as { rows: number };
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          label="Inputs that moved"
          value={`${features.filter((f) => f.band !== 'stable').length} of ${features.length}`}
          hint="PSI above 0.1"
        />
        <Stat
          label="Compared"
          value={`${number(current.rows)} vs ${number(reference.rows)}`}
          hint="Scored accounts vs training rows"
        />
        <Stat
          label="Risk-score shift"
          value={shift ? metric(shift.psi) : '—'}
          hint={
            shift
              ? `Median ${metric(shift.previous_median)} → ${metric(shift.current_median)}`
              : 'First batch for this model'
          }
        />
      </div>
      <Card
        title="Population stability by input"
        description="Under 0.1 is usually stable, 0.1–0.25 worth watching, above 0.25 a large shift. These bands are a rule of thumb, not a statistical test."
      >
        <Bars
          data={features.slice(0, 15).map((f) => ({ ...f, psi: f.psi }))}
          x="feature"
          y="psi"
          horizontal
          height={Math.max(180, Math.min(15, features.length) * 30)}
        />
        <div className="mt-4 flex flex-wrap gap-2">
          {features
            .filter((f) => f.band !== 'stable')
            .map((f) => (
              <Badge key={f.feature} tone={STATUS[f.band][1]}>
                {f.feature} · {metric(f.psi)}
              </Badge>
            ))}
        </div>
      </Card>
      <Alert tone="info">
        Drift means the inputs changed since training, not that the model is
        wrong. Measured performance, once outcomes are known, is what shows
        whether it still ranks churners well.
      </Alert>
    </>
  );
}

function Performance({ p }: { p: Record<string, never> }) {
  const list = p.contact_list as {
    size: number;
    churned: number;
    precision: number | null;
    recall: number | null;
  };
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Measured average precision"
          tone="brand"
          value={metric(p.average_precision)}
          hint={`Validation ${metric(p.validation_average_precision)}`}
        />
        <Stat
          label="Chance level"
          value={metric(p.base_rate)}
          hint={
            p.lift_over_chance
              ? `${p.lift_over_chance}× better than random`
              : 'Churn rate among matched accounts'
          }
        />
        <Stat
          label="Contact list"
          value={`${list.churned} of ${list.size}`}
          hint={`went on to churn · precision ${metric(list.precision)}`}
        />
        <Stat
          label="Accounts with outcomes"
          value={number(p.matched_accounts)}
          hint={`of ${number(p.scored_accounts)} scored`}
        />
      </div>
      <Alert tone="warning">{p.note}</Alert>
    </>
  );
}

interface LiftSummary {
  contacted: { accounts: number; churned: number };
  holdout: { accounts: number; churned: number };
  contacted_churn_rate: number;
  holdout_churn_rate: number;
  reduction: number;
  interval_95: [number, number];
  verdict: 'fewer_churned' | 'more_churned' | 'no_clear_difference';
}
const VERDICT: Record<
  LiftSummary['verdict'],
  [string, 'success' | 'warning' | 'info']
> = {
  fewer_churned: ['Fewer contacted accounts churned', 'success'],
  more_churned: ['More contacted accounts churned', 'warning'],
  no_clear_difference: ['No clear difference yet', 'info'],
};
const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
/** Percentage points with an explicit sign, e.g. −5.9 pts. */
const points = (v: number) =>
  `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v * 100).toFixed(1)} pts`;

function OutreachResult({
  report,
  link = true,
}: {
  report?: Pick<Report, 'id' | 'payload'>;
  link?: boolean;
}) {
  if (!report)
    return (
      <Card
        title="Did outreach work?"
        icon={Users}
        description="Measured, not assumed: compare the accounts you contacted with a random group you held back."
      >
        <ol className="space-y-2 text-sm text-slate-600">
          <li>
            1. When scoring, tick{' '}
            <span className="font-medium text-slate-900">
              Hold back 20% to measure whether outreach works
            </span>
            .
          </li>
          <li>2. Contact only the accounts that aren’t marked holdout.</li>
          <li>
            3. Once the prediction window has passed, the automatic check
            compares how many churned in each group.
          </li>
        </ol>
      </Card>
    );
  const p = report.payload as unknown as LiftSummary;
  const [label, tone] = VERDICT[p.verdict];
  return (
    <Card
      title="Did outreach work?"
      icon={Users}
      action={<Badge tone={tone}>{label}</Badge>}
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Stat
          label="Contacted, then churned"
          value={pct(p.contacted_churn_rate)}
          hint={`${p.contacted.churned} of ${p.contacted.accounts}`}
        />
        <Stat
          label="Held back, then churned"
          value={pct(p.holdout_churn_rate)}
          hint={`${p.holdout.churned} of ${p.holdout.accounts}`}
        />
        <Stat
          label="Churn change when contacted"
          tone="brand"
          value={points(-p.reduction)}
          hint={`95% range ${points(-p.interval_95[1])} to ${points(-p.interval_95[0])}`}
        />
      </div>
      <p className="mt-4 text-xs text-slate-500">
        {p.verdict === 'no_clear_difference'
          ? 'The range includes zero, so this does not yet show that outreach helped. Larger groups narrow it.'
          : 'Based on accounts whose outcome is now known.'}{' '}
        {link && (
          <Link
            className="font-medium text-brand-700"
            to={`/app/monitoring/${report.id}`}
          >
            Details
          </Link>
        )}
      </p>
    </Card>
  );
}

function Lift({ p }: { p: Record<string, never> }) {
  const summary = p as unknown as {
    by_segment: (LiftSummary & { segment: string })[];
    note: string;
  };
  return (
    <>
      <OutreachResult report={{ id: '', payload: p }} link={false} />
      {summary.by_segment.length > 0 && (
        <Card
          title="By segment"
          description="Only segments with at least 10 contacted and 10 held-back accounts are shown."
        >
          <ul className="-my-2 divide-y divide-slate-100">
            {summary.by_segment.map((s) => (
              <li
                key={s.segment}
                className="flex flex-wrap items-center gap-3 py-3 text-sm"
              >
                <span className="min-w-24 font-medium text-slate-900">
                  {s.segment}
                </span>
                <span className="flex-1 text-slate-600">
                  {pct(s.contacted_churn_rate)} contacted vs{' '}
                  {pct(s.holdout_churn_rate)} held back
                </span>
                <Badge tone={VERDICT[s.verdict][1]}>
                  {VERDICT[s.verdict][0]}
                </Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Alert tone="info">{summary.note}</Alert>
    </>
  );
}
