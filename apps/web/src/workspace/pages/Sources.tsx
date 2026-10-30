import { useState, type ReactNode } from 'react';
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
import { date, number, percent } from '../format';
import { useAction, useIdentity, useResource } from '../queries';
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
  Checkbox,
} from '../ui';
import { useDemoPipeline, useUploadDemo } from '../workflow';
import { HowItWorks } from '../workflow-ui';

interface Source {
  id: string;
  name: string;
  kind: 'synthetic' | 'csv_bundle' | 'stripe' | 'hubspot' | 'stripe+hubspot';
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
const KIND: Record<Source['kind'], [string, 'violet' | 'info' | 'success']> = {
  synthetic: ['Synthetic demo', 'violet'],
  csv_bundle: ['CSV bundle', 'info'],
  stripe: ['Stripe', 'success'],
  hubspot: ['HubSpot', 'success'],
  'stripe+hubspot': ['Stripe + HubSpot', 'success'],
};

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
                        <Badge tone={KIND[s.kind][1]}>{KIND[s.kind][0]}</Badge>
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
          <div>
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
        eyebrow={<Badge tone={KIND[s.kind][1]}>{KIND[s.kind][0]}</Badge>}
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

const COMING = [
  ['Salesforce', 'Accounts, opportunities and cases.'],
  ['Intercom and Zendesk', 'Support conversations and their topics.'],
] as const;

type Provider = 'stripe' | 'hubspot';

interface Connection {
  id: string;
  provider: Provider;
  label: string;
  last_synced_at: string | null;
  last_source_id: string | null;
  last_error: string | null;
  write_enabled: boolean;
  churn_property: string | null;
  enrich_connection_id: string | null;
  last_counts: {
    accounts?: number;
    invoices?: number;
    tickets?: number;
    cancelled?: number | null;
  } | null;
  last_match: { stripe_accounts: number; matched: number; rate: number } | null;
}

const PROVIDER: Record<
  Provider,
  {
    name: string;
    label: string;
    about: string;
    keyName: string;
    placeholder: string;
    howTo: string;
  }
> = {
  stripe: {
    name: 'Stripe',
    label: 'Stripe billing',
    about:
      'Customers, subscriptions and invoices, read every day. Stripe gives billing signals (plan, seats, revenue, failed payments, cancellations).',
    keyName: 'Restricted key',
    placeholder: 'rk_live_… or rk_test_…',
    howTo:
      'Create it in Stripe under Developers → API keys → Create restricted key, with Read on Customers, Subscriptions and Invoices.',
  },
  hubspot: {
    name: 'HubSpot',
    label: 'HubSpot CRM',
    about:
      'Companies and support tickets, read every day; optionally, approved plays become tasks for the account owner.',
    keyName: 'Private app access token',
    placeholder: 'pat-…',
    howTo:
      'Create it in HubSpot under Development → Legacy apps → Create legacy app → Private (super admins only), with the scopes crm.objects.companies.read, crm.schemas.companies.read and tickets. Task write-back also needs a task write scope.',
  },
};

/** Stripe and HubSpot are live; the others are still coming. CSV bundles work for anything. */
function Connectors() {
  const list = useResource<{ enabled: boolean; connections: Connection[] }>(
    '/api/v1/connections',
  );
  const canManage = useIdentity().data?.can_manage ?? false;
  const all = list.data?.connections ?? [];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {list.isLoading ? (
        <div className="sm:col-span-2">
          <Loading label="Loading connections" />
        </div>
      ) : (
        (['stripe', 'hubspot'] as const).map((provider) => {
          const mine = all.filter((c) => c.provider === provider);
          return (
            <div key={provider} className="space-y-3 sm:col-span-2">
              {!list.data?.enabled ? (
                <ConnectorShell
                  name={PROVIDER[provider].name}
                  badge={<Badge>Needs setup</Badge>}
                >
                  {canManage
                    ? 'Connectors are switched off on this server. Run pnpm setup:connectors, then restart the API.'
                    : 'Ask a workspace admin to finish connector setup.'}
                </ConnectorShell>
              ) : mine.length ? (
                mine.map((c) => (
                  <ConnectionCard
                    key={c.id}
                    c={c}
                    all={all}
                    canManage={canManage}
                  />
                ))
              ) : (
                <ConnectForm provider={provider} canManage={canManage} />
              )}
            </div>
          );
        })
      )}
      {COMING.map(([name, description]) => (
        <ConnectorShell
          key={name}
          name={name}
          badge={<Badge tone="info">Coming soon</Badge>}
        >
          {description}
        </ConnectorShell>
      ))}
      <p className="text-xs text-slate-500 sm:col-span-2">
        For anything not connected yet, export the tables as CSV and upload them
        as a bundle above.
      </p>
    </div>
  );
}

function ConnectorShell({
  name,
  badge,
  children,
}: {
  name: string;
  badge: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200/80">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-sm font-semibold text-slate-500">
        {name[0]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
          {name}
          {badge}
        </p>
        <div className="mt-0.5 text-xs text-slate-500">{children}</div>
      </div>
    </div>
  );
}

function ConnectForm({
  provider,
  canManage,
}: {
  provider: Provider;
  canManage: boolean;
}) {
  const info = PROVIDER[provider];
  const [label, setLabel] = useState(info.label);
  const [secret, setSecret] = useState('');
  const connect = useAction<Connection, undefined>(() =>
    post('/api/v1/connections', { provider, label, secret }),
  );
  return (
    <ConnectorShell
      name={info.name}
      badge={<Badge tone="success">Available</Badge>}
    >
      <p>{info.about}</p>
      {canManage ? (
        <form
          className="mt-3 grid gap-3 sm:grid-cols-[1fr_1.4fr_auto] sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            connect.mutate(undefined, { onSuccess: () => setSecret('') });
          }}
        >
          <Field label="Name">
            <Input
              value={label}
              maxLength={80}
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
          <Field label={info.keyName}>
            <Input
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={info.placeholder}
              value={secret}
              onChange={(e) => setSecret(e.target.value.trim())}
            />
          </Field>
          <Button
            type="submit"
            variant="primary"
            disabled={!label.trim() || secret.length < 8}
            loading={connect.isPending}
          >
            Connect
          </Button>
          <div className="sm:col-span-3">
            <Notice error={connect.error} />
            <p className="mt-1">
              {info.howTo} The key is checked with one read, then stored
              encrypted. It is never shown again.
            </p>
          </div>
        </form>
      ) : (
        <p className="mt-2">A workspace admin can connect {info.name}.</p>
      )}
    </ConnectorShell>
  );
}

function ConnectionCard({
  c,
  all,
  canManage,
}: {
  c: Connection;
  all: Connection[];
  canManage: boolean;
}) {
  const info = PROVIDER[c.provider];
  const sync = useAction<Source, undefined>(() =>
    post(`/api/v1/connections/${c.id}/sync`, {}),
  );
  const remove = useAction<unknown, undefined>(() =>
    request(`/api/v1/connections/${c.id}`, { method: 'DELETE' }),
  );
  const counts = c.last_counts;
  const summary =
    counts?.accounts == null
      ? null
      : c.provider === 'stripe'
        ? `${number(counts.accounts)} customers, ${number(counts.invoices ?? 0)} invoices, ${number(counts.cancelled ?? 0)} cancelled`
        : `${number(counts.accounts)} companies, ${number(counts.tickets ?? 0)} tickets`;
  return (
    <ConnectorShell
      name={info.name}
      badge={
        c.last_error ? (
          <Badge tone="danger">Sync failed</Badge>
        ) : (
          <Badge tone="success" dot>
            Connected
          </Badge>
        )
      }
    >
      <p className="text-slate-700">
        {c.label}
        {' · '}
        {c.last_synced_at
          ? `Last synced ${date(c.last_synced_at)}`
          : 'Not synced yet'}
        {summary && ` · ${summary}`}
      </p>
      {c.last_match && (
        <p className="mt-1">
          Matched {number(c.last_match.matched)} of{' '}
          {number(c.last_match.stripe_accounts)} customers (
          {percent(c.last_match.rate)}) to HubSpot companies by email domain.
          Unmatched customers keep billing data only.
        </p>
      )}
      {c.last_error && (
        <Alert tone="danger" className="mt-2">
          {c.last_error}
        </Alert>
      )}
      {canManage && c.provider === 'hubspot' && <HubSpotSettings c={c} />}
      {canManage && c.provider === 'stripe' && (
        <MatchWithHubSpot
          c={c}
          hubspot={all.filter((x) => x.provider === 'hubspot')}
        />
      )}
      <Notice error={sync.error || remove.error} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {canManage && (
          <Button
            size="sm"
            loading={sync.isPending}
            onClick={() => sync.mutate(undefined)}
          >
            Sync now
          </Button>
        )}
        {c.last_source_id && (
          <ButtonLink
            size="sm"
            variant="primary"
            to={`/app/sources/${c.last_source_id}`}
          >
            Train from this data <ArrowRight className="size-3.5" />
          </ButtonLink>
        )}
        {canManage && (
          <Button
            size="sm"
            variant="ghost"
            loading={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `Disconnect ${c.label}? Synced data stays; daily checks on it pause.`,
                )
              )
                remove.mutate(undefined);
            }}
          >
            Disconnect
          </Button>
        )}
      </div>
      <p className="mt-2">
        To check it daily: train a model from this data, make it active, then
        pick this connection under Results → Automatic check.
      </p>
    </ConnectorShell>
  );
}

const settingsOf = (id: string) => (body: Record<string, unknown>) =>
  request<Connection>(`/api/v1/connections/${id}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

/** HubSpot has no standard churn field, so an admin picks the date property that records it. */
function HubSpotSettings({ c }: { c: Connection }) {
  const properties = useResource<{ name: string; label: string }[]>(
    `/api/v1/connections/${c.id}/properties`,
  );
  const save = useAction(settingsOf(c.id));
  const write = useAction<Connection, boolean>((enabled) =>
    request(`/api/v1/connections/${c.id}/write`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, confirm: enabled }),
    }),
  );
  return (
    <div className="mt-3 space-y-3">
      <Field
        label="Which company date records churn?"
        hint="Holdfast never guesses churn. Without this, HubSpot data can be scored but not trained on."
      >
        <Select
          value={c.churn_property ?? ''}
          disabled={properties.isLoading || save.isPending}
          onChange={(e) =>
            save.mutate({ churn_property: e.target.value || null })
          }
        >
          <option value="">Not set</option>
          {properties.data?.map((p) => (
            <option key={p.name} value={p.name}>
              {p.label}
            </option>
          ))}
        </Select>
      </Field>
      <Checkbox
        checked={c.write_enabled}
        disabled={write.isPending}
        onChange={(on) => {
          if (
            !on ||
            window.confirm(
              'Allow approved plays to create tasks in HubSpot? Nothing is written until a play is approved.',
            )
          )
            write.mutate(on);
        }}
        description="Approved plays become HubSpot tasks on the matching companies. The token needs the tasks write scope."
      >
        Create tasks for approved plays
      </Checkbox>
      <Notice error={properties.error || save.error || write.error} />
    </div>
  );
}

function MatchWithHubSpot({
  c,
  hubspot,
}: {
  c: Connection;
  hubspot: Connection[];
}) {
  const save = useAction(settingsOf(c.id));
  if (!hubspot.length) return null;
  return (
    <div className="mt-3">
      <Field
        label="Add HubSpot companies and tickets"
        hint="Customers are matched to companies by email domain on each sync; personal mailboxes never match."
      >
        <Select
          value={c.enrich_connection_id ?? ''}
          disabled={save.isPending}
          onChange={(e) =>
            save.mutate({ enrich_connection_id: e.target.value || null })
          }
        >
          <option value="">Billing only</option>
          {hubspot.map((h) => (
            <option key={h.id} value={h.id}>
              Match with {h.label}
            </option>
          ))}
        </Select>
      </Field>
      <Notice error={save.error} />
    </div>
  );
}
