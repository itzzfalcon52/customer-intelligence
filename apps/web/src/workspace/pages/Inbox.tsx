import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowUpRight,
  BrainCircuit,
  Check,
  Download,
  AlertTriangle,
  Inbox as InboxIcon,
  Radar,
  X,
} from 'lucide-react';
import { download, post } from '../api';
import { date } from '../format';
import { useAction, useIdentity, useResource } from '../queries';
import type { PendingAction } from '../types';
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Notice,
  PageHeader,
} from '../ui';

const KIND: Record<string, string> = {
  train: 'Train a model',
  retrain: 'Retrain on the latest data',
  play: 'Run a retention play',
};
type PlayResult =
  | { destination: 'csv'; accounts: number }
  | {
      destination: 'hubspot';
      written: number;
      skipped: number;
      failed: number;
    };
interface Digest {
  id: string;
  severity: 'info' | 'watch' | 'alert';
  title: string;
  body: string;
  links: { label: string; href: string }[];
  created_at: string;
  read_at: string | null;
  notified: string | null;
}
const SEVERITY = {
  info: ['success', Radar],
  watch: ['warning', Radar],
  alert: ['danger', AlertTriangle],
} as const;

export function Inbox() {
  const pending = useResource<PendingAction[]>(
    '/api/v1/actions?status=pending',
    true,
    15000,
  );
  const history = useResource<PendingAction[]>('/api/v1/actions');
  const canManage = useIdentity().data?.can_manage ?? false;
  const decide = useAction<PendingAction, { id: string; approve: boolean }>(
    ({ id, approve }) =>
      post(`/api/v1/actions/${id}/${approve ? 'approve' : 'reject'}`, {}),
  );
  const digest = useResource<Digest[]>('/api/v1/digest', true, 30000);
  const read = useAction<Digest, string>((id) =>
    post(`/api/v1/digest/${id}/read`, {}),
  );
  const decided = (history.data ?? []).filter((a) => a.status !== 'pending');
  return (
    <>
      <PageHeader
        title="Inbox"
        description="Approvals waiting for you, and the digest from scheduled monitoring. Nothing that costs money or changes your workspace runs without your say-so."
      />
      <div className="space-y-6">
        <Notice error={pending.error || decide.error || digest.error} />
        <Card
          title="Waiting for approval"
          icon={InboxIcon}
          action={
            pending.data?.length ? (
              <Badge tone="warning" dot>
                {pending.data.length} pending
              </Badge>
            ) : undefined
          }
        >
          {pending.isPending ? (
            <div className="skeleton h-24" />
          ) : pending.data?.length ? (
            <div className="space-y-3">
              <AnimatePresence initial={false}>
                {pending.data.map((a) => (
                  <motion.div
                    key={a.id}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, x: 30 }}
                    className="flex flex-col gap-4 rounded-xl bg-amber-50/50 p-4 ring-1 ring-amber-200/80 sm:flex-row sm:items-center"
                  >
                    <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-white text-amber-600 ring-1 ring-amber-200">
                      <BrainCircuit className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900">
                        {KIND[a.kind] ?? a.kind}
                      </p>
                      <p className="mt-0.5 text-[13px] text-slate-600">
                        {a.summary}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        Proposed by the {a.origin} · {date(a.created_at)}
                      </p>
                    </div>
                    {canManage ? (
                      <div className="flex gap-2">
                        <Button
                          icon={X}
                          variant="ghost"
                          disabled={decide.isPending}
                          onClick={() =>
                            decide.mutate({ id: a.id, approve: false })
                          }
                        >
                          Reject
                        </Button>
                        <Button
                          icon={Check}
                          variant="primary"
                          disabled={decide.isPending}
                          onClick={() =>
                            decide.mutate({ id: a.id, approve: true })
                          }
                        >
                          Approve
                        </Button>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-500">
                        Waiting for an owner or admin
                      </span>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          ) : (
            <EmptyState
              compact
              icon={Check}
              title="You’re all caught up"
              description="When Ask AI proposes training or another action, it appears here for approval."
            />
          )}
        </Card>
        {decided.length > 0 && (
          <Card title="Decided">
            <ol className="-mx-5 -my-5 divide-y divide-slate-100">
              {decided.map((a) => (
                <li
                  key={a.id}
                  className="flex flex-wrap items-center gap-3 px-5 py-3.5"
                >
                  <Badge
                    tone={a.status === 'approved' ? 'success' : 'neutral'}
                    dot
                  >
                    {a.status === 'approved' ? 'Approved' : 'Rejected'}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-700">
                    {a.summary}
                  </span>
                  <span className="text-xs text-slate-400">
                    {a.decided_at && date(a.decided_at)}
                  </span>
                  {a.kind === 'play' && a.status === 'approved' && (
                    <PlayOutcome
                      id={a.id}
                      result={a.payload.result as PlayResult | undefined}
                    />
                  )}
                  {a.result_id && (
                    <ButtonLink
                      size="sm"
                      variant="ghost"
                      to="/app/jobs"
                      trailing={ArrowUpRight}
                    >
                      Job
                    </ButtonLink>
                  )}
                </li>
              ))}
            </ol>
          </Card>
        )}
        <Card
          title="Digest"
          icon={Radar}
          description="One entry per scheduled check, linked to the scores and reports behind it."
        >
          {digest.data?.length ? (
            <ol className="-my-2 divide-y divide-slate-100">
              {digest.data.map((d) => {
                const [tone, Icon] = SEVERITY[d.severity];
                return (
                  <li key={d.id} className="flex gap-3 py-3.5">
                    <Icon
                      className={
                        'mt-0.5 size-4 shrink-0 ' +
                        (tone === 'danger'
                          ? 'text-rose-500'
                          : tone === 'warning'
                            ? 'text-amber-500'
                            : 'text-emerald-500')
                      }
                    />
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
                        {d.title}
                        {!d.read_at && (
                          <Badge tone="brand" dot>
                            New
                          </Badge>
                        )}
                      </p>
                      <p className="mt-1 text-[13px] whitespace-pre-line text-slate-600">
                        {d.body}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                        {d.links.map((l) => (
                          <Link
                            key={l.href}
                            to={l.href}
                            onClick={() => !d.read_at && read.mutate(d.id)}
                            className="font-medium text-brand-700 hover:underline"
                          >
                            {l.label}
                          </Link>
                        ))}
                        <span className="text-slate-400">
                          {date(d.created_at)}
                          {d.notified === 'slack' && ' · sent to Slack'}
                        </span>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <EmptyState
              compact
              icon={Radar}
              title="No digest yet"
              description="Turn on a scheduled check on the Monitoring page to get one entry per run."
              action={
                <ButtonLink size="sm" to="/app/monitoring">
                  Set up monitoring
                </ButtonLink>
              }
            />
          )}
        </Card>
        <p className="text-xs text-slate-500">
          Approvals come from{' '}
          <Link className="font-medium text-brand-700" to="/app/ask">
            Ask AI
          </Link>{' '}
          and scheduled monitoring. They can propose work, but only you can
          start it.
        </p>
      </div>
    </>
  );
}

function PlayOutcome({ id, result }: { id: string; result?: PlayResult }) {
  const [error, setError] = useState('');
  return (
    <span className="flex items-center gap-2 text-xs text-slate-500">
      {result?.destination === 'hubspot' &&
        `${result.written} HubSpot tasks created` +
          (result.skipped ? `, ${result.skipped} not HubSpot companies` : '') +
          (result.failed ? `, ${result.failed} failed` : '')}
      <Button
        size="sm"
        variant="ghost"
        icon={Download}
        onClick={() =>
          download(`/api/v1/actions/${id}/export`, `play-${id}.csv`).catch(
            (e: Error) => setError(e.message),
          )
        }
      >
        CSV
      </Button>
      {error && <span className="text-rose-600">{error}</span>}
    </span>
  );
}
