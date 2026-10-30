import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronDown,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { post, request } from './api';
import { date } from './format';
import { useAction, useIdentity, useReasons, useResource } from './queries';
import { ProviderConsent } from './retention-ui';
import { useWorkspaceStore } from './store';
import { TracePanel } from './trace-ui';
import { Button, ButtonLink, Notice } from './ui';
import { cn } from './style';
import { Grommet } from '../components/site/Tag';

interface Citation {
  label: string;
  playbook_id: string;
  playbook: string;
  heading: string;
  passage: number;
}
export interface Brief {
  id: string;
  created_at: string;
  score_id: string;
  trace_id: string | null;
  status: 'ready' | 'failed';
  error: string | null;
  content: {
    headline: string;
    what_changed: string[];
    call_first: {
      customer_id: string;
      rank: number;
      why: string;
      citation: Citation | null;
    }[];
    recommended_play: {
      title: string;
      instructions: string;
      citation: Citation | null;
    } | null;
    caveats: string[];
    model: string | null;
  };
  verification: { numbers_checked?: number; withheld?: string[] };
}

/** The "Nemotron" mark used wherever the model wrote something. */
export function NemotronBadge({ checked }: { checked?: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-ink-900 px-2.5 py-1 text-[11px] font-semibold text-brand-200">
      <Sparkles className="size-3" />
      Nemotron
      {checked != null && (
        <span className="font-medium text-slate-300">
          · {checked} numbers checked
        </span>
      )}
    </span>
  );
}

export function CitationLink({ c }: { c: Citation }) {
  return (
    <Link
      to={`/app/playbooks/${c.playbook_id}#passage-${c.passage}`}
      className="inline-flex items-center gap-1 rounded-md bg-brand-50 px-1.5 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-brand-200 hover:bg-brand-100"
      title={`${c.playbook}${c.heading ? ` › ${c.heading}` : ''}`}
    >
      <BookOpen className="size-3" />
      {c.heading || c.playbook}
    </Link>
  );
}

interface Autonomy {
  level: string;
  paused: boolean;
  daily_token_budget: number | null;
  daily_action_quota: number;
  ai_briefs: boolean;
}

/** Turn the scheduled Nemotron brief on or off, keeping every other setting as it is. */
function useBriefSwitch() {
  const current = useResource<Autonomy>('/api/v1/autonomy');
  return useAction<unknown, boolean>(async (on) => {
    const a = current.data!;
    return request('/api/v1/autonomy', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level: a.level,
        paused: a.paused,
        daily_token_budget: a.daily_token_budget,
        daily_action_quota: a.daily_action_quota,
        ai_briefs: on,
      }),
    });
  });
}

export function BriefCard({
  scoreId,
  runId,
}: {
  scoreId: string;
  runId: string;
}) {
  const latest = useResource<{ brief: Brief | null; enabled: boolean }>(
    '/api/v1/briefs/latest',
  );
  const identity = useIdentity();
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const [open, setOpen] = useState(false);
  const write = useAction<Brief, undefined>(() =>
    post('/api/v1/briefs', { score_id: scoreId, provider_consent: true }),
  );
  const toggle = useBriefSwitch();
  const brief = latest.data?.brief;
  const ready = brief?.status === 'ready' ? brief : null;
  const canEdit = identity.data?.can_edit ?? false;
  const canManage = identity.data?.can_manage ?? false;
  if (latest.isPending)
    return <div className="skeleton mb-6 h-56 rounded-2xl" />;
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative mb-6 overflow-hidden bg-field-900 pt-4 text-field-100 shadow-tag [clip-path:polygon(0_0,calc(100%-22px)_0,100%_22px,100%_100%,0_100%)]"
    >
      <Grommet className="absolute top-3 right-9 size-3.5" />
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-1.5 bg-tag-red"
      />
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 px-6 py-4">
        <div className="flex items-center gap-3">
          <NemotronBadge checked={ready?.verification.numbers_checked} />
          <span className="text-sm font-medium text-white">
            {ready ? 'Today’s brief' : 'Your daily brief'}
          </span>
          {ready && (
            <span className="text-xs text-field-200">
              {date(ready.created_at)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {canManage && (
            <label className="flex cursor-pointer items-center gap-2 text-xs text-field-100">
              <input
                type="checkbox"
                className="size-3.5 accent-brand-500"
                checked={latest.data?.enabled ?? false}
                disabled={toggle.isPending}
                onChange={(e) => toggle.mutate(e.target.checked)}
              />
              After every automatic check
            </label>
          )}
          {canEdit && (
            <Button
              size="sm"
              variant="dark"
              icon={Sparkles}
              disabled={!consent}
              loading={write.isPending}
              title={consent ? undefined : 'Allow AI processing below first'}
              onClick={() => write.mutate(undefined)}
            >
              {ready ? 'Refresh' : 'Brief me now'}
            </Button>
          )}
        </div>
      </div>
      {ready ? (
        <div className="grid gap-6 px-6 py-5 lg:grid-cols-[1.2fr_1fr]">
          <div>
            <h2 className="text-xl leading-snug font-semibold text-white">
              {ready.content.headline}
            </h2>
            {ready.content.what_changed.length > 0 && (
              <ul className="mt-4 space-y-2 text-sm text-field-100">
                {ready.content.what_changed.map((t) => (
                  <li key={t} className="flex gap-2">
                    <Check className="mt-0.5 size-4 shrink-0 text-brand-400" />
                    {t}
                  </li>
                ))}
              </ul>
            )}
            {ready.content.recommended_play && (
              <div className="mt-5 bg-white/5 p-4 ring-1 ring-white/10">
                <p className="text-[11px] font-semibold tracking-wide text-brand-300 uppercase">
                  Recommended play
                </p>
                <p className="mt-1 font-medium text-white">
                  {ready.content.recommended_play.title}
                </p>
                <p className="mt-1 text-sm text-field-100">
                  {ready.content.recommended_play.instructions}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {ready.content.recommended_play.citation && (
                    <CitationLink c={ready.content.recommended_play.citation} />
                  )}
                  {canEdit && (
                    <ButtonLink
                      size="sm"
                      variant="primary"
                      trailing={ArrowRight}
                      to={`/app/plays?run=${runId}&brief=${ready.id}`}
                    >
                      Assign this play
                    </ButtonLink>
                  )}
                </div>
              </div>
            )}
          </div>
          <div>
            <p className="text-[11px] font-semibold tracking-wide text-field-200 uppercase">
              Call first
            </p>
            <ol className="mt-2 space-y-2">
              {ready.content.call_first.map((c) => (
                <li
                  key={c.customer_id}
                  className="bg-white/5 p-3 ring-1 ring-white/10"
                >
                  <Link
                    to={`/app/scores/${ready.score_id}`}
                    className="text-sm font-semibold text-white hover:text-brand-200"
                  >
                    #{c.rank} {c.customer_id}
                  </Link>
                  <p className="mt-0.5 text-[13px] text-field-100">{c.why}</p>
                  {c.citation && (
                    <div className="mt-1.5">
                      <CitationLink c={c.citation} />
                    </div>
                  )}
                </li>
              ))}
              {ready.content.call_first.length === 0 && (
                <li className="text-sm text-field-200">
                  No account notes passed verification this time; see the ranked
                  list.
                </li>
              )}
            </ol>
          </div>
          <div className="lg:col-span-2">
            <button
              onClick={() => setOpen(!open)}
              className="flex cursor-pointer items-center gap-1.5 text-xs font-medium text-field-200 hover:text-stock"
            >
              <ShieldCheck className="size-3.5" />
              How this was checked
              <ChevronDown
                className={cn('size-3.5 transition', open && 'rotate-180')}
              />
            </button>
            {open && (
              <div className="mt-3 space-y-3 rounded-xl bg-white p-4 text-sm text-slate-600">
                <p>
                  Nemotron saw only computed results, pseudonymous account
                  labels and your playbook passages; real account IDs stayed on
                  the server. Every number was matched against those results and
                  causal claims were rejected.
                  {ready.verification.withheld?.length
                    ? ` ${ready.verification.withheld.length} item(s) failed the check and were withheld.`
                    : ' Nothing had to be withheld.'}
                </p>
                {ready.content.caveats.length > 0 && (
                  <ul className="list-disc pl-5 text-xs text-slate-500">
                    {ready.content.caveats.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                )}
                {ready.trace_id && <TracePanel traceId={ready.trace_id} />}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="px-6 py-6">
          <h2 className="text-xl font-semibold text-white">
            Let Nemotron tell you who to call today, and why
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-field-100">
            Nemotron reads what your models measured (risk, what changed,
            outcomes) and your own playbooks, then writes a short brief with the
            accounts to call first and a recommended play. Every number is
            checked against the results before you see it.
          </p>
          {brief?.status === 'failed' && (
            <p className="mt-3 text-sm text-amber-300">
              The last brief couldn’t be written: {brief.error}
            </p>
          )}
          {canEdit && (
            <div className="mt-4 max-w-2xl [&_label]:bg-white/5 [&_label]:text-field-100 [&_label]:ring-white/10 [&_span.font-medium]:text-white">
              <ProviderConsent />
            </div>
          )}
        </div>
      )}
      <div className="px-6 pb-4">
        <Notice error={latest.error || write.error || toggle.error} />
      </div>
    </motion.section>
  );
}

export interface Reasons {
  accounts: {
    customer_id: string;
    drivers: {
      feature: string;
      value: unknown;
      typical: unknown;
      risk_change: number;
    }[];
  }[];
  notes: {
    items: Record<
      string,
      {
        text: string;
        source: 'nemotron' | 'computed';
        citation: Citation | null;
        withheld_reason?: string | null;
      }
    >;
    verified: number;
    withheld: number;
    trace_id: string;
    created_at: string;
  } | null;
}

/** Why an account is on the list: Nemotron's checked note, or the computed drivers. */
export function ReasonLine({
  reasons,
  customerId,
}: {
  reasons?: Reasons;
  customerId: string;
}) {
  const account = reasons?.accounts.find((a) => a.customer_id === customerId);
  if (!account) return null;
  const note = reasons?.notes?.items[customerId];
  if (note?.source === 'nemotron')
    return (
      <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs leading-relaxed whitespace-normal text-slate-600">
        <Sparkles className="size-3 shrink-0 text-brand-600" />
        {note.text}
        {note.citation && <CitationLink c={note.citation} />}
      </span>
    );
  return (
    <span className="mt-1 block text-xs whitespace-normal text-slate-500">
      {account.drivers.length
        ? 'Stands out on ' +
          account.drivers
            .map(
              (d) =>
                `${d.feature.replaceAll('_', ' ')} ${String(d.value)} (typical ${String(d.typical)})`,
            )
            .join('; ')
        : 'No single input stands out.'}
    </span>
  );
}

export function ExplainTop({ scoreId }: { scoreId: string }) {
  const reasons = useReasons(scoreId);
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const identity = useIdentity();
  const explain = useAction<Reasons, undefined>(() =>
    post(`/api/v1/scores/${scoreId}/reasons/notes`, { provider_consent: true }),
  );
  const notes = reasons.data?.notes;
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-xl bg-field-900 p-4 text-slate-200 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <NemotronBadge />
          <span className="text-sm font-medium text-white">
            Why these accounts
          </span>
        </div>
        <p className="mt-1 text-xs text-field-200">
          {notes
            ? `${notes.verified} notes passed the number and wording checks${notes.withheld ? `, ${notes.withheld} withheld` : ''}. Written ${date(notes.created_at)}.`
            : 'Each top account shows the inputs that stand out. Nemotron can turn them into plain notes with a matching playbook passage.'}
        </p>
      </div>
      {identity.data?.can_edit && (
        <div className="flex flex-col items-stretch gap-2 sm:items-end">
          {!consent && (
            <div className="max-w-sm text-left [&_label]:bg-white/5 [&_label]:p-2.5 [&_label]:text-xs [&_label]:text-field-100 [&_label]:ring-white/10 [&_span.font-medium]:text-white">
              <ProviderConsent />
            </div>
          )}
          <Button
            size="sm"
            variant="primary"
            icon={Sparkles}
            disabled={!consent}
            loading={explain.isPending}
            onClick={() => explain.mutate(undefined)}
          >
            {notes ? 'Rewrite notes' : 'Explain the top 15'}
          </Button>
        </div>
      )}
      <Notice error={reasons.error || explain.error} />
    </div>
  );
}
