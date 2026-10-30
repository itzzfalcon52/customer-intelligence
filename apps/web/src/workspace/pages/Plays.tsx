import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  Calculator,
  Check,
  Copy,
  FileText,
  HeartHandshake,
  Mail,
  Scale,
  Sparkles,
  Wallet,
  Send,
  WandSparkles,
} from 'lucide-react';
import { post } from '../api';
import { date, model, number, percent } from '../format';
import {
  useAction,
  useAnalyses,
  useMemory,
  useResource,
  useRuns,
  useScores,
} from '../queries';
import { useAIAction } from '../retention-hooks';
import { ProviderConsent } from '../retention-ui';
import { useWorkspaceStore } from '../store';
import type { Brief } from '../brief-ui';
import type { Memory, Metrics, Run } from '../types';
import { Curve } from '../charts';
import {
  Alert,
  AnimatedNumber,
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Field,
  Input,
  Notice,
  PageHeader,
  Reveal,
  Select,
  Tabs,
  Textarea,
} from '../ui';
import { cn } from '../style';
import { StagePill, WorkflowSteps } from '../workflow-ui';

interface Draft {
  row_reference: number;
  customer_id: string;
  subject: string;
  body: string;
  evidence_features: string[];
}
interface Artifact {
  id: string;
  kind: string;
  run_id: string;
  warning: string;
  drafts?: Draft[];
  paragraphs?: string[];
  proposal?: {
    name: string;
    rationale: string;
    conditions: { column: string; operator: string; value: string }[];
  };
  metrics?: Metrics;
}
interface Scenario {
  validation_evidence_count: number;
  small_sample_warning: string | null;
  validation_precision_interval: [number, number] | null;
  recommended_contacts: number;
  maximum_affordable_contacts: number;
  reserved_cost: number;
  scenario_gross_value: number;
  scenario_net_value: number;
  budget_remaining: number;
  population_size: number;
  curve: { contacts: number; scenario_net_value: number }[];
  warning: string;
  shortlist: { customer_id: string; rank: number }[];
}
const SAVED_KIND: Record<string, string> = {
  campaign: 'Outreach drafts',
  executive_briefing: 'Evidence briefing',
  rule_challenger: 'Rule check',
};
type Tab = 'assign' | 'budget' | 'drafts' | 'evidence';

export function Plays() {
  const [params] = useSearchParams();
  const runs = useRuns();
  const scores = useScores();
  const usable = runs.data?.filter((r) => !r.error) ?? [];
  const fallback =
    usable.find((r) => r.run_id === scores.data?.[0]?.run_id)?.run_id ??
    usable[0]?.run_id ??
    '';
  const [selection, setSelection] = useState(params.get('run') || '');
  const id = selection || fallback;
  const memory = useMemory();
  return (
    <>
      <WorkflowSteps current="act" />
      <PageHeader
        eyebrow={<StagePill stage="act" />}
        title="Plan who to contact"
        description="Turn risk scores into action: decide how many accounts you can afford to contact, and prepare outreach your team reviews before sending."
        actions={
          usable.length > 0 && (
            <div className="w-full sm:w-80">
              <Select
                value={id}
                onChange={(e) => setSelection(e.target.value)}
                aria-label="Model in use"
              >
                {usable.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    {model(r.model)} · {date(r.created_at)}
                  </option>
                ))}
              </Select>
            </div>
          )
        }
      />
      <Notice error={runs.error || scores.error} />
      {id ? (
        memory.isPending ? (
          <div className="skeleton h-96 rounded-2xl" />
        ) : (
          <Studio key={id} id={id} assumed={memory.data?.assumptions ?? {}} />
        )
      ) : (
        <Card>
          <EmptyState
            icon={HeartHandshake}
            title="Train a model first"
            description="Retention plays use your model’s measured performance and risk scores."
            action={
              <ButtonLink variant="primary" to="/app/models">
                Go to models
              </ButtonLink>
            }
          />
        </Card>
      )}
    </>
  );
}

function Studio({
  id,
  assumed,
}: {
  id: string;
  assumed: Memory['assumptions'];
}) {
  const [tab, setTab] = useState<Tab>('assign');
  const [params] = useSearchParams();
  const briefId = params.get('brief') ?? '';
  const fromBrief = useResource<Brief>(
    `/api/v1/briefs/${briefId}`,
    Boolean(briefId),
  );
  const data = useResource<Run>(`/api/v1/runs/${id}`);
  const scores = useScores();
  const analyses = useAnalyses();
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const [batch, setBatch] = useState('');
  const [archive, setArchive] = useState('');
  const saved = useResource<Artifact>(
    `/api/v1/analyses/${archive}`,
    Boolean(archive),
  );
  const [budget, setBudget] = useState(assumed.budget ?? 10000);
  const [contactCost, setContactCost] = useState(assumed.contact_cost ?? 10);
  const [offerCost, setOfferCost] = useState(assumed.offer_cost ?? 100);
  const [saveRate, setSaveRate] = useState(assumed.assumed_save_rate ?? 0.1);
  const [value, setValue] = useState(assumed.retained_value ?? 3000);
  const [population, setPopulation] = useState(1000);
  const [currency, setCurrency] = useState(assumed.currency ?? 'USD');
  const [product, setProduct] = useState('');
  const [offer, setOffer] = useState(
    'A helpful check-in; no discount promised.',
  );
  const [channel, setChannel] = useState('email');
  const [features, setFeatures] = useState<string[]>([]);
  const [copied, setCopied] = useState<number | null>(null);
  const [copyError, setCopyError] = useState('');
  const simulate = useAction<Scenario, Record<string, unknown>>((body) =>
    post('/api/v1/retention/roi', body),
  );
  const campaign = useAIAction<Artifact>('/api/v1/retention/campaign');
  const rule = useAIAction<Artifact>('/api/v1/retention/rule-challenger');
  const briefing = useAIAction<Artifact>('/api/v1/retention/briefing');
  const batches = scores.data?.filter((s) => s.run_id === id) ?? [];
  const scoreId = batch || batches[0]?.id || '';
  const savedWork = (analyses.data ?? []).filter(
    (a) => a.run_id === id && String(a.kind) in SAVED_KIND,
  );
  const money = (n: number) =>
    new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(n);
  const scenario = simulate.data;
  const drafts = (
    campaign.data || (saved.data?.kind === 'campaign' ? saved.data : null)
  )?.drafts;
  const challenger =
    rule.data || (saved.data?.kind === 'rule_challenger' ? saved.data : null);
  const brief =
    briefing.data ||
    (saved.data?.kind === 'executive_briefing' ? saved.data : null);
  const invalid =
    [budget, contactCost, offerCost, saveRate, value, population].some(
      (n) => !Number.isFinite(n),
    ) ||
    budget < 0 ||
    contactCost <= 0 ||
    offerCost < 0 ||
    saveRate < 0 ||
    saveRate > 1 ||
    value <= 0 ||
    population < 1 ||
    population > 50000;
  async function copy(d: Draft) {
    try {
      await navigator.clipboard.writeText(`${d.subject}\n\n${d.body}`);
      setCopied(d.row_reference);
      setCopyError('');
    } catch {
      setCopyError(
        'Copy is unavailable in this browser. Select and copy the draft text.',
      );
    }
  }
  const field = (
    label: string,
    v: number,
    set: (n: number) => void,
    opts: { step?: string; min?: number; hint?: string; prefix?: string } = {},
  ) => (
    <Field label={label} hint={opts.hint}>
      <div className="relative">
        {opts.prefix && (
          <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-slate-400">
            {opts.prefix}
          </span>
        )}
        <Input
          type="number"
          value={v}
          step={opts.step ?? '1'}
          min={opts.min ?? 0}
          className={cn(opts.prefix && 'pl-12')}
          onChange={(e) => {
            set(Number(e.target.value));
            simulate.reset();
          }}
        />
      </div>
    </Field>
  );
  const featureOptions = data.data?.report.feature_columns.filter(
    (f) =>
      !/email|phone|address|name|gender|senior|age|religio|race|caste|ethnic|health|disabil|customer.?id/i.test(
        f,
      ),
  );
  return (
    <div className="space-y-6">
      <Notice error={data.error} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <Tabs
          value={tab}
          onChange={(t) => {
            setTab(t);
            setArchive('');
          }}
          tabs={[
            { value: 'assign', label: 'Assign a play', icon: Send },
            { value: 'budget', label: 'Budget plan', icon: Calculator },
            { value: 'drafts', label: 'Outreach drafts', icon: Mail },
            { value: 'evidence', label: 'Evidence & rules', icon: FileText },
          ]}
        />
        {savedWork.length > 0 && (
          <div className="w-64">
            <Select
              value={archive}
              aria-label="Open saved work"
              onChange={(e) => {
                const a = savedWork.find((x) => x.id === e.target.value);
                setArchive(e.target.value);
                if (a) setTab(a.kind === 'campaign' ? 'drafts' : 'evidence');
              }}
            >
              <option value="">Saved work ({savedWork.length})</option>
              {savedWork.map((a, i) => (
                <option key={a.id} value={a.id}>
                  {SAVED_KIND[String(a.kind)]} {savedWork.length - i}
                </option>
              ))}
            </Select>
          </div>
        )}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          {tab === 'assign' && (
            <AssignPlay
              key={fromBrief.data?.id ?? 'blank'}
              scoreId={fromBrief.data?.score_id ?? scoreId}
              preset={fromBrief.data?.content.recommended_play ?? null}
            />
          )}
          {tab === 'budget' && (
            <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
              <Card
                title="Your assumptions"
                icon={Wallet}
                description={
                  Object.keys(assumed).length
                    ? 'Pre-filled from your saved assumptions. Assumptions, not measured returns.'
                    : 'One currency, one retention period. Assumptions, not measured returns.'
                }
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  {field('Total budget', budget, setBudget, {
                    prefix: currency,
                  })}
                  <Field label="Currency">
                    <Select
                      value={currency}
                      onChange={(e) => {
                        setCurrency(e.target.value);
                        simulate.reset();
                      }}
                    >
                      {['USD', 'EUR', 'GBP', 'INR'].map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </Select>
                  </Field>
                  {field('Cost per contact', contactCost, setContactCost, {
                    min: 0.01,
                    prefix: currency,
                  })}
                  {field('Offer cost per contact', offerCost, setOfferCost, {
                    prefix: currency,
                  })}
                  {field('Value of a saved customer', value, setValue, {
                    prefix: currency,
                  })}
                  {field('Assumed save rate', saveRate, setSaveRate, {
                    step: '0.01',
                    hint: '0.1 = 10% of contacted churners stay',
                  })}
                  {field('Customer population', population, setPopulation, {
                    hint: 'Ignored when a scoring batch is chosen',
                  })}
                  <Field label="Scoring batch">
                    <Select
                      value={batch}
                      onChange={(e) => {
                        setBatch(e.target.value);
                        simulate.reset();
                      }}
                    >
                      <option value="">Use population estimate</option>
                      {batches.map((s) => (
                        <option key={s.id} value={s.id}>
                          {number(s.row_count)} customers · {date(s.created_at)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Button
                  className="mt-5 w-full"
                  variant="primary"
                  icon={Scale}
                  disabled={invalid}
                  loading={simulate.isPending}
                  onClick={() =>
                    simulate.mutate({
                      run_id: id,
                      budget,
                      contact_cost: contactCost,
                      offer_cost: offerCost,
                      assumed_save_rate: saveRate,
                      retained_value: value,
                      currency,
                      population_size: population,
                      score_id: batch || null,
                    })
                  }
                >
                  Calculate contact plan
                </Button>
                <div className="mt-3">
                  <Notice error={simulate.error} />
                </div>
              </Card>
              {scenario ? (
                <div className="space-y-6" aria-live="polite">
                  <Reveal>
                    <div className="relative overflow-hidden rounded-2xl bg-ink-900 p-6 text-white shadow-lift">
                      <div className="absolute -top-16 -right-16 size-56 rounded-full bg-brand-500/25 blur-3xl" />
                      <p className="relative text-sm text-slate-400">
                        Recommended contacts in this scenario
                      </p>
                      <p className="relative mt-1 text-5xl font-semibold tracking-tight tabular">
                        <AnimatedNumber value={scenario.recommended_contacts} />
                      </p>
                      <div className="relative mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
                        {[
                          ['Cost reserved', money(scenario.reserved_cost)],
                          [
                            'Scenario net value',
                            money(scenario.scenario_net_value),
                          ],
                          ['Budget left', money(scenario.budget_remaining)],
                          [
                            'Affordable contacts',
                            number(scenario.maximum_affordable_contacts),
                          ],
                        ].map(([l, v]) => (
                          <div key={l}>
                            <p className="text-xs text-slate-400">{l}</p>
                            <p className="mt-0.5 text-lg font-semibold tabular">
                              {v}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </Reveal>
                  <Card
                    title="Net value by number of contacts"
                    description="Under your assumptions, using validation precision at each contact fraction."
                  >
                    <Curve
                      data={scenario.curve}
                      x="contacts"
                      lines={['scenario_net_value']}
                      height={240}
                    />
                    <p className="mt-3 text-[13px] leading-relaxed text-slate-500">
                      Based on {scenario.validation_evidence_count} validation
                      customers.
                      {scenario.validation_precision_interval &&
                        ` Precision interval ${percent(scenario.validation_precision_interval[0])}–${percent(scenario.validation_precision_interval[1])} (does not account for model selection).`}
                    </p>
                  </Card>
                  {scenario.small_sample_warning && (
                    <Alert tone="warning">
                      {scenario.small_sample_warning}
                    </Alert>
                  )}
                  <Alert tone="info">{scenario.warning}</Alert>
                  {scenario.shortlist.length > 0 && (
                    <Card
                      title={`Shortlist (${scenario.shortlist.length} shown)`}
                    >
                      <div className="flex flex-wrap gap-2">
                        {scenario.shortlist.map((c) => (
                          <Badge key={c.rank}>
                            <span className="text-slate-400">#{c.rank}</span>{' '}
                            {c.customer_id}
                          </Badge>
                        ))}
                      </div>
                    </Card>
                  )}
                </div>
              ) : (
                <Card>
                  <EmptyState
                    icon={Calculator}
                    title="Would an intervention pay off?"
                    description="Enter your costs and how many contacted churners you expect to keep. The plan is calculated from your model’s measured precision. It can recommend zero contacts when spending isn’t justified."
                  />
                </Card>
              )}
            </div>
          )}

          {tab === 'drafts' && (
            <div className="grid gap-6 xl:grid-cols-[420px_1fr]">
              <Card
                title="Draft outreach"
                icon={Mail}
                description="For the five highest-risk accounts. Mapped back to IDs locally."
              >
                <div className="space-y-4">
                  <ProviderConsent personal />
                  <Field label="Scoring batch">
                    <Select
                      value={scoreId}
                      onChange={(e) => {
                        setBatch(e.target.value);
                        campaign.reset();
                        setArchive('');
                      }}
                    >
                      <option value="">Select a batch</option>
                      {batches.map((s) => (
                        <option key={s.id} value={s.id}>
                          {number(s.row_count)} customers · {date(s.created_at)}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  {!batches.length && (
                    <ButtonLink to={`/app/scores/new?run=${id}`}>
                      Score current customers first
                    </ButtonLink>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Product name">
                      <Input
                        maxLength={100}
                        value={product}
                        onChange={(e) => setProduct(e.target.value)}
                        placeholder="Your product"
                      />
                    </Field>
                    <Field label="Channel">
                      <Select
                        value={channel}
                        onChange={(e) => setChannel(e.target.value)}
                      >
                        <option value="email">Email</option>
                        <option value="sms">SMS</option>
                      </Select>
                    </Field>
                  </div>
                  <Field
                    label="Approved offer or next step"
                    hint="Only promise what your team approved. Nothing is sent automatically."
                  >
                    <Textarea
                      value={offer}
                      onChange={(e) => setOffer(e.target.value)}
                      maxLength={400}
                    />
                  </Field>
                  <div>
                    <p className="mb-2 text-[13px] font-medium text-slate-700">
                      Facts the AI may use (optional)
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {featureOptions?.map((f) => {
                        const on = features.includes(f);
                        return (
                          <button
                            key={f}
                            type="button"
                            disabled={!on && features.length >= 12}
                            onClick={() =>
                              setFeatures((p) =>
                                on ? p.filter((v) => v !== f) : [...p, f],
                              )
                            }
                            className={cn(
                              'inline-flex h-7 cursor-pointer items-center gap-1 rounded-full px-3 text-xs font-medium ring-1 transition',
                              on
                                ? 'bg-brand-600 text-white ring-brand-600'
                                : 'bg-white text-slate-600 ring-slate-200 hover:ring-slate-300',
                            )}
                          >
                            {on && <Check className="size-3" />}
                            {f}
                          </button>
                        );
                      })}
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      Sensitive fields, IDs and free text are blocked. Without
                      facts, drafts stay general.
                    </p>
                  </div>
                  <Button
                    className="w-full"
                    variant="primary"
                    icon={Sparkles}
                    disabled={
                      !consent || !scoreId || !product.trim() || !offer.trim()
                    }
                    loading={campaign.isPending}
                    onClick={() => {
                      setArchive('');
                      campaign.mutate({
                        score_id: scoreId,
                        channel,
                        product_name: product.trim(),
                        approved_offer: offer.trim(),
                        permitted_features: features,
                      });
                    }}
                  >
                    {campaign.isPending
                      ? 'Writing drafts…'
                      : 'Draft with Nemotron'}
                  </Button>
                  <Notice error={campaign.error} />
                </div>
              </Card>
              <div className="space-y-4">
                <Notice error={copyError} />
                {drafts?.length ? (
                  drafts.map((d, i) => (
                    <Reveal key={d.row_reference} delay={i * 0.06}>
                      <article className="rounded-2xl bg-white shadow-card ring-1 ring-slate-200/80">
                        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
                          <span className="flex items-center gap-2 text-sm font-medium text-slate-900">
                            <span className="grid size-7 place-items-center rounded-full bg-slate-100 text-xs text-slate-600">
                              {d.customer_id.slice(0, 2)}
                            </span>
                            {d.customer_id}
                          </span>
                          <Badge tone="warning" dot>
                            Needs review
                          </Badge>
                        </div>
                        <div className="px-5 py-4">
                          <p className="text-[15px] font-semibold text-slate-900">
                            {d.subject}
                          </p>
                          <p className="mt-2 text-sm leading-relaxed whitespace-pre-line text-slate-600">
                            {d.body}
                          </p>
                        </div>
                        <div className="flex items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/60 px-5 py-3">
                          <span className="truncate text-xs text-slate-500">
                            Based on:{' '}
                            {d.evidence_features.join(', ') ||
                              'general check-in, no customer facts'}
                          </span>
                          <Button
                            size="sm"
                            icon={copied === d.row_reference ? Check : Copy}
                            onClick={() => void copy(d)}
                          >
                            {copied === d.row_reference ? 'Copied' : 'Copy'}
                          </Button>
                        </div>
                      </article>
                    </Reveal>
                  ))
                ) : (
                  <Card>
                    <EmptyState
                      icon={Mail}
                      title="Drafts appear here"
                      description="Nemotron writes a helpful check-in per account using only the facts you allow. Drafts are never sent: copy them into your own tools after review."
                    />
                  </Card>
                )}
              </div>
            </div>
          )}

          {tab === 'evidence' && (
            <div className="space-y-6">
              <ProviderConsent />
              <div className="grid gap-6 xl:grid-cols-2">
                <Card
                  title="Executive briefing"
                  icon={FileText}
                  description="A three-paragraph summary grounded in the saved results."
                >
                  <Button
                    variant="primary"
                    icon={Sparkles}
                    disabled={!consent}
                    loading={briefing.isPending}
                    onClick={() => {
                      setArchive('');
                      briefing.mutate({ run_id: id });
                    }}
                  >
                    Generate briefing
                  </Button>
                  <div className="mt-3">
                    <Notice error={briefing.error} />
                  </div>
                  {brief?.paragraphs && (
                    <div className="mt-4 space-y-3 text-sm leading-relaxed text-slate-700">
                      {brief.paragraphs.map((p, i) => (
                        <p key={i}>{p}</p>
                      ))}
                    </div>
                  )}
                </Card>
                <Card
                  title="Does a simple rule do enough?"
                  icon={WandSparkles}
                  description="AI proposes up to three conditions; code measures the rule on validation rows."
                >
                  <Button
                    icon={WandSparkles}
                    disabled={!consent}
                    loading={rule.isPending}
                    onClick={() => {
                      setArchive('');
                      rule.mutate({ run_id: id });
                    }}
                  >
                    Challenge with a business rule
                  </Button>
                  <div className="mt-3">
                    <Notice error={rule.error} />
                  </div>
                  {challenger?.proposal && (
                    <div className="mt-4 space-y-3">
                      <p className="text-sm font-semibold text-slate-900">
                        {challenger.proposal.name}
                      </p>
                      <p className="text-sm text-slate-600">
                        {challenger.proposal.rationale}
                      </p>
                      <div className="rounded-xl bg-ink-900 p-4 font-mono text-[13px] leading-relaxed text-brand-200">
                        {challenger.proposal.conditions.map((c, i) => (
                          <div key={i}>
                            {i > 0 && (
                              <span className="text-slate-500">AND </span>
                            )}
                            {c.column} {c.operator} {c.value}
                          </div>
                        ))}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
                          <p className="text-xs text-slate-500">
                            Validation precision
                          </p>
                          <p className="text-lg font-semibold tabular">
                            {challenger.metrics?.precision == null
                              ? '—'
                              : percent(challenger.metrics.precision)}
                          </p>
                        </div>
                        <div className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200">
                          <p className="text-xs text-slate-500">
                            Validation recall
                          </p>
                          <p className="text-lg font-semibold tabular">
                            {challenger.metrics?.recall == null
                              ? '—'
                              : percent(challenger.metrics.recall)}
                          </p>
                        </div>
                      </div>
                      <p className="text-xs text-slate-500">
                        {challenger.warning}
                      </p>
                    </div>
                  )}
                </Card>
              </div>
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

interface Hit {
  citation: string;
  playbook: string;
  heading: string;
  text: string;
}

/** Queue a play for the batch's contact list; it runs only after approval in the Inbox. */
function AssignPlay({
  scoreId,
  preset,
}: {
  scoreId: string;
  preset: Brief['content']['recommended_play'];
}) {
  const navigate = useNavigate();
  const [title, setTitle] = useState(preset?.title ?? '');
  const [instructions, setInstructions] = useState(preset?.instructions ?? '');
  const [accounts, setAccounts] = useState(25);
  const [query, setQuery] = useState('');
  const [destination, setDestination] = useState('');
  const connections = useResource<{
    connections: {
      id: string;
      provider: string;
      label: string;
      write_enabled: boolean;
    }[];
  }>('/api/v1/connections');
  const writable =
    connections.data?.connections.filter(
      (c) => c.provider === 'hubspot' && c.write_enabled,
    ) ?? [];
  const playbooks = useResource<{ id: string }[]>('/api/v1/playbooks');
  const hits = useResource<{ results: Hit[] }>(
    `/api/v1/playbooks/search?q=${encodeURIComponent(query)}&limit=3`,
    query.length >= 2,
  );
  const queue = useAction<{ id: string }, undefined>(() =>
    post('/api/v1/actions/plays', {
      score_id: scoreId,
      title: title.trim(),
      instructions: instructions.trim(),
      accounts,
      connection_id: destination || null,
    }),
  );
  async function submit() {
    try {
      await queue.mutateAsync(undefined);
      navigate('/app/inbox');
    } catch {
      /* rendered */
    }
  }
  if (!scoreId)
    return (
      <EmptyState
        icon={Send}
        title="Score your customers first"
        description="A play goes to the accounts on a batch’s contact list."
      />
    );
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card
        title="Assign a play"
        icon={Send}
        description="Choose what your team should do and for how many accounts. It waits in your Inbox until you approve it. Holdout accounts are never included."
      >
        <div className="space-y-4">
          <Field label="Play name">
            <Input
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Billing check-in"
            />
          </Field>
          <Field
            label="What the account owner should do"
            hint="This becomes the task text. Nothing is sent to customers."
          >
            <Textarea
              rows={4}
              value={instructions}
              maxLength={4000}
              onChange={(e) => setInstructions(e.target.value)}
              placeholder="Call the billing contact within two business days and confirm the card on file."
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Accounts" hint="From the top of the contact list.">
              <Input
                type="number"
                min={1}
                max={200}
                value={accounts}
                onChange={(e) => setAccounts(Number(e.target.value))}
              />
            </Field>
            <Field
              label="Deliver as"
              hint={
                writable.length
                  ? 'HubSpot tasks go to the matching companies’ owners after approval. Nothing is sent to customers.'
                  : 'To create HubSpot tasks, an admin turns on task creation for a HubSpot connection on Data sources.'
              }
            >
              <Select
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                <option value="">CSV export after approval</option>
                {writable.map((c) => (
                  <option key={c.id} value={c.id}>
                    HubSpot tasks · {c.label}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Notice error={queue.error} />
          <div className="flex justify-end">
            <Button
              variant="primary"
              icon={Send}
              loading={queue.isPending}
              disabled={
                !title.trim() ||
                !instructions.trim() ||
                accounts < 1 ||
                accounts > 200
              }
              onClick={() => void submit()}
            >
              Send for approval
            </Button>
          </div>
        </div>
      </Card>
      <Card
        title="From your playbooks"
        icon={FileText}
        description="Find a passage and use it as the instructions."
      >
        {playbooks.data?.length ? (
          <div className="space-y-3">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. failed payments"
              aria-label="Search playbooks"
            />
            {hits.data?.results.map((h) => (
              <button
                key={h.citation}
                onClick={() => {
                  setTitle(h.heading || h.playbook);
                  setInstructions(h.text);
                }}
                className="block w-full cursor-pointer rounded-xl p-3 text-left ring-1 ring-slate-200 transition hover:ring-brand-300"
              >
                <span className="block text-xs font-medium text-slate-500">
                  {h.playbook}
                  {h.heading && ` › ${h.heading}`}
                </span>
                <span className="mt-1 line-clamp-3 block text-sm text-slate-700">
                  {h.text}
                </span>
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-slate-500">
            Upload a playbook under Advanced › Playbooks to pick plays from it.
          </p>
        )}
      </Card>
    </div>
  );
}
