import { useState } from 'react';
import { motion } from 'motion/react';
import {
  Activity,
  ArrowUpRight,
  Brain,
  Clock3,
  Cpu,
  Database,
  Pause,
  Plug,
  RefreshCw,
  Server,
  Sparkles,
  Terminal,
  UserRound,
} from 'lucide-react';
import { authClient } from '../../lib/auth';
import { post, request } from '../api';
import { date } from '../format';
import {
  useAction,
  useIdentity,
  useJobs,
  useMemory,
  useResource,
} from '../queries';
import type { Job, Memory } from '../types';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Field,
  Input,
  JsonDetails,
  KeyValue,
  Notice,
  PageHeader,
  Pagination,
  StateBadge,
  Textarea,
} from '../ui';
import { cn } from '../style';
import { JOB_LABEL, jobResultLink } from '../workflow';
import {
  AuditCard,
  EmailDigestCard,
  PrivacyCard,
  RetentionCard,
  UsageCard,
} from '../governance-ui';

function WorkerAlert() {
  return (
    <Alert
      tone="warning"
      title="The training worker is offline"
      action={<Terminal className="size-4 text-amber-500" />}
    >
      Jobs are queued but won’t run until you start{' '}
      <code className="rounded bg-amber-100 px-1 font-mono text-xs">
        pnpm worker:api
      </code>{' '}
      in a separate terminal.
    </Alert>
  );
}

export function Jobs() {
  const [page, setPage] = useState(0);
  const jobs = useJobs(page);
  const worker = useResource<{ running: boolean }>(
    '/api/v1/worker',
    true,
    10000,
  );
  const cancel = useAction<Job, string>((id) =>
    post(`/api/v1/jobs/${id}/cancel`, {}),
  );
  const active =
    jobs.data?.filter((j) => ['queued', 'running'].includes(j.state)) ?? [];
  return (
    <>
      <PageHeader
        title="Jobs"
        description="Training, scoring and analysis run in the background. Keep working; you’ll get a notification when each one finishes."
        actions={
          <Button icon={RefreshCw} onClick={() => void jobs.refetch()}>
            Refresh
          </Button>
        }
      />
      <div className="space-y-6">
        {worker.data && !worker.data.running && <WorkerAlert />}
        <Notice error={jobs.error || cancel.error} />
        {active.length > 0 && (
          <div className="grid gap-4 md:grid-cols-2">
            {active.map((j) => (
              <motion.div
                key={j.id}
                layout
                className="relative overflow-hidden rounded-2xl bg-white p-5 shadow-card ring-1 ring-sky-200"
              >
                <motion.div
                  className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-sky-500 to-transparent"
                  animate={{ x: ['-100%', '100%'] }}
                  transition={{
                    duration: 1.6,
                    repeat: Infinity,
                    ease: 'linear',
                  }}
                />
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[15px] font-semibold text-slate-900">
                      {JOB_LABEL[j.kind] ?? j.kind}
                    </p>
                    <p className="mt-0.5 text-sm text-slate-500 capitalize">
                      {j.stage.replaceAll('_', ' ')}
                      {j.cancel_requested && ' · cancelling'}
                    </p>
                  </div>
                  <StateBadge state={j.state} />
                </div>
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-xs text-slate-400">
                    Started {date(j.created_at)}
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={Pause}
                    disabled={cancel.isPending || j.cancel_requested}
                    onClick={() => cancel.mutate(j.id)}
                  >
                    Cancel
                  </Button>
                </div>
              </motion.div>
            ))}
          </div>
        )}
        <Card
          title="History"
          icon={Activity}
          description="Updates automatically while work is running."
        >
          {jobs.isPending ? (
            <div className="skeleton h-48" />
          ) : jobs.data?.length ? (
            <>
              <ol className="-mx-5 -my-5 divide-y divide-slate-100">
                {jobs.data.map((j) => (
                  <li
                    key={j.id}
                    className="flex flex-wrap items-center gap-4 px-5 py-4"
                  >
                    <span
                      className={cn(
                        'grid size-9 place-items-center rounded-lg',
                        j.state === 'succeeded'
                          ? 'bg-emerald-50 text-emerald-600'
                          : j.state === 'failed'
                            ? 'bg-rose-50 text-rose-600'
                            : 'bg-slate-100 text-slate-500',
                      )}
                    >
                      <Cpu className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-900">
                        {JOB_LABEL[j.kind] ?? j.kind}
                      </p>
                      <p className="text-xs text-slate-500">
                        {date(j.created_at)} · {j.stage.replaceAll('_', ' ')}
                      </p>
                      {j.error && (
                        <p className="mt-1 text-xs text-rose-600">{j.error}</p>
                      )}
                    </div>
                    <StateBadge state={j.state} />
                    {j.state === 'succeeded' && (
                      <ButtonLink
                        size="sm"
                        to={jobResultLink(j)}
                        trailing={ArrowUpRight}
                      >
                        View result
                      </ButtonLink>
                    )}
                  </li>
                ))}
              </ol>
              <div className="mt-5">
                <Pagination
                  page={page}
                  setPage={setPage}
                  count={jobs.data.length}
                />
              </div>
            </>
          ) : (
            <EmptyState
              icon={Clock3}
              title="Nothing has run yet"
              description="Start training a model or scoring customers to see progress here."
              action={
                <ButtonLink variant="primary" to="/app/models">
                  Train a model
                </ButtonLink>
              }
            />
          )}
        </Card>
      </div>
    </>
  );
}

export function Settings() {
  const session = authClient.useSession();
  const identity = useIdentity();
  const provider = useAction<{ reachable: boolean; model: string }, undefined>(
    () => post('/api/v1/retention/provider-check', {}),
  );
  const capabilities = useResource<{
    workspace_mode: string;
    provider_notice: string;
    limits: Record<string, number>;
  }>('/api/v1/capabilities');
  const worker = useResource<{ running: boolean }>(
    '/api/v1/worker',
    true,
    10000,
  );
  const status = (ok: boolean | undefined, yes: string, no: string) => (
    <Badge tone={ok ? 'success' : 'neutral'} dot>
      {ok ? yes : no}
    </Badge>
  );
  return (
    <>
      <PageHeader
        title="Settings"
        description="Your account, service health and workspace limits."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Account" icon={UserRound}>
          <KeyValue
            items={[
              ['Name', session.data?.user.name],
              ['Email', session.data?.user.email],
              [
                'Workspace',
                <Badge key="w">
                  {identity.data?.organization_id
                    ? `Team · ${identity.data.role}`
                    : 'Personal · isolated'}
                </Badge>,
              ],
            ]}
          />
          <p className="mt-4 text-xs leading-relaxed text-slate-500">
            Each workspace keeps its own data, models and settings. Create a
            team, add colleagues or switch workspaces on the Team page.
          </p>
        </Card>
        <Card title="Service status" icon={Server}>
          <KeyValue
            items={[
              [
                'ML API',
                status(Boolean(capabilities.data), 'Connected', 'Unavailable'),
              ],
              [
                'Training worker',
                status(worker.data?.running, 'Online', 'Offline'),
              ],
              [
                'Nemotron on Nebius',
                status(provider.data?.reachable, 'Reachable', 'Not checked'),
              ],
            ]}
          />
          <Button
            className="mt-4"
            icon={Sparkles}
            loading={provider.isPending}
            onClick={() => provider.mutate(undefined)}
          >
            Check AI connection
          </Button>
          <p className="mt-2 text-xs text-slate-500">
            Makes one tiny provider request. No customer data is sent.
          </p>
          <div className="mt-3">
            <Notice
              error={provider.error || capabilities.error || worker.error}
            />
          </div>
        </Card>
        <Card title="AI data use" icon={Plug}>
          <p className="text-sm leading-relaxed text-slate-600">
            {capabilities.data?.provider_notice ||
              'The assistant sends aggregate evidence and your question to Nebius. Raw sheets are not sent.'}
          </p>
        </Card>
        <Card title="Storage" icon={Database}>
          <p className="text-sm leading-relaxed text-slate-600">
            Accounts live in the auth database. Customer files, models and
            reports are stored in private local workspace folders. Existing
            legacy experiments are kept separately and not auto-imported.
          </p>
        </Card>
      </div>
      {identity.data && (
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <PrivacyCard canManage={identity.data.can_manage} />
          <RetentionCard canManage={identity.data.can_manage} />
          <UsageCard />
        </div>
      )}
      <div id="email" className="mt-6 scroll-mt-20">
        <EmailDigestCard />
      </div>
      <div className="mt-6">
        <MemoryCard />
      </div>
      {identity.data?.can_manage && <AuditCard />}
      {capabilities.data && (
        <Card className="mt-6" title="Workspace limits">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(capabilities.data.limits).map(([name, value]) => (
              <div
                key={name}
                className="rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/70"
              >
                <p className="text-xs text-slate-500 capitalize">
                  {name.replaceAll('_', ' ')}
                </p>
                <p className="mt-1 text-lg font-semibold tabular">
                  {value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <JsonDetails data={capabilities.data} label="API capabilities" />
          </div>
        </Card>
      )}
    </>
  );
}

function MemoryCard() {
  const memory = useMemory();
  if (memory.isPending) return <div className="skeleton h-64 rounded-2xl" />;
  return (
    <MemoryForm key={memory.data?.updated_at ?? 'new'} initial={memory.data} />
  );
}

function MemoryForm({ initial }: { initial?: Memory }) {
  const a = initial?.assumptions ?? {};
  const [values, setValues] = useState({
    budget: a.budget?.toString() ?? '',
    contact_cost: a.contact_cost?.toString() ?? '',
    offer_cost: a.offer_cost?.toString() ?? '',
    assumed_save_rate: a.assumed_save_rate?.toString() ?? '',
    retained_value: a.retained_value?.toString() ?? '',
    currency: a.currency ?? 'USD',
  });
  const [decisions, setDecisions] = useState(
    (initial?.decisions ?? []).map((d) => d.text).join('\n'),
  );
  const save = useAction<Memory, undefined>(() =>
    request('/api/v1/memory', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assumptions: Object.fromEntries(
          Object.entries(values)
            .filter(([, v]) => v !== '')
            .map(([k, v]) => [k, k === 'currency' ? v : Number(v)]),
        ),
        decisions: decisions
          .split('\n')
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 20)
          .map((text) => ({ text })),
      }),
    }),
  );
  const field = (key: keyof typeof values, label: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <Input
        value={values[key]}
        inputMode={key === 'currency' ? 'text' : 'decimal'}
        onChange={(e) => setValues({ ...values, [key]: e.target.value })}
      />
    </Field>
  );
  return (
    <Card
      className="mt-6"
      title="Workspace memory"
      icon={Brain}
      description="Assumptions and decisions the budget planner and Ask AI start from. They are your assumptions, not measured results."
      action={
        initial?.assumptions_source && (
          <Badge>
            {initial.assumptions_source === 'budget_planner'
              ? 'Last set in budget planner'
              : 'Set here'}
          </Badge>
        )
      }
    >
      <div className="grid gap-4 sm:grid-cols-3">
        {field('budget', 'Budget')}
        {field('contact_cost', 'Cost per contact')}
        {field('offer_cost', 'Offer cost per contact')}
        {field('retained_value', 'Value of a saved customer')}
        {field('assumed_save_rate', 'Assumed save rate', '0.1 = 10%')}
        {field('currency', 'Currency', 'Three letters, e.g. USD')}
      </div>
      <Field
        className="mt-4"
        label="Decisions to remember"
        hint="One per line, e.g. “Only contact annual plans this quarter.”"
      >
        <Textarea
          value={decisions}
          onChange={(e) => setDecisions(e.target.value)}
        />
      </Field>
      <div className="mt-4 flex items-center gap-3">
        <Button
          variant="primary"
          loading={save.isPending}
          onClick={() => save.mutate(undefined)}
        >
          Save memory
        </Button>
        {save.isSuccess && (
          <span className="text-sm text-emerald-700">Saved</span>
        )}
      </div>
      <div className="mt-3">
        <Notice error={save.error} />
      </div>
    </Card>
  );
}
