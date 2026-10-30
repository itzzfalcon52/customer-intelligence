import { useState } from 'react';
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Crown,
  Download,
  FlaskConical,
  Gauge,
  GitCompare,
  Lock,
  Play,
  Scale,
  ShieldCheck,
  Sparkles,
  Target,
  Trees,
  TrendingUp,
} from 'lucide-react';
import { ApiError, download, post } from '../api';
import { date, metric, model, number, percent, quality } from '../format';
import {
  useAction,
  useCatalog,
  useIdentity,
  useJobAction,
  useResource,
  useTasks,
} from '../queries';
import { useWorkspaceStore } from '../store';
import type {
  Evaluation,
  Plan,
  Profile,
  Report,
  Run as RunData,
  RunSummary,
  Split,
  Task,
} from '../types';
import { Bars, Curve } from '../charts';
import { SchemaReview } from '../retention-ui';
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
  JsonDetails,
  Loading,
  Notice,
  PageHeader,
  Pagination,
  Reveal,
  Select,
  Stat,
  Table,
  Tabs,
  Td,
  Th,
  Tr,
} from '../ui';
import { cn } from '../style';
import { HowItWorks, NextStep, StagePill, WorkflowSteps } from '../workflow-ui';

const FAMILY: Record<
  string,
  { icon: typeof Gauge; blurb: string; tone: string }
> = {
  dummy_prior: {
    icon: Scale,
    blurb:
      'Baseline: always predicts the average. Any useful model must beat it.',
    tone: 'bg-slate-100 text-slate-600',
  },
  logistic_regression: {
    icon: TrendingUp,
    blurb: 'A simple, transparent linear benchmark.',
    tone: 'bg-sky-50 text-sky-600',
  },
  random_forest: {
    icon: Trees,
    blurb: 'Many decision trees voting together.',
    tone: 'bg-emerald-50 text-emerald-600',
  },
  xgboost: {
    icon: BrainCircuit,
    blurb: 'Boosted trees: often strongest on tabular data.',
    tone: 'bg-violet-50 text-violet-600',
  },
};

interface Comparison {
  comparable: boolean;
  differences: string[];
  warning: string;
  runs: { run_id: string; report: Report; calibration: unknown }[];
}

/* ------------------------------------------------------------------ List */

export function Models() {
  const [page, setPage] = useState(0);
  const runs = useCatalog<RunSummary>('runs', page);
  const tasks = useTasks();
  const [selected, setSelected] = useState<string[]>([]);
  const compare = useAction<Comparison, string[]>((ids) =>
    post('/api/v1/runs/compare', { run_ids: ids }),
  );
  // Runs can come from different datasets, so they aren't ranked against each other here.
  const best = runs.data?.find((r) => !r.error);
  return (
    <>
      <WorkflowSteps current="train" />
      <PageHeader
        eyebrow={<StagePill stage="train" />}
        title="Train and compare models"
        description="Each training run compares four model families on the same split and keeps the best one. Open a run to see how well it ranks churners."
        actions={
          <ButtonLink
            to={
              tasks.data?.[0]
                ? `/app/models/new?task=${tasks.data[0].id}`
                : '/app/churn'
            }
            variant="primary"
            icon={Play}
          >
            Train a new model
          </ButtonLink>
        }
      />
      <Notice error={runs.error || compare.error} />
      {best && (
        <Reveal>
          <Link
            to={`/app/models/${best.run_id}`}
            className="group mb-6 flex flex-col gap-4 rounded-2xl bg-gradient-to-br from-ink-900 to-ink-800 p-6 text-white shadow-lift sm:flex-row sm:items-center"
          >
            <span className="grid size-12 place-items-center rounded-xl bg-brand-500/20 text-brand-300 ring-1 ring-brand-400/30">
              <Crown className="size-6" />
            </span>
            <div className="flex-1">
              <p className="text-xs font-medium text-brand-300">Latest model</p>
              <p className="mt-0.5 text-lg font-semibold">
                {model(best.model)}
              </p>
              <p className="text-sm text-slate-400">
                Trained {date(best.created_at)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-semibold tabular">
                {metric(best.average_precision)}
              </p>
              <p className="text-xs text-slate-400">
                validation avg. precision
              </p>
            </div>
            <ArrowRight className="hidden size-5 text-slate-500 transition group-hover:translate-x-1 group-hover:text-white sm:block" />
          </Link>
        </Reveal>
      )}
      <Card
        title="Training runs"
        description="Tick two or more to compare them side by side."
        icon={BrainCircuit}
        action={
          <Button
            size="sm"
            icon={GitCompare}
            disabled={selected.length < 2}
            loading={compare.isPending}
            onClick={() => compare.mutate(selected)}
          >
            Compare ({selected.length})
          </Button>
        }
      >
        {runs.isPending ? (
          <div className="skeleton h-40" />
        ) : runs.data?.length ? (
          <>
            <Table>
              <thead>
                <tr>
                  <Th className="w-10" />
                  <Th>Selected model</Th>
                  <Th>Trained</Th>
                  <Th align="right">Avg. precision</Th>
                  <Th>Final test</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => {
                  const fam = FAMILY[r.model];
                  const Icon = fam?.icon ?? BrainCircuit;
                  return (
                    <Tr key={r.run_id}>
                      <Td>
                        <input
                          type="checkbox"
                          className="size-4 accent-brand-600"
                          aria-label="Compare this run"
                          checked={selected.includes(r.run_id)}
                          disabled={
                            !selected.includes(r.run_id) &&
                            selected.length === 5
                          }
                          onChange={(e) =>
                            setSelected((p) =>
                              e.target.checked
                                ? [...p, r.run_id]
                                : p.filter((x) => x !== r.run_id),
                            )
                          }
                        />
                      </Td>
                      <Td>
                        <Link
                          to={`/app/models/${r.run_id}`}
                          className="flex items-center gap-3 font-medium text-slate-900 hover:text-brand-700"
                        >
                          <span
                            className={cn(
                              'grid size-8 place-items-center rounded-lg',
                              fam?.tone ?? 'bg-slate-100 text-slate-600',
                            )}
                          >
                            <Icon className="size-4" />
                          </span>
                          {r.error ? (
                            <span className="text-rose-600">Failed</span>
                          ) : (
                            model(r.model)
                          )}
                        </Link>
                      </Td>
                      <Td className="text-slate-500">{date(r.created_at)}</Td>
                      <Td align="right">
                        <div className="flex items-center justify-end gap-2.5">
                          <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className="h-full rounded-full bg-brand-500"
                              style={{ width: `${r.average_precision * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-[13px] tabular">
                            {metric(r.average_precision)}
                          </span>
                        </div>
                      </Td>
                      <Td>
                        {r.test_evaluated ? (
                          <Badge tone="success" dot>
                            Evaluated
                          </Badge>
                        ) : (
                          <Badge tone="neutral">
                            <Lock className="size-3" /> Reserved
                          </Badge>
                        )}
                      </Td>
                      <Td align="right">
                        <ButtonLink
                          size="sm"
                          to={`/app/models/${r.run_id}`}
                          trailing={ArrowUpRight}
                        >
                          Open
                        </ButtonLink>
                      </Td>
                    </Tr>
                  );
                })}
              </tbody>
            </Table>
            <Pagination
              page={page}
              setPage={setPage}
              count={runs.data.length}
            />
          </>
        ) : (
          <EmptyState
            icon={BrainCircuit}
            title="No models trained yet"
            description="Define churn for a dataset, then start a training run. It takes about a minute with the worker running."
            action={
              <ButtonLink
                variant="primary"
                to={
                  tasks.data?.[0]
                    ? `/app/models/new?task=${tasks.data[0].id}`
                    : '/app/churn'
                }
                icon={Play}
              >
                Train your first model
              </ButtonLink>
            }
          />
        )}
      </Card>
      {compare.data && (
        <Card
          className="mt-6"
          title="Comparison"
          icon={GitCompare}
          description={
            compare.data.comparable
              ? 'These runs share the same data and split, so the comparison is fair.'
              : 'These runs differ in data or setup. A direct comparison can mislead.'
          }
          action={
            <Badge tone={compare.data.comparable ? 'success' : 'warning'} dot>
              {compare.data.comparable ? 'Comparable' : 'Different setup'}
            </Badge>
          }
        >
          {compare.data.differences.length > 0 && (
            <Alert tone="warning" className="mb-4">
              Differences: {compare.data.differences.join(', ')}
            </Alert>
          )}
          <Bars
            data={compare.data.runs.map((r) => ({
              name: `${model(r.report.best_validation_model)} · ${r.run_id.slice(0, 4)}`,
              average_precision: Math.max(
                ...r.report.results.map((c) => c.validation.average_precision),
              ),
            }))}
            x="name"
            y="average_precision"
            height={220}
          />
        </Card>
      )}
      <NextStep
        title="Score your current customers"
        description="Apply the trained model to today’s customers to rank who is most at risk."
        to={best ? `/app/scores/new?run=${best.run_id}` : '/app/models'}
        label="Score customers"
        disabled={!best}
      />
    </>
  );
}

/* ------------------------------------------------------------------ New training run */

export function TrainModel() {
  const [params] = useSearchParams();
  const tasks = useTasks();
  const [chosen, setSelected] = useState(params.get('task') || '');
  const selected = chosen || tasks.data?.[0]?.id || '';
  const task = useResource<Task>(
    `/api/v1/tasks/${selected}`,
    Boolean(selected),
  );
  const plan = useResource<Plan>(
    `/api/v1/tasks/${selected}/plan`,
    Boolean(selected),
  );
  const split = useAction<Split, string>((id) =>
    post(`/api/v1/tasks/${id}/split`, {}),
  );
  const [trials, setTrials] = useState(4);
  const [cv, setCv] = useState(3);
  const [autoBrief, setAutoBrief] = useState(false);
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const [policy, setPolicy] = useState('f1');
  const [minimumRecall, setMinimumRecall] = useState(0.5);
  const [threshold, setThreshold] = useState(0.5);
  const [advanced, setAdvanced] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const train = useJobAction();
  const navigate = useNavigate();
  const invalid =
    !Number.isFinite(threshold) ||
    threshold < 0 ||
    threshold > 1 ||
    !Number.isFinite(minimumRecall) ||
    minimumRecall <= 0 ||
    minimumRecall > 1;
  async function start() {
    try {
      await train.mutateAsync({
        kind: 'train',
        body: {
          task_id: selected,
          search_trials: trials,
          threshold,
          cv_folds: cv,
          generate_briefing: autoBrief && consent,
          threshold_policy: policy,
          minimum_recall: minimumRecall,
        },
      });
      navigate('/app/jobs');
    } catch {
      /* rendered */
    }
  }
  if (tasks.isPending) return <Loading />;
  if (!tasks.data?.length)
    return (
      <>
        <WorkflowSteps current="train" />
        <Card>
          <EmptyState
            icon={Target}
            title="Define churn first"
            description="Training needs a churn definition: the outcome column and the inputs to learn from."
            action={
              <ButtonLink variant="primary" to="/app/churn">
                Define churn
              </ButtonLink>
            }
          />
        </Card>
      </>
    );
  return (
    <>
      <WorkflowSteps current="train" />
      <PageHeader
        back={{ to: '/app/models', label: 'All models' }}
        eyebrow={<StagePill stage="train" />}
        title="Train a churn model"
        description="The defaults are sensible: review the plan, confirm, and start. Training runs in the background, and you’ll get a notification when it’s done."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Card title="Churn definition" icon={Target}>
            <Field label="Train on">
              <Select
                value={selected}
                onChange={(e) => {
                  setSelected(e.target.value);
                  setConfirmed(false);
                  split.reset();
                }}
              >
                {tasks.data.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.target_column} = {t.positive_label} ·{' '}
                    {t.feature_columns.length} inputs
                  </option>
                ))}
              </Select>
            </Field>
            {task.data && (
              <div className="mt-4 flex flex-wrap gap-2">
                {task.data.feature_columns.map((f) => (
                  <Badge key={f}>{f}</Badge>
                ))}
              </div>
            )}
            <div className="mt-3">
              <Notice error={tasks.error || task.error || plan.error} />
            </div>
          </Card>

          <Card
            title="Models that will compete"
            description="Same split, same data. The best validation average precision wins."
            icon={BrainCircuit}
          >
            {plan.isPending ? (
              <div className="skeleton h-32" />
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {plan.data?.candidates.map((c, i) => {
                  const fam = FAMILY[c.model];
                  const Icon = fam?.icon ?? BrainCircuit;
                  return (
                    <motion.div
                      key={c.candidate_id}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.06 }}
                      className="flex gap-3 rounded-xl p-4 ring-1 ring-slate-200"
                    >
                      <span
                        className={cn(
                          'grid size-10 shrink-0 place-items-center rounded-xl',
                          fam?.tone,
                        )}
                      >
                        <Icon className="size-5" />
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {model(c.model)}
                        </p>
                        <p className="mt-0.5 text-[13px] leading-relaxed text-slate-500">
                          {fam?.blurb}
                        </p>
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            )}
          </Card>

          <Card
            title="Settings"
            description="Defaults work for most data."
            action={
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setAdvanced(!advanced)}
              >
                {advanced ? 'Hide advanced' : 'Show advanced'}
              </Button>
            }
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field
                label="Search effort"
                hint="Extra variants of each model family."
              >
                <Select
                  value={trials}
                  onChange={(e) => setTrials(Number(e.target.value))}
                >
                  {[0, 2, 4, 8].map((n) => (
                    <option key={n} value={n}>
                      {n === 0
                        ? 'Quick: base models only'
                        : `${n} extra variants`}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Stability check"
                hint="Cross-validation on training rows only."
              >
                <Select
                  value={cv}
                  onChange={(e) => setCv(Number(e.target.value))}
                >
                  <option value={3}>3 folds (recommended)</option>
                  <option value={5}>5 folds (slower)</option>
                  <option value={0}>Off (fastest)</option>
                </Select>
              </Field>
            </div>
            {advanced && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="mt-4 grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2"
              >
                <Field
                  label="Alert cutoff policy"
                  hint="Automatic cutoffs use training out-of-fold predictions."
                >
                  <Select
                    value={policy}
                    onChange={(e) => setPolicy(e.target.value)}
                  >
                    <option value="f1">Balance precision and recall</option>
                    <option value="precision_at_recall">
                      Precision with a recall floor
                    </option>
                    <option value="fixed">Fixed threshold</option>
                  </Select>
                </Field>
                <Field
                  label={policy === 'fixed' ? 'Threshold' : 'Initial threshold'}
                  hint="Ranking doesn’t depend on this cutoff."
                >
                  <Input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    value={threshold}
                    onChange={(e) => setThreshold(Number(e.target.value))}
                  />
                </Field>
                {policy === 'precision_at_recall' && (
                  <Field label="Minimum recall">
                    <Input
                      type="number"
                      min="0.05"
                      max="1"
                      step="0.05"
                      value={minimumRecall}
                      onChange={(e) => setMinimumRecall(Number(e.target.value))}
                    />
                  </Field>
                )}
                <div className="sm:col-span-2">
                  <Checkbox
                    checked={autoBrief && consent}
                    disabled={!consent}
                    onChange={setAutoBrief}
                    description={
                      consent
                        ? undefined
                        : 'Turn on AI processing (in the input review below) to enable.'
                    }
                  >
                    Write an AI executive briefing when training finishes
                  </Checkbox>
                </div>
                <div className="sm:col-span-2">
                  <Button
                    size="sm"
                    loading={split.isPending}
                    onClick={() => split.mutate(selected)}
                  >
                    Preview the data split
                  </Button>
                  <div className="mt-2">
                    <Notice error={split.error} />
                  </div>
                  {split.data && (
                    <div className="mt-3 grid grid-cols-3 gap-3">
                      {(['train', 'validation', 'test'] as const).map(
                        (part) => (
                          <div
                            key={part}
                            className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200"
                          >
                            <p className="text-xs font-medium text-slate-500 capitalize">
                              {part}
                              {part === 'test' && ' · reserved'}
                            </p>
                            <p className="mt-1 text-lg font-semibold tabular">
                              {number(split.data![part].row_count)}
                            </p>
                            <p className="text-xs text-slate-500">
                              {Object.entries(split.data![part].class_counts)
                                .map(([l, n]) => `${l}: ${n}`)
                                .join(' · ')}
                            </p>
                          </div>
                        ),
                      )}
                    </div>
                  )}
                  {split.data && split.data.train.row_count > 200_000 && (
                    <Alert tone="info" className="mt-4">
                      Large dataset ({number(split.data.train.row_count)}{' '}
                      training rows). Training can take many minutes; skip the
                      extra search to finish sooner.
                    </Alert>
                  )}
                </div>
              </motion.div>
            )}
          </Card>

          <SchemaReview
            taskId={selected}
            onApplied={(id) => {
              setSelected(id);
              setConfirmed(false);
            }}
          />

          <Confirm checked={confirmed} onChange={setConfirmed}>
            I’ve reviewed the churn definition and plan. Start this training
            run.
          </Confirm>
          <Notice error={train.error} />
          <div className="flex justify-end">
            <Button
              variant="primary"
              size="lg"
              icon={Play}
              disabled={!confirmed || invalid}
              loading={train.isPending}
              onClick={() => void start()}
            >
              Start training
            </Button>
          </div>
        </div>
        <div className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <HowItWorks
            points={[
              {
                title: 'Split',
                body: 'Rows are split into training, validation and a reserved test set. Nothing is fitted on test rows.',
              },
              {
                title: 'Compete',
                body: 'Each model learns from training rows and is scored on validation rows.',
              },
              {
                title: 'Select',
                body: 'The model that ranks churners best (average precision) wins. The test set stays locked until you choose to reveal it.',
              },
            ]}
            footer="Training needs the worker: run pnpm worker:api in a separate terminal."
          />
          {plan.data?.limitations && (
            <Card title="Limitations">
              <ul className="ml-4 list-disc space-y-1.5 text-[13px] leading-relaxed text-slate-600">
                {plan.data.limitations.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ Detail */

export function ModelDetail() {
  const { id } = useParams();
  const data = useResource<RunData>(`/api/v1/runs/${id}`, Boolean(id));
  const briefing = useResource<{
    state: string;
    paragraphs?: string[];
    message?: string;
  }>(`/api/v1/runs/${id}/briefing`, Boolean(data.data));
  const evaluation = useResource<Evaluation>(
    `/api/v1/runs/${id}/evaluation`,
    Boolean(data.data),
  );
  const profile = useResource<Profile>(
    `/api/v1/datasets/${data.data?.report.dataset_id}/profile`,
    Boolean(data.data),
  );
  const action = useJobAction();
  const registry = useResource<{ run_id: string | null }>('/api/v1/registry');
  const canManage = useIdentity().data?.can_manage ?? false;
  const promote = useAction<{ run_id: string | null }, undefined>(() =>
    post('/api/v1/registry/promote', { run_id: id }),
  );
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [segment, setSegment] = useState('');
  const [heuristic, setHeuristic] = useState('');
  const [direction, setDirection] = useState('higher_risk');
  const [freeze, setFreeze] = useState(false);
  const [view, setView] = useState<'validation' | 'test' | 'tools'>(
    'validation',
  );
  if (data.isPending) return <Loading />;
  if (!data.data) return <Notice error={data.error} />;
  const r = data.data;
  const report = r.report;
  const best =
    report.results.find(
      (c) => c.candidate_id === report.best_validation_candidate_id,
    ) ||
    report.results.find((c) => c.model_name === report.best_validation_model)!;
  const metrics = view === 'test' ? evaluation.data?.metrics : best.validation;
  // Chance level is the churn rate of the partition being shown.
  const grade = metrics
    ? quality(
        metrics.average_precision,
        metrics.positive_count / Math.max(1, metrics.row_count),
      )
    : null;
  async function queue(kind: string, body: Record<string, unknown>) {
    try {
      await action.mutateAsync({ kind, body });
      navigate('/app/jobs');
    } catch {
      /* rendered */
    }
  }
  async function exportReport() {
    try {
      await download(`/api/v1/runs/${id}/report`, `model-report-${id}.html`);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const sorted = [...report.results].sort(
    (a, b) => b.validation.average_precision - a.validation.average_precision,
  );
  return (
    <>
      <WorkflowSteps current="train" />
      <PageHeader
        back={{ to: '/app/models', label: 'All models' }}
        eyebrow={<StagePill stage="train" />}
        title={
          <span className="flex items-center gap-3">
            {model(report.best_validation_model)}
            <Badge tone="success" dot>
              Selected
            </Badge>
            {registry.data?.run_id === id && (
              <Badge tone="brand" dot>
                Active model
              </Badge>
            )}
          </span>
        }
        description={`Predicts ${report.target_column} = ${report.positive_label} from ${report.feature_columns.length} inputs. Trained ${date(r.created_at)}.`}
        actions={
          <>
            <Button icon={Download} onClick={() => void exportReport()}>
              Report
            </Button>
            {registry.data && registry.data.run_id !== id && canManage && (
              <Button
                icon={Crown}
                loading={promote.isPending}
                onClick={() => promote.mutate(undefined)}
                title="Scheduled monitoring scores new data with the active model"
              >
                Make active
              </Button>
            )}
            <ButtonLink
              to={`/app/scores/new?run=${id}`}
              variant="primary"
              trailing={ArrowRight}
            >
              Score customers
            </ButtonLink>
          </>
        }
      />
      <div className="space-y-6">
        <Notice error={error || action.error || promote.error} />
        {report.selection_warning && (
          <Alert tone="warning">{report.selection_warning}</Alert>
        )}
        {briefing.data?.state === 'failed' && (
          <Alert tone="warning">
            Your model trained successfully. {briefing.data.message}
          </Alert>
        )}

        <Tabs
          value={view}
          onChange={setView}
          tabs={[
            { value: 'validation', label: 'Validation results', icon: Gauge },
            {
              value: 'test',
              label: evaluation.data ? 'Final test' : 'Final test (reserved)',
              icon: evaluation.data ? ShieldCheck : Lock,
            },
            {
              value: 'tools',
              label: 'Diagnostics & tools',
              icon: FlaskConical,
            },
          ]}
        />

        {view !== 'tools' && metrics && (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              [
                'Average precision',
                metric(metrics.average_precision),
                grade
                  ? `${grade.lift.toFixed(1)}× better than random (${metric(grade.chance)})`
                  : 'How well it ranks churners first',
              ],
              ['ROC-AUC', metric(metrics.roc_auc), 'Ranking quality overall'],
              [
                'Precision',
                metric(metrics.precision),
                'Share of alerts that churned',
              ],
              ['Recall', metric(metrics.recall), 'Share of churners caught'],
            ].map(([l, v, h], i) => (
              <Reveal key={l} delay={i * 0.04}>
                <Stat
                  label={l}
                  value={
                    <span className="flex items-center gap-2">
                      <span className="font-mono">{v}</span>
                      {i === 0 && grade && (
                        <Badge tone={grade.tone}>{grade.band}</Badge>
                      )}
                    </span>
                  }
                  hint={h}
                />
              </Reveal>
            ))}
          </div>
        )}

        {view === 'validation' && (
          <>
            {(briefing.data?.state === 'succeeded' ||
              report.executive_briefing?.paragraphs) && (
              <Card
                title="What this means for your team"
                icon={Sparkles}
                description={
                  briefing.data?.state === 'succeeded'
                    ? 'AI briefing generated after training. Check the numbers below.'
                    : 'Computed from saved results, without an AI call.'
                }
              >
                <div className="space-y-3 text-[14.5px] leading-relaxed text-slate-700">
                  {(briefing.data?.state === 'succeeded'
                    ? briefing.data.paragraphs
                    : report.executive_briefing?.paragraphs
                  )?.map((p, i) => (
                    <p key={i}>{p}</p>
                  ))}
                </div>
              </Card>
            )}
            <div className="grid gap-6 xl:grid-cols-2">
              <Card
                title="Model leaderboard"
                description="All candidates, same split. Higher is better."
                icon={Crown}
              >
                <div className="space-y-3">
                  {sorted.map((c, i) => {
                    const fam = FAMILY[c.model_name];
                    const win = c.candidate_id === best.candidate_id;
                    return (
                      <div
                        key={c.candidate_id}
                        className={cn(
                          'rounded-xl p-3 ring-1',
                          win
                            ? 'bg-brand-50/50 ring-brand-200'
                            : 'ring-slate-200',
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="flex items-center gap-2 text-sm font-medium text-slate-900">
                            <span className="w-4 text-xs text-slate-400">
                              {i + 1}
                            </span>
                            {model(c.model_name)}
                            {win && (
                              <Crown className="size-3.5 text-brand-600" />
                            )}
                          </span>
                          <span className="font-mono text-sm font-semibold tabular">
                            {metric(c.validation.average_precision)}
                          </span>
                        </div>
                        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                          <motion.div
                            className={cn(
                              'h-full rounded-full',
                              win ? 'bg-brand-500' : 'bg-slate-300',
                            )}
                            initial={{ width: 0 }}
                            animate={{
                              width: `${c.validation.average_precision * 100}%`,
                            }}
                            transition={{ duration: 0.7, delay: i * 0.08 }}
                          />
                        </div>
                        {fam && (
                          <p className="mt-1.5 text-xs text-slate-500">
                            {fam.blurb}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
              {report.threshold_selection?.validation_curve ? (
                <Card
                  title="Precision vs. recall"
                  description="Raising the cutoff gives fewer, more precise alerts. Development evidence only."
                >
                  <Curve
                    data={report.threshold_selection.validation_curve}
                    x="threshold"
                    lines={['precision', 'recall']}
                    height={300}
                  />
                </Card>
              ) : (
                <Card title="Outcomes at the cutoff">
                  {metrics && <Confusion m={metrics} />}
                </Card>
              )}
            </div>
            {report.threshold_selection?.validation_curve && metrics && (
              <Card
                title="Outcomes at the selected cutoff"
                description={`Validation customers at threshold ${report.classification_threshold}.`}
              >
                <Confusion m={metrics} />
              </Card>
            )}
            <Card
              title="All metrics"
              description="Validation metrics for every candidate."
            >
              <Table>
                <thead>
                  <tr>
                    <Th>Candidate</Th>
                    {[
                      'Avg. precision',
                      'AUC',
                      'Precision',
                      'Recall',
                      'F1',
                      'Accuracy',
                      'CV avg. precision',
                      'Seconds',
                    ].map((h) => (
                      <Th key={h} align="right">
                        {h}
                      </Th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.results.map((c) => (
                    <Tr key={c.candidate_id}>
                      <Td className="font-medium whitespace-nowrap text-slate-900">
                        {model(c.model_name)}
                        <span className="block font-mono text-[11px] font-normal text-slate-400">
                          {c.candidate_id}
                        </span>
                      </Td>
                      <Td align="right" mono>
                        {metric(c.validation.average_precision)}
                      </Td>
                      <Td align="right" mono>
                        {metric(c.validation.roc_auc)}
                      </Td>
                      <Td align="right" mono>
                        {metric(c.validation.precision)}
                      </Td>
                      <Td align="right" mono>
                        {metric(c.validation.recall)}
                      </Td>
                      <Td align="right" mono>
                        {metric(c.validation.f1)}
                      </Td>
                      <Td align="right" mono>
                        {percent(c.validation.accuracy)}
                      </Td>
                      <Td align="right" mono>
                        {c.training_cv_average_precision == null
                          ? '—'
                          : `${metric(c.training_cv_average_precision)} ± ${metric(c.training_cv_std)}`}
                      </Td>
                      <Td align="right" mono>
                        {c.elapsed_seconds.toFixed(2)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </Card>
            <Caveats
              items={[
                ...report.results.flatMap((c) =>
                  c.warnings.map((w) => `${model(c.model_name)}: ${w}`),
                ),
                ...report.failures.map(
                  (f) => `${f.candidate_id} failed: ${f.error}`,
                ),
              ]}
            />
            <Alert tone="info">
              Average precision and ROC-AUC measure ranking, not accuracy.
              Random ranking scores average precision equal to the churn rate (
              {grade ? metric(grade.chance) : 'the baseline'}), so read it as
              lift over chance. On churn data with only contract and billing
              fields, 0.5–0.7 is typical; usage, support and payment history
              raise the ceiling more than further tuning does.
            </Alert>
          </>
        )}

        {view === 'test' &&
          (evaluation.data ? (
            <>
              <Caveats items={[evaluation.data.warning]} />
              <Card
                title="Contact budget performance"
                description="Measured on the reserved test set, not on current customers."
              >
                <Curve
                  data={evaluation.data.contact_metrics}
                  x="k"
                  lines={['precision', 'recall', 'lift']}
                />
              </Card>
              {metrics && (
                <Card title="Outcomes on the test set">
                  <Confusion m={metrics} />
                </Card>
              )}
              <JsonDetails
                data={evaluation.data}
                label="All final metrics and calibration checks"
              />
            </>
          ) : (
            <Card>
              <div className="mx-auto max-w-lg py-8 text-center">
                <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-slate-900 text-white shadow-lift">
                  <Lock className="size-6" />
                </span>
                <h3 className="mt-5 text-lg font-semibold text-slate-900">
                  The final test is still locked
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-slate-500">
                  A slice of your data was held back to give one honest, final
                  measurement. Reveal it only when you’ve finished tuning.
                  Afterwards this model is frozen.
                </p>
                <Notice
                  error={
                    evaluation.error instanceof ApiError &&
                    evaluation.error.status === 404
                      ? null
                      : evaluation.error
                  }
                />
                <div className="mt-6 text-left">
                  <Confirm checked={freeze} onChange={setFreeze}>
                    I’m done tuning. Freeze this model and evaluate it on the
                    reserved test set.
                  </Confirm>
                </div>
                <Button
                  className="mt-4"
                  variant="dark"
                  icon={ShieldCheck}
                  disabled={!freeze}
                  loading={action.isPending}
                  onClick={() => void queue('evaluate', { run_id: id })}
                >
                  Run final evaluation
                </Button>
              </div>
            </Card>
          ))}

        {view === 'tools' && (
          <div className="grid gap-6 xl:grid-cols-2">
            <Card
              title="Diagnostics"
              icon={FlaskConical}
              description="Which inputs matter, contact curves, score reliability and segment performance."
            >
              <div className="space-y-4">
                <Field label="Compare performance by segment (optional)">
                  <Select
                    value={segment}
                    onChange={(e) => setSegment(e.target.value)}
                  >
                    <option value="">No segment comparison</option>
                    {profile.data?.columns
                      .filter(
                        (c) =>
                          c.name !== report.target_column &&
                          c.unique_count <= 20,
                      )
                      .map((c) => (
                        <option key={c.name}>{c.name}</option>
                      ))}
                  </Select>
                </Field>
                <Field label="Benchmark against a simple rule (optional)">
                  <Select
                    value={heuristic}
                    onChange={(e) => setHeuristic(e.target.value)}
                  >
                    <option value="">No rule benchmark</option>
                    {profile.data?.columns
                      .filter(
                        (c) =>
                          c.inferred_type === 'numeric' &&
                          report.feature_columns.includes(c.name),
                      )
                      .map((c) => (
                        <option key={c.name}>{c.name}</option>
                      ))}
                  </Select>
                </Field>
                {heuristic && (
                  <Field label="Rule direction">
                    <Select
                      value={direction}
                      onChange={(e) => setDirection(e.target.value)}
                    >
                      <option value="higher_risk">
                        Higher values = higher risk
                      </option>
                      <option value="lower_risk">
                        Lower values = higher risk
                      </option>
                    </Select>
                  </Field>
                )}
                <Button
                  variant="primary"
                  loading={action.isPending}
                  onClick={() =>
                    void queue('diagnostics', {
                      run_id: id,
                      segment_column: segment || null,
                      heuristic_column: heuristic || null,
                      heuristic_direction: direction,
                    })
                  }
                >
                  Create diagnostics
                </Button>
              </div>
            </Card>
            <div className="space-y-6">
              <Card
                title="Calibrate scores"
                description="Fit a calibration on development data. Creates a separate model; this one stays saved."
              >
                <Button
                  disabled={Boolean(evaluation.data)}
                  loading={action.isPending}
                  onClick={() => void queue('calibrate', { run_id: id })}
                >
                  Create calibrated model
                </Button>
              </Card>
              <Card
                title="See why leakage misleads"
                description="A teaching run with a deliberately invalid future input. Never used for scoring."
              >
                <Button
                  loading={action.isPending}
                  onClick={() =>
                    void queue('leakage-demo', { task_id: report.task_id })
                  }
                >
                  Run leakage demonstration
                </Button>
              </Card>
              <JsonDetails
                data={{ ...report, calibration: r.calibration }}
                label="Parameters, inputs and provenance"
              />
            </div>
          </div>
        )}
      </div>
      <NextStep
        title="Score your current customers"
        description="Upload today’s customers and rank them by churn risk with this model."
        to={`/app/scores/new?run=${id}`}
        label="Score customers"
      />
    </>
  );
}

function Confusion({
  m,
}: {
  m: NonNullable<RunData['report']['results'][number]['validation']>;
}) {
  const cells = [
    [
      'Churners caught',
      m.true_positive,
      'True positives',
      'bg-emerald-50 text-emerald-800 ring-emerald-200',
    ],
    [
      'False alarms',
      m.false_positive,
      'False positives',
      'bg-amber-50 text-amber-800 ring-amber-200',
    ],
    [
      'Churners missed',
      m.false_negative,
      'False negatives',
      'bg-rose-50 text-rose-800 ring-rose-200',
    ],
    [
      'Correctly left alone',
      m.true_negative,
      'True negatives',
      'bg-slate-50 text-slate-700 ring-slate-200',
    ],
  ] as const;
  return (
    <div className="grid grid-cols-2 gap-3">
      {cells.map(([label, value, tech, tone]) => (
        <div key={label} className={cn('rounded-xl p-4 ring-1', tone)}>
          <p className="text-xs font-medium opacity-80">{label}</p>
          <p className="mt-1 font-mono text-2xl font-bold tabular">
            {number(value)}
          </p>
          <p className="text-[11px] opacity-60">{tech}</p>
        </div>
      ))}
    </div>
  );
}
