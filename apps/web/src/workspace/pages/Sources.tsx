import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowRight,
  CalendarClock,
  Database,
  FileSpreadsheet,
  Layers,
  ListOrdered,
  PlayCircle,
  Search,
  Sparkles,
  Table2,
  Upload,
} from 'lucide-react';
import { post, request } from '../api';
import { number, percent } from '../format';
import { useAction, useResource } from '../queries';
import type { Task } from '../types';
import { Curve } from '../charts';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Reveal,
  Select,
  Stat,
} from '../ui';
import { useDemoPipeline, useUploadDemo } from '../workflow';
import { HowItWorks } from '../workflow-ui';
import { Connectors } from '../connectors-ui';

interface Source {
  id: string;
  name: string;
  kind: string;
  created_at: string;
  counts: Record<'accounts' | 'invoices' | 'usage' | 'tickets', number>;
  first_date: string;
  last_date: string;
  cancelled_accounts: number;
  note?: string;
}
interface Built {
  dataset_id: string;
  rows: number;
  snapshot_dates: number;
  dropped_unobserved_dates: number;
  positive_rate: number | null;
  recommended_task: {
    target_column: string;
    positive_label: string;
    id_column: string;
    time_column: string;
    feature_columns: string[];
  } | null;
}
interface Timeline {
  account_id: string;
  created_at: string;
  cancelled_at: string | null;
  attributes: Record<string, unknown>;
  usage: { date: string; active_users: number }[];
  invoices: { date: string; amount: number; status: string }[];
  tickets: { date: string; subject: string; topics: string[] }[];
}
const KIND: Record<string, [string, 'violet' | 'info' | 'success']> = {
  synthetic: ['Synthetic demo', 'violet'],
  csv_bundle: ['CSV bundle', 'info'],
  stripe: ['Stripe', 'success'],
  razorpay: ['Razorpay', 'success'],
  zoho_billing: ['Zoho Billing', 'success'],
  hubspot: ['HubSpot', 'success'],
  zoho_crm: ['Zoho CRM', 'success'],
};
/** A badge for a source kind; a matched pair such as "razorpay+zoho_crm" names both. */
function kindOf(kind: string): [string, 'violet' | 'info' | 'success'] {
  if (KIND[kind]) return KIND[kind];
  const parts = kind.split('+').map((k) => KIND[k]?.[0] ?? k);
  return [parts.join(' + '), 'success'];
}

export function Sources() {
  const navigate = useNavigate();
  const sources = useResource<Source[]>('/api/v1/sources');
  const demo = useUploadDemo();
  const pipeline = useDemoPipeline();
  const synthetic = useAction<Source, undefined>(() =>
    post('/api/v1/sources/synthetic', {}),
  );
  const [files, setFiles] = useState<Record<string, File | undefined>>({});
  const [name, setName] = useState('');
  const upload = useAction<Source, undefined>(() => {
    const body = new FormData();
    body.append('name', name.trim() || 'Account data');
    for (const [k, f] of Object.entries(files)) if (f) body.append(k, f);
    return request('/api/v1/sources/upload', { method: 'POST', body });
  });
  async function go(action: typeof synthetic | typeof upload) {
    try {
      const source = await action.mutateAsync(undefined);
      navigate(`/app/sources/${source.id}`);
    } catch {
      /* rendered */
    }
  }
  async function loadDemo() {
    try {
      const result = await demo.mutateAsync(undefined);
      navigate(`/app/data/${result.id}`);
    } catch {
      /* rendered */
    }
  }
  return (
    <>
      <PageHeader
        title="Data sources"
        description="Bring in account history. A single customer table works; account, billing, usage and support tables give the model much more to learn from."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card
            title="Account data (multi-table)"
            icon={Layers}
            description="Accounts, invoices, product usage and support tickets, turned into point-in-time snapshots with a prediction horizon."
            action={<Badge tone="brand">Recommended</Badge>}
          >
            <Notice error={sources.error || synthetic.error || upload.error} />
            {sources.isPending ? (
              <div className="skeleton h-24" />
            ) : sources.data?.length ? (
              <div className="-mx-2 mb-5 space-y-1">
                {sources.data.map((s) => (
                  <Link
                    key={s.id}
                    to={`/app/sources/${s.id}`}
                    className="group flex items-center gap-3 rounded-xl p-3 transition hover:bg-slate-50"
                  >
                    <span className="grid size-10 place-items-center rounded-xl bg-brand-50 text-brand-600">
                      <Table2 className="size-5" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2 text-sm font-medium text-slate-900">
                        {s.name}{' '}
                        <Badge tone={kindOf(s.kind)[1]}>
                          {kindOf(s.kind)[0]}
                        </Badge>
                      </span>
                      <span className="block text-xs text-slate-500">
                        {number(s.counts.accounts)} accounts · {s.first_date} →{' '}
                        {s.last_date}
                      </span>
                    </span>
                    <ArrowRight className="size-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-600" />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="mb-5 text-sm text-slate-500">
                No account data yet.
              </p>
            )}
            <div className="grid gap-4 rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/70">
              <p className="text-sm font-medium text-slate-900">
                Upload a CSV bundle
              </p>
              <Field label="Name">
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Q3 account export"
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                {(['accounts', 'invoices', 'usage', 'tickets'] as const).map(
                  (t) => (
                    <label
                      key={t}
                      className="flex cursor-pointer items-center gap-3 rounded-lg bg-white p-3 text-sm ring-1 ring-slate-200 hover:ring-slate-300"
                    >
                      <FileSpreadsheet className="size-4 text-slate-400" />
                      <span className="min-w-0 flex-1">
                        <span className="block font-medium text-slate-800">
                          {t}.csv{' '}
                          {t === 'accounts' && (
                            <span className="text-rose-600">*</span>
                          )}
                        </span>
                        <span className="block truncate text-xs text-slate-500">
                          {files[t]?.name ?? 'Choose file'}
                        </span>
                      </span>
                      <input
                        type="file"
                        accept=".csv"
                        className="hidden"
                        onChange={(e) =>
                          setFiles({ ...files, [t]: e.target.files?.[0] })
                        }
                      />
                    </label>
                  ),
                )}
              </div>
              <p className="text-xs leading-relaxed text-slate-500">
                Required: accounts (account_id, created_at; cancelled_at when an
                account left), invoices (account_id, date, amount, status),
                usage (account_id, date, active_users), tickets (account_id,
                created_at, subject).
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  icon={Upload}
                  disabled={!files.accounts}
                  loading={upload.isPending}
                  onClick={() => void go(upload)}
                >
                  Upload bundle
                </Button>
                <Button
                  icon={Sparkles}
                  loading={synthetic.isPending}
                  onClick={() => void go(synthetic)}
                >
                  Generate synthetic SaaS workspace
                </Button>
              </div>
            </div>
          </Card>
          <div className="grid gap-6 md:grid-cols-2">
            <Card
              title="Single customer table"
              icon={FileSpreadsheet}
              action={
                <Badge tone="success" dot>
                  Available
                </Badge>
              }
            >
              <p className="text-sm leading-relaxed text-slate-600">
                One row per customer with a churn column. Simplest start.
              </p>
              <ButtonLink className="mt-4" to="/app/data">
                Upload a file
              </ButtonLink>
            </Card>
            <Card
              title="Quick demo"
              icon={Database}
              action={<Badge tone="violet">Demo only</Badge>}
            >
              <p className="text-sm leading-relaxed text-slate-600">
                600 synthetic customers in one table, trained in one click.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  icon={PlayCircle}
                  variant="primary"
                  loading={pipeline.isPending}
                  onClick={() => void pipeline.start()}
                >
                  Run demo pipeline
                </Button>
                <Button
                  size="sm"
                  loading={demo.isPending}
                  onClick={() => void loadDemo()}
                >
                  File only
                </Button>
              </div>
              <div className="mt-3">
                <Notice error={demo.error || pipeline.error} />
              </div>
            </Card>
          </div>
          <div id="connectors" className="scroll-mt-20">
            <h2 className="mb-3 text-[15px] font-semibold text-slate-900">
              Connectors
            </h2>
            <Connectors />
          </div>
        </div>
        <HowItWorks
          title="Why multiple tables?"
          points={[
            {
              title: 'Behaviour beats demographics',
              body: 'Usage declines, failed payments and support friction predict churn far better than plan or contract alone.',
            },
            {
              title: 'Snapshots in time',
              body: 'Each row is an account as of a date, built only from what was known then, labelled by whether it churned in the next N days.',
            },
            {
              title: 'Honest evaluation',
              body: 'Models are tested on the most recent period, the way they’ll actually be used.',
            },
          ]}
        />
      </div>
    </>
  );
}

export function SourceDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const source = useResource<Source>(`/api/v1/sources/${id}`, Boolean(id));
  const [horizon, setHorizon] = useState(90);
  const [lookup, setLookup] = useState('');
  const [account, setAccount] = useState('');
  const timeline = useResource<Timeline>(
    `/api/v1/sources/${id}/accounts/${encodeURIComponent(account)}`,
    Boolean(account),
  );
  const build = useAction<Built, 'training' | 'scoring'>((purpose) =>
    post(`/api/v1/sources/${id}/datasets`, { horizon_days: horizon, purpose }),
  );
  const define = useAction<Task, Built>((b) =>
    post(`/api/v1/datasets/${b.dataset_id}/tasks`, {
      ...b.recommended_task,
      features_available_at_prediction: true,
    }),
  );
  if (source.isPending) return <Loading />;
  if (!source.data) return <Notice error={source.error} />;
  const s = source.data;
  const built = build.data;
  async function applyRecommended() {
    if (!built) return;
    try {
      const task = await define.mutateAsync(built);
      navigate(`/app/models/new?task=${task.id}`);
    } catch {
      /* rendered */
    }
  }
  return (
    <>
      <PageHeader
        back={{ to: '/app/sources', label: 'Data sources' }}
        eyebrow={<Badge tone={kindOf(s.kind)[1]}>{kindOf(s.kind)[0]}</Badge>}
        title={s.name}
        description={`Account history from ${s.first_date} to ${s.last_date}.${s.note ? ` ${s.note}` : ''}`}
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Reveal>
          <Stat
            label="Accounts"
            icon={Layers}
            tone="info"
            value={number(s.counts.accounts)}
            hint={`${number(s.cancelled_accounts)} cancelled`}
          />
        </Reveal>
        <Reveal delay={0.05}>
          <Stat
            label="Invoices"
            icon={FileSpreadsheet}
            tone="violet"
            value={number(s.counts.invoices)}
          />
        </Reveal>
        <Reveal delay={0.1}>
          <Stat
            label="Usage records"
            icon={Table2}
            tone="brand"
            value={number(s.counts.usage)}
          />
        </Reveal>
        <Reveal delay={0.15}>
          <Stat
            label="Support tickets"
            icon={Database}
            tone="warning"
            value={number(s.counts.tickets)}
          />
        </Reveal>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Card
          title="Build a training dataset"
          icon={CalendarClock}
          description="Monthly snapshots, each labelled by whether the account cancelled within the horizon."
        >
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Prediction horizon" className="w-56">
              <Select
                value={horizon}
                onChange={(e) => {
                  setHorizon(Number(e.target.value));
                  build.reset();
                }}
              >
                {[30, 60, 90, 180].map((d) => (
                  <option key={d} value={d}>
                    Churn within {d} days
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              variant="primary"
              loading={build.isPending && build.variables === 'training'}
              onClick={() => build.mutate('training')}
            >
              Build snapshots
            </Button>
          </div>
          <div className="mt-3">
            <Notice error={build.error || define.error} />
          </div>
          {built?.recommended_task && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-5 space-y-4"
            >
              <div className="grid grid-cols-3 gap-3">
                {[
                  ['Snapshot rows', number(built.rows)],
                  ['Snapshot dates', number(built.snapshot_dates)],
                  [
                    'Churn rate',
                    built.positive_rate == null
                      ? '—'
                      : percent(built.positive_rate),
                  ],
                ].map(([l, v]) => (
                  <div
                    key={l}
                    className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70"
                  >
                    <p className="text-xs text-slate-500">{l}</p>
                    <p className="mt-0.5 text-lg font-semibold tabular">{v}</p>
                  </div>
                ))}
              </div>
              {built.dropped_unobserved_dates > 0 && (
                <Alert tone="info">
                  {built.dropped_unobserved_dates} recent dates were skipped
                  because their {horizon}-day outcome isn’t known yet.
                </Alert>
              )}
              <div className="rounded-xl bg-brand-50/60 p-4 ring-1 ring-brand-200/70">
                <p className="text-sm font-semibold text-brand-900">
                  Recommended churn definition
                </p>
                <p className="mt-1 text-[13px] text-brand-900/80">
                  Outcome <b>{built.recommended_task.target_column} = Yes</b>,{' '}
                  {built.recommended_task.feature_columns.length} inputs,
                  evaluated in time order (newest snapshots are the final test).
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    loading={define.isPending}
                    onClick={() => void applyRecommended()}
                  >
                    Use it and train <ArrowRight className="size-4" />
                  </Button>
                  <ButtonLink to={`/app/data/${built.dataset_id}/churn`}>
                    Review manually
                  </ButtonLink>
                </div>
              </div>
            </motion.div>
          )}
        </Card>
        <Card
          title="Build a scoring dataset"
          icon={ListOrdered}
          description={`Every account still active on ${s.last_date}, with the same features. Score it with a model trained above.`}
        >
          <Button
            loading={build.isPending && build.variables === 'scoring'}
            onClick={() => build.mutate('scoring')}
          >
            Build current accounts
          </Button>
          {built && !built.recommended_task && (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Badge tone="success" dot>
                {number(built.rows)} active accounts ready
              </Badge>
              <ButtonLink size="sm" variant="primary" to="/app/scores/new">
                Score them
              </ButtonLink>
            </div>
          )}
        </Card>
      </div>
      <Card
        className="mt-6"
        title="Account timeline"
        icon={Search}
        description="Look up any account to see usage, billing and support history."
      >
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setAccount(lookup.trim());
          }}
        >
          <Input
            value={lookup}
            onChange={(e) => setLookup(e.target.value)}
            placeholder={
              s.kind === 'synthetic' ? 'e.g. ACME-0042' : 'Account ID'
            }
            className="max-w-xs"
          />
          <Button type="submit" disabled={!lookup.trim()}>
            Look up
          </Button>
        </form>
        <div className="mt-4">
          <Notice error={timeline.error} />
        </div>
        {timeline.data && <AccountTimeline t={timeline.data} />}
        {!account && (
          <EmptyState
            compact
            icon={Search}
            title="Find an account"
            description="Usage trend, invoices and tickets for one account, in one view."
          />
        )}
      </Card>
    </>
  );
}

function AccountTimeline({ t }: { t: Timeline }) {
  const events = [
    ...t.invoices
      .filter((i) => i.status !== 'paid')
      .map((i) => ({
        date: i.date,
        kind: 'Failed payment',
        tone: 'danger' as const,
        text: `${i.amount}`,
      })),
    ...t.tickets.map((x) => ({
      date: x.date,
      kind: 'Ticket',
      tone: x.topics.includes('cancel_intent')
        ? ('danger' as const)
        : ('neutral' as const),
      text: x.subject,
    })),
  ].sort((a, b) => b.date.localeCompare(a.date));
  return (
    <div className="mt-2 grid gap-6 xl:grid-cols-[1fr_360px]">
      <div>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold text-slate-900">{t.account_id}</span>
          {t.cancelled_at ? (
            <Badge tone="danger" dot>
              Cancelled {t.cancelled_at}
            </Badge>
          ) : (
            <Badge tone="success" dot>
              Active
            </Badge>
          )}
          {Object.entries(t.attributes).map(
            ([k, v]) =>
              v != null && (
                <Badge key={k}>
                  {k}: {String(v)}
                </Badge>
              ),
          )}
        </div>
        <Curve data={t.usage} x="date" lines={['active_users']} height={220} />
      </div>
      <div className="max-h-72 overflow-y-auto rounded-xl ring-1 ring-slate-200">
        {events.length ? (
          <ol className="divide-y divide-slate-100">
            {events.map((e, i) => (
              <li key={i} className="flex gap-3 px-4 py-2.5 text-sm">
                <span className="w-24 shrink-0 font-mono text-xs text-slate-400">
                  {e.date}
                </span>
                <span className="min-w-0">
                  <Badge tone={e.tone}>{e.kind}</Badge>{' '}
                  <span className="text-slate-700">{e.text}</span>
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="p-4 text-sm text-slate-500">
            No failed payments or tickets.
          </p>
        )}
      </div>
    </div>
  );
}
