import { useState } from 'react';
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Download,
  FileSpreadsheet,
  ListOrdered,
  Mail,
  Search,
  Sparkles,
  Upload,
  Wand2,
} from 'lucide-react';
import { download } from '../api';
import { amount, column, date, metric, model, number } from '../format';
import { useCatalog, useJobAction, useReasons, useResource } from '../queries';
import { useWorkspaceStore } from '../store';
import type {
  CustomerPage,
  Dataset,
  Profile,
  RunSummary,
  Score,
} from '../types';
import { ProviderConsent } from '../retention-ui';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  Caveats,
  Checkbox,
  Confirm,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Pagination,
  RiskBadge,
  ScoreBar,
  Select,
  Table,
  Td,
  Textarea,
  Th,
  Tr,
} from '../ui';
import { cn, riskLevel } from '../style';
import { ExplainTop, ReasonLine } from '../brief-ui';
import { TAG_SHAPE } from '../../components/site/Tag';
import { HowItWorks, NextStep, StagePill, WorkflowSteps } from '../workflow-ui';

/* ------------------------------------------------------------------ List */

export function ScoreBatches() {
  const [page, setPage] = useState(0);
  const scores = useCatalog<Score>('scores', page);
  const runs = useCatalog<RunSummary>('runs');
  const best = runs.data?.find((r) => !r.error);
  return (
    <>
      <WorkflowSteps current="score" />
      <PageHeader
        eyebrow={<StagePill stage="score" />}
        title="At-risk accounts"
        description="Each batch ranks your current customers by how likely they are to churn. Open the latest one to see who to contact first."
        actions={
          <ButtonLink
            to={best ? `/app/scores/new?run=${best.run_id}` : '/app/models'}
            variant="primary"
            icon={Upload}
          >
            Score customers
          </ButtonLink>
        }
      />
      <Notice error={scores.error} />
      {scores.isPending ? (
        <div className="skeleton h-48 rounded-2xl" />
      ) : scores.data?.length ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {scores.data.map((s, i) => (
              <Link
                key={s.id}
                to={`/app/scores/${s.id}`}
                className="group flex flex-col rounded-2xl bg-white p-5 shadow-card ring-1 ring-slate-200/80 transition hover:-translate-y-0.5 hover:shadow-lift"
              >
                <div className="flex items-center justify-between">
                  <span className="grid size-10 place-items-center rounded-xl bg-rose-50 text-rose-600">
                    <ListOrdered className="size-5" />
                  </span>
                  {i === 0 && page === 0 && <Badge tone="brand">Latest</Badge>}
                </div>
                <p className="mt-4 text-[15px] font-semibold text-slate-900">
                  {date(s.created_at)}
                </p>
                <p className="text-[13px] text-slate-500">
                  {s.ranking === 'risk'
                    ? 'Ranked by risk'
                    : `Ranked by risk × ${s.value_column}`}
                </p>
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-100 pt-4">
                  <div>
                    <p className="text-xs text-slate-500">Accounts</p>
                    <p className="text-lg font-semibold tabular">
                      {number(s.row_count)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Contact budget</p>
                    <p className="text-lg font-semibold tabular">
                      {number(s.contact_count)}
                    </p>
                  </div>
                </div>
                <span className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium text-brand-700">
                  Open ranked list{' '}
                  <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
                </span>
              </Link>
            ))}
          </div>
          <Pagination
            page={page}
            setPage={setPage}
            count={scores.data.length}
          />
        </>
      ) : (
        <Card>
          <EmptyState
            icon={ListOrdered}
            title="No customers scored yet"
            description={
              best
                ? 'Upload a file of current customers (same columns as your training data, without the outcome) and score it.'
                : 'Train a model first, then score current customers with it.'
            }
            action={
              <ButtonLink
                variant="primary"
                to={best ? `/app/scores/new?run=${best.run_id}` : '/app/models'}
              >
                {best ? 'Score customers' : 'Train a model'}
              </ButtonLink>
            }
          />
        </Card>
      )}
      <NextStep
        title="Plan who to contact"
        description="Turn the ranked list into a budgeted contact plan and outreach drafts."
        to={
          scores.data?.[0]
            ? `/app/plays?run=${scores.data[0].run_id}`
            : '/app/plays'
        }
        label="Plan retention"
        disabled={!scores.data?.length}
      />
    </>
  );
}

/* ------------------------------------------------------------------ New */

export function NewScore() {
  const [params] = useSearchParams();
  const runs = useResource<RunSummary[]>('/api/v1/runs?limit=100');
  const datasets = useResource<Dataset[]>('/api/v1/datasets?limit=100');
  const [chosenRun, setRun] = useState(params.get('run') || '');
  const run = chosenRun || runs.data?.find((r) => !r.error)?.run_id || '';
  const [dataset, setDataset] = useState('');
  const [count, setCount] = useState(50);
  const [ranking, setRanking] = useState('risk');
  const [holdout, setHoldout] = useState(false);
  const [value, setValue] = useState('');
  const [unit, setUnit] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [autoDraft, setAutoDraft] = useState(false);
  const [product, setProduct] = useState('');
  const [offer, setOffer] = useState(
    'A helpful check-in; no discount promised.',
  );
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const profile = useResource<Profile>(
    `/api/v1/datasets/${dataset}/profile`,
    Boolean(dataset),
  );
  const queue = useJobAction();
  const navigate = useNavigate();
  const max = profile.data?.row_count || 50000;
  async function start() {
    try {
      await queue.mutateAsync({
        kind: 'score',
        body: {
          run_id: run,
          dataset_id: dataset,
          contact_count: count,
          holdout_rate: holdout && count >= 10 ? 0.2 : 0,
          outreach:
            autoDraft && consent
              ? {
                  provider_consent: true,
                  product_name: product.trim(),
                  approved_offer: offer.trim(),
                  permitted_features: [],
                  channel: 'email',
                }
              : null,
          ranking,
          value_column: ranking === 'risk_x_value' ? value : null,
          value_unit: ranking === 'risk_x_value' ? unit || null : null,
        },
      });
      navigate('/app/jobs');
    } catch {
      /* rendered */
    }
  }
  return (
    <>
      <WorkflowSteps current="score" />
      <PageHeader
        back={{ to: '/app/scores', label: 'All scoring batches' }}
        eyebrow={<StagePill stage="score" />}
        title="Score current customers"
        description="Choose the model and a file of today’s customers. You’ll get every account ranked by churn risk."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card title="1. Model and customers" icon={BrainCircuit}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Model">
                <Select value={run} onChange={(e) => setRun(e.target.value)}>
                  {!run && <option value="">No trained model</option>}
                  {runs.data
                    ?.filter((r) => !r.error)
                    .map((r) => (
                      <option value={r.run_id} key={r.run_id}>
                        {model(r.model)} · AP {metric(r.average_precision)} ·{' '}
                        {date(r.created_at)}
                      </option>
                    ))}
                </Select>
              </Field>
              <Field
                label="Current customers file"
                hint={
                  <>
                    Same columns as training, outcome not needed.{' '}
                    <Link className="font-medium text-brand-700" to="/app/data">
                      Upload one
                    </Link>
                    .
                  </>
                }
              >
                <Select
                  value={dataset}
                  onChange={(e) => {
                    setDataset(e.target.value);
                    setValue('');
                    setConfirmed(false);
                  }}
                >
                  <option value="">Choose a file</option>
                  {datasets.data?.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_filename} · {number(d.row_count)} rows
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {profile.data && (
              <div className="mt-4 flex items-center gap-3 rounded-xl bg-slate-50 p-3 text-sm ring-1 ring-slate-200">
                <FileSpreadsheet className="size-5 text-brand-600" />
                <span className="text-slate-700">
                  <span className="font-medium">
                    {number(profile.data.row_count)}
                  </span>{' '}
                  customers · {profile.data.column_count} columns
                </span>
              </div>
            )}
          </Card>
          <Card title="2. Ranking and shortlist">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Contact budget"
                hint="How many top-ranked accounts go on the shortlist."
              >
                <Input
                  type="number"
                  min="1"
                  max={max}
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
              </Field>
              <Field label="Rank by">
                <Select
                  value={ranking}
                  onChange={(e) => setRanking(e.target.value)}
                >
                  <option value="risk">Risk score</option>
                  <option value="risk_x_value">Risk × customer value</option>
                </Select>
              </Field>
              {ranking === 'risk_x_value' && (
                <>
                  <Field label="Customer value column">
                    <Select
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                    >
                      <option value="">Choose a numeric column</option>
                      {profile.data?.columns
                        .filter((c) => c.inferred_type === 'numeric')
                        .map((c) => (
                          <option key={c.name}>{c.name}</option>
                        ))}
                    </Select>
                  </Field>
                  <Field label="Value unit (optional)">
                    <Input
                      value={unit}
                      onChange={(e) => setUnit(e.target.value)}
                      maxLength={30}
                      placeholder="e.g. USD / month"
                    />
                  </Field>
                </>
              )}
            </div>
            {ranking === 'risk_x_value' && (
              <Alert tone="info" className="mt-4">
                Risk × value is an exposure proxy, not expected or saved
                revenue.
              </Alert>
            )}
            <div className="mt-4">
              <Checkbox
                checked={holdout && count >= 10}
                disabled={count < 10}
                onChange={setHoldout}
                description={
                  count < 10
                    ? 'Needs a shortlist of at least 10 accounts.'
                    : `${Math.max(1, Math.round(count * 0.2))} of the ${count} shortlisted accounts are picked at random and marked “don’t contact”. Comparing them later with the accounts you did contact is the only fair way to tell whether outreach worked.`
                }
              >
                Hold back 20% to measure whether outreach works
              </Checkbox>
            </div>
          </Card>
          <Card
            title="3. Outreach drafts (optional)"
            icon={Mail}
            description="Have AI prepare five general check-in drafts when scoring finishes. Nothing is ever sent."
          >
            <div className="space-y-4">
              <ProviderConsent />
              <Checkbox
                checked={autoDraft && consent}
                disabled={!consent}
                onChange={setAutoDraft}
              >
                Prepare drafts after scoring
              </Checkbox>
              {autoDraft && consent && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Product name">
                    <Input
                      maxLength={100}
                      value={product}
                      onChange={(e) => setProduct(e.target.value)}
                    />
                  </Field>
                  <Field
                    label="Approved offer or next step"
                    className="sm:col-span-2"
                  >
                    <Textarea
                      maxLength={400}
                      value={offer}
                      onChange={(e) => setOffer(e.target.value)}
                    />
                  </Field>
                </div>
              )}
            </div>
          </Card>
          <Confirm checked={confirmed} onChange={setConfirmed}>
            This file contains the customers I want to score, with the same
            inputs the model was trained on.
          </Confirm>
          <Notice
            error={runs.error || datasets.error || profile.error || queue.error}
          />
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="lg"
              icon={ListOrdered}
              loading={queue.isPending}
              disabled={
                !run ||
                !dataset ||
                !confirmed ||
                !Number.isInteger(count) ||
                count < 1 ||
                count > max ||
                (ranking === 'risk_x_value' && !value) ||
                (autoDraft && consent && (!product.trim() || !offer.trim()))
              }
              onClick={() => void start()}
            >
              Score customers
            </Button>
          </div>
        </div>
        <HowItWorks
          points={[
            {
              title: 'Inputs are checked',
              body: 'Missing columns or unseen categories are reported, never silently guessed.',
            },
            {
              title: 'Every account is ranked',
              body: 'Rank 1 is the most at risk. IDs stay matched to their rows.',
            },
            {
              title: 'Scores are relative',
              body: 'Current customers have no outcome yet, so accuracy on this batch can’t be measured.',
            },
          ]}
        />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Batch */

export function ScoreBatch() {
  const { id } = useParams();
  const campaign = useResource<{
    state: string;
    analysis_id?: string;
    message?: string;
  }>(`/api/v1/scores/${id}/campaign`, Boolean(id));
  const [page, setPage] = useState(0);
  const reasons = useReasons(id ?? '');
  const [top, setTop] = useState(50);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const score = useResource<Score>(`/api/v1/scores/${id}`, Boolean(id));
  const customers = useResource<CustomerPage>(
    `/api/v1/scores/${id}/customers?offset=${page * 25}&limit=25`,
    Boolean(id),
  );
  const explain = useJobAction();
  const navigate = useNavigate();
  const setAsk = useWorkspaceStore((s) => s.setAsk);
  if (score.isPending) return <Loading />;
  if (!score.data) return <Notice error={score.error} />;
  const s = score.data;
  async function exportRows() {
    try {
      await download(
        `/api/v1/scores/${id}/export?top_k=${top}`,
        `shortlist-${id}.csv`,
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function explanation(row: number) {
    try {
      await explain.mutateAsync({
        kind: 'explain',
        body: { score_id: id, row_reference: row },
      });
      navigate('/app/jobs');
    } catch {
      /* rendered */
    }
  }
  const rows = (customers.data?.customers ?? []).filter((c) =>
    c.customer_id.toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <>
      <WorkflowSteps current="score" />
      <PageHeader
        back={{ to: '/app/scores', label: 'All scoring batches' }}
        eyebrow={<StagePill stage="score" />}
        title="Ranked accounts"
        description={`${number(s.row_count)} accounts scored ${date(s.created_at)}, ranked by ${s.ranking === 'risk' ? 'risk score' : `risk × ${s.value_column}`}. Rank 1 is most at risk.`}
        actions={
          <>
            <Button icon={Sparkles} onClick={() => setAsk(true)}>
              Ask AI
            </Button>
            <ButtonLink
              to={`/app/plays?run=${s.run_id}`}
              variant="primary"
              trailing={ArrowRight}
            >
              Plan who to contact
            </ButtonLink>
          </>
        }
      />
      <div className="space-y-6">
        {campaign.data?.state === 'failed' && (
          <Alert tone="warning">
            Scores are saved. {campaign.data.message}
          </Alert>
        )}
        {campaign.data?.state === 'succeeded' && (
          <Alert
            tone="success"
            title="Outreach drafts are ready"
            action={
              <ButtonLink size="sm" to={`/app/plays?run=${s.run_id}`}>
                Review
              </ButtonLink>
            }
          >
            AI prepared check-in drafts for the top accounts. Review them in
            Retention plays.
          </Alert>
        )}
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            [
              'High risk',
              Math.max(1, Math.round(s.row_count * 0.1)),
              'Top 10%',
              'text-rose-600',
            ],
            [
              'Elevated',
              Math.round(s.row_count * 0.3) -
                Math.max(1, Math.round(s.row_count * 0.1)),
              'Next 20%',
              'text-amber-600',
            ],
            [
              'Contact budget',
              s.contact_count,
              'On the shortlist',
              'text-slate-900',
            ],
          ].map(([l, v, h, c]) => (
            <div
              key={String(l)}
              className="rounded-2xl bg-white p-5 shadow-card ring-1 ring-slate-200/80"
            >
              <p className="text-[13px] font-medium text-slate-500">{l}</p>
              <p
                className={cn(
                  'mt-1 font-mono text-2xl font-bold tabular',
                  String(c),
                )}
              >
                {number(Number(v))}
              </p>
              <p className="text-xs text-slate-500">{h}</p>
            </div>
          ))}
        </div>
        <Card
          title="Accounts"
          icon={ListOrdered}
          action={
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="Filter this page"
                  className="w-44 pl-9"
                  aria-label="Filter accounts"
                />
              </div>
              <div className="flex items-center gap-1.5">
                <Input
                  type="number"
                  min="1"
                  max={s.row_count}
                  value={top}
                  onChange={(e) => setTop(Number(e.target.value))}
                  className="w-20"
                  aria-label="Rows to export"
                />
                <Button
                  icon={Download}
                  disabled={
                    !Number.isInteger(top) || top < 1 || top > s.row_count
                  }
                  onClick={() => void exportRows()}
                >
                  Export top {top}
                </Button>
              </div>
            </div>
          }
        >
          <Notice error={error || customers.error || explain.error} />
          {id && page === 0 && <ExplainTop scoreId={id} />}
          {customers.isPending ? (
            <div className="skeleton h-96" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Rank</Th>
                  <Th>Account</Th>
                  <Th>Risk</Th>
                  <Th align="right">Risk score</Th>
                  {s.value_column && (
                    <Th align="right">
                      {column(s.value_column)}
                      {s.value_unit ? ` (${s.value_unit})` : ''}
                    </Th>
                  )}
                  {s.value_column && <Th align="right">Risk × value</Th>}
                  <Th />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => {
                  const rank =
                    s.ranking === 'risk' ? c.rank : (c.priority_rank ?? c.rank);
                  const level = riskLevel(c.rank, s.row_count);
                  return (
                    <Tr key={c.row_reference}>
                      <Td mono className="font-semibold text-tag-ink">
                        <span className="flex items-center gap-2.5">
                          <span
                            aria-hidden="true"
                            className={cn(
                              'h-4 w-2.5 shrink-0',
                              level === 'high' && 'bg-tag-red',
                              level === 'elevated' && 'bg-tag-amber',
                              level === 'low' && 'bg-stock-300',
                            )}
                            style={{ clipPath: TAG_SHAPE }}
                          />
                          #{rank}
                        </span>
                      </Td>
                      <Td className="font-medium whitespace-nowrap text-slate-900">
                        {c.customer_id}
                        {c.group === 'holdout' && (
                          <Badge className="ml-2" tone="neutral">
                            Holdout · don’t contact
                          </Badge>
                        )}
                        <ReasonLine
                          reasons={reasons.data}
                          customerId={c.customer_id}
                        />
                      </Td>
                      <Td>
                        <RiskBadge level={level} />
                      </Td>
                      <Td align="right">
                        <ScoreBar value={c.risk_score} />
                      </Td>
                      {s.value_column && (
                        <Td align="right" mono>
                          {c.customer_value == null
                            ? '—'
                            : number(c.customer_value)}
                        </Td>
                      )}
                      {s.value_column && (
                        <Td align="right" mono>
                          {c.exposure_proxy == null
                            ? '—'
                            : amount(c.exposure_proxy)}
                        </Td>
                      )}
                      <Td align="right">
                        <Button
                          size="sm"
                          variant="ghost"
                          icon={Wand2}
                          disabled={explain.isPending}
                          onClick={() => void explanation(c.row_reference)}
                        >
                          Explain
                        </Button>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
          )}
          <Pagination
            page={page}
            setPage={setPage}
            count={customers.data?.customers.length || 0}
          />
        </Card>
        <Caveats
          items={[
            ...s.warnings,
            'Current accounts have no outcome yet, so accuracy on this batch is not measured.',
          ]}
        />
        <div className="flex flex-wrap gap-2">
          <ButtonLink
            to={`/app/models/${s.run_id}`}
            icon={BrainCircuit}
            trailing={ArrowUpRight}
          >
            Model behind these scores
          </ButtonLink>
        </div>
      </div>
      <NextStep
        title="Plan who to contact"
        description="Set a budget and costs, get a recommended contact count and outreach drafts."
        to={`/app/plays?run=${s.run_id}`}
        label="Plan retention"
      />
    </>
  );
}
