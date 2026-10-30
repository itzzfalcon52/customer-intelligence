import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Check,
  FileSpreadsheet,
  FlaskConical,
  Gauge,
  HeartHandshake,
  ListOrdered,
  Loader2,
  PlayCircle,
  Sparkles,
  Upload,
  Users,
  Wallet,
} from 'lucide-react';
import { authClient } from '../../lib/auth';
import { BriefCard } from '../brief-ui';
import { column, date, metric, model, number, quality } from '../format';
import { useResource } from '../queries';
import { useWorkspaceStore } from '../store';
import type { CustomerPage, Run } from '../types';
import { Donut, Histogram } from '../charts';
import {
  AnimatedNumber,
  Badge,
  ButtonLink,
  Card,
  Loading,
  Notice,
  Reveal,
  RiskBadge,
  ScoreBar,
  Stat,
  StateBadge,
  Table,
  Td,
  Th,
  Tr,
} from '../ui';
import { buttonClass, cn, riskLevel } from '../style';
import {
  JOB_LABEL,
  jobResultLink,
  useDemoPipeline,
  useWorkflow,
  type Stage,
} from '../workflow';

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

export function Overview() {
  const flow = useWorkflow();
  if (flow.isPending) return <Loading />;
  if (flow.ready) return <Dashboard />;
  return <Onboarding />;
}

/* ---------------------------------------------------------------- Before scoring */

function StageCard({ stage, index }: { stage: Stage; index: number }) {
  const Icon = stage.icon;
  const done = stage.status === 'done';
  const next = stage.status === 'active' || stage.status === 'running';
  return (
    <Reveal delay={0.05 * index} className="h-full">
      <Link
        to={stage.status === 'todo' ? stage.home : stage.to}
        className={cn(
          'group relative flex h-full flex-col rounded-2xl bg-white p-5 shadow-card ring-1 transition hover:-translate-y-0.5 hover:shadow-lift',
          next ? 'ring-2 ring-brand-500' : 'ring-slate-200/80',
        )}
      >
        <div className="flex items-center justify-between">
          <span
            className={cn(
              'grid size-10 place-items-center rounded-xl',
              done
                ? 'bg-brand-50 text-brand-600'
                : next
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-100 text-slate-400',
            )}
          >
            <Icon className="size-5" strokeWidth={1.9} />
          </span>
          {done ? (
            <Badge tone="success">
              <Check className="size-3" /> Done
            </Badge>
          ) : stage.status === 'running' ? (
            <Badge tone="info">
              <Loader2 className="size-3 animate-spin" /> Running
            </Badge>
          ) : next ? (
            <Badge tone="brand">Up next</Badge>
          ) : null}
        </div>
        <p className="mt-4 text-xs font-medium text-slate-400">
          Step {stage.step}
        </p>
        <p className="mt-0.5 text-[15px] font-semibold text-slate-900">
          {stage.verb}
        </p>
        <p className="mt-1.5 flex-1 text-[13px] leading-relaxed text-slate-500">
          {stage.summary}
        </p>
        <span
          className={cn(
            'mt-4 inline-flex items-center gap-1 text-[13px] font-medium',
            next
              ? 'text-brand-700'
              : 'text-slate-500 group-hover:text-slate-800',
          )}
        >
          {done ? 'Review' : next ? 'Start this step' : 'Learn more'}
          <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
        </span>
      </Link>
    </Reveal>
  );
}

function PipelineArt() {
  const nodes = [
    ['Upload', FileSpreadsheet],
    ['Define', Gauge],
    ['Train', BrainCircuit],
    ['Rank', ListOrdered],
    ['Act', HeartHandshake],
  ] as const;
  return (
    <div className="relative hidden h-full min-h-[220px] items-center justify-center lg:flex">
      <div className="relative flex items-center gap-3">
        {nodes.map(([label, Icon], i) => (
          <div key={label} className="flex items-center gap-3">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.12 }}
              className="flex flex-col items-center gap-2"
            >
              <span className="grid size-12 place-items-center rounded-2xl bg-white/10 ring-1 ring-white/15 backdrop-blur">
                <Icon className="size-5 text-brand-300" strokeWidth={1.8} />
              </span>
              <span className="text-[11px] font-medium text-slate-400">
                {label}
              </span>
            </motion.div>
            {i < nodes.length - 1 && (
              <div className="relative mb-6 h-px w-8 overflow-hidden bg-white/15">
                <motion.span
                  className="absolute inset-y-0 w-3 bg-brand-300"
                  animate={{ x: [-12, 32] }}
                  transition={{
                    duration: 1.4,
                    repeat: Infinity,
                    delay: i * 0.25,
                    ease: 'easeInOut',
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Onboarding() {
  const flow = useWorkflow();
  const session = authClient.useSession();
  const demo = useDemoPipeline();
  const first = session.data?.user.name.split(' ')[0];
  const started = flow.completed > 0;
  const next = flow.next;
  return (
    <>
      <Reveal>
        <section className="relative overflow-hidden rounded-3xl bg-ink-900 p-8 text-white shadow-pop sm:p-10">
          <div className="grid-bg absolute inset-0 opacity-30 [mask-image:radial-gradient(ellipse_at_top_right,black,transparent_70%)]" />
          <div className="absolute -top-24 -right-24 size-72 rounded-full bg-brand-500/25 blur-3xl" />
          <div className="relative grid gap-8 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <Badge
                tone="brand"
                className="bg-brand-500/15 text-brand-200 ring-brand-400/30"
              >
                <Sparkles className="size-3" />
                {started
                  ? `${flow.completed} of 5 steps complete`
                  : 'Welcome to your workspace'}
              </Badge>
              <h1
                className="mt-5 text-[38px] leading-[0.95] font-[840] tracking-[-0.015em] text-balance [word-spacing:0.08em] sm:text-[52px]"
                style={{ fontStretch: '68%' }}
              >
                {greeting()}
                {first ? `, ${first}` : ''}.{' '}
                {started
                  ? 'Let’s finish your churn model.'
                  : 'Let’s find the customers you’re about to lose.'}
              </h1>
              <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-slate-300">
                Five steps take you from a customer export to a ranked list of
                at-risk accounts and a contact plan. Every number is computed
                from your data, and AI answers are checked against it.
              </p>
              <div className="mt-7 flex flex-wrap gap-3">
                {next && started ? (
                  <Link to={next.to} className={buttonClass('primary', 'lg')}>
                    Continue: {next.verb}
                    <ArrowRight className="size-4" />
                  </Link>
                ) : (
                  <button
                    onClick={() => void demo.start()}
                    disabled={demo.isPending}
                    className={buttonClass('primary', 'lg')}
                  >
                    {demo.isPending ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <PlayCircle className="size-4" />
                    )}
                    {demo.isPending
                      ? 'Setting up the demo…'
                      : 'Run the demo in one click'}
                  </button>
                )}
                <Link
                  to="/app/data"
                  className="inline-flex h-11 items-center gap-2 rounded-xl bg-white/10 px-5 text-[15px] font-medium text-white ring-1 ring-white/15 transition hover:bg-white/15"
                >
                  <Upload className="size-4" />
                  Upload your own data
                </Link>
              </div>
              {!started && (
                <p className="mt-4 text-xs leading-relaxed text-slate-400">
                  The demo uploads 600 clearly labelled synthetic accounts,
                  defines churn and starts training. It needs the worker running
                  (<code className="font-mono">pnpm worker:api</code>).
                </p>
              )}
              {demo.error && (
                <div className="mt-4">
                  <Notice error={demo.error} />
                </div>
              )}
            </div>
            <PipelineArt />
          </div>
        </section>
      </Reveal>

      <div className="mt-10 mb-4 flex items-end justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-900">
            Your workflow
          </h2>
          <p className="text-sm text-slate-500">
            Each step unlocks the next. You can always go back.
          </p>
        </div>
        <span className="hidden text-sm font-medium text-slate-500 sm:block">
          {flow.completed} of 5 complete
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {flow.stages.map((s, i) => (
          <StageCard key={s.key} stage={s} index={i} />
        ))}
      </div>

      <div className="mt-10 grid gap-6 lg:grid-cols-3">
        <Card title="What you need" icon={FileSpreadsheet}>
          <ul className="space-y-3 text-sm text-slate-600">
            {[
              'A CSV or Excel export of past customers (up to 1 million rows)',
              'A column that says whether each customer churned',
              'Fields known before churn: tenure, usage, plan, tickets…',
              'Later, a second file of current customers to score',
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-brand-600" />
                {t}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="What you get" icon={Sparkles}>
          <ul className="space-y-3 text-sm text-slate-600">
            {[
              'A ranked list of the accounts most likely to churn',
              'A fair comparison of four models, with honest metrics',
              'Investigations into which segments churn most',
              'A budgeted contact plan and reviewable outreach drafts',
            ].map((t) => (
              <li key={t} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-brand-600" />
                {t}
              </li>
            ))}
          </ul>
        </Card>
        <RecentActivity />
      </div>
    </>
  );
}

/* ---------------------------------------------------------------- After scoring */

function RecentActivity() {
  const flow = useWorkflow();
  const jobs = flow.jobs.slice(0, 5);
  return (
    <Card
      title="Recent activity"
      icon={Activity}
      action={
        <Link
          to="/app/jobs"
          className="text-[13px] font-medium text-brand-700 hover:text-brand-800"
        >
          All jobs
        </Link>
      }
    >
      {jobs.length ? (
        <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-[5px] before:w-px before:bg-slate-200">
          {jobs.map((j) => (
            <li key={j.id} className="relative flex items-start gap-3 pl-6">
              <span
                className={cn(
                  'absolute top-1.5 left-0 size-[11px] rounded-full ring-2 ring-white',
                  j.state === 'succeeded'
                    ? 'bg-emerald-500'
                    : j.state === 'failed'
                      ? 'bg-rose-500'
                      : j.state === 'running'
                        ? 'bg-sky-500'
                        : 'bg-amber-400',
                )}
              />
              <div className="min-w-0 flex-1">
                <Link
                  to={jobResultLink(j)}
                  className="text-sm font-medium text-slate-900 hover:text-brand-700"
                >
                  {JOB_LABEL[j.kind] ?? j.kind}
                </Link>
                <p className="text-xs text-slate-500">{date(j.created_at)}</p>
              </div>
              <StateBadge state={j.state} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm leading-relaxed text-slate-500">
          Training, scoring and analysis jobs show up here as they run.
        </p>
      )}
    </Card>
  );
}

function Dashboard() {
  const flow = useWorkflow();
  const session = authClient.useSession();
  const setAsk = useWorkspaceStore((s) => s.setAsk);
  const score = flow.latest.score!;
  const run = flow.runs.find((r) => r.run_id === score.run_id);
  const report = useResource<Run>(`/api/v1/runs/${score.run_id}`);
  const chosen = report.data?.report.results.find(
    (c) => c.candidate_id === report.data?.report.best_validation_candidate_id,
  )?.validation;
  const grade = chosen
    ? quality(
        chosen.average_precision,
        chosen.positive_count / Math.max(1, chosen.row_count),
      )
    : null;
  const sample = useResource<CustomerPage>(
    `/api/v1/scores/${score.id}/customers?offset=0&limit=500`,
  );
  const total = score.row_count;
  const high = Math.max(1, Math.round(total * 0.1));
  const elevated = Math.round(total * 0.3) - high;
  const customers = sample.data?.customers ?? [];
  const exposure = customers
    .filter((c) => c.rank <= high)
    .reduce((sum, c) => sum + (c.exposure_proxy ?? 0), 0);
  const first = session.data?.user.name.split(' ')[0];
  const actions = [
    [
      HeartHandshake,
      'Plan who to contact',
      'Budget, contact count and drafts',
      `/app/plays?run=${score.run_id}`,
    ],
    [
      FlaskConical,
      'Investigate why they churn',
      'Verified segment analysis',
      '/app/investigate',
    ],
    [
      BrainCircuit,
      'Review the model',
      'Metrics, tradeoffs and final test',
      `/app/models/${score.run_id}`,
    ],
  ] as const;
  return (
    <>
      <BriefCard scoreId={score.id} runId={score.run_id} />
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-500">
            {greeting()}
            {first ? `, ${first}` : ''}
          </p>
          <h1
            className="mt-1 text-[32px] leading-[0.95] font-[840] tracking-[-0.015em] text-tag-ink [word-spacing:0.08em] sm:text-[42px]"
            style={{ fontStretch: '68%' }}
          >
            Here’s who needs attention
          </h1>
          <p className="mt-1.5 text-[15px] text-slate-500">
            Latest scoring of {number(total)} accounts on{' '}
            {date(score.created_at)}. Rankings are relative risk within this
            batch, not guaranteed outcomes.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ButtonLink to={`/app/scores/new?run=${score.run_id}`} icon={Upload}>
            Score new data
          </ButtonLink>
          <ButtonLink
            to={`/app/plays?run=${score.run_id}`}
            variant="primary"
            trailing={ArrowRight}
          >
            Plan who to contact
          </ButtonLink>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Reveal>
          <Stat
            label="Accounts scored"
            icon={Users}
            tone="info"
            value={<AnimatedNumber value={total} />}
            hint="In the latest batch"
          />
        </Reveal>
        <Reveal delay={0.05}>
          <Stat
            label="High-risk accounts"
            icon={AlertTriangle}
            tone="danger"
            value={<AnimatedNumber value={high} />}
            hint="Top 10% by risk score"
          />
        </Reveal>
        <Reveal delay={0.1}>
          {score.value_column ? (
            <Stat
              label="Value exposure (high risk)"
              icon={Wallet}
              tone="warning"
              value={
                <AnimatedNumber
                  value={exposure}
                  format={(n) => number(Math.round(n))}
                />
              }
              hint={`Risk × ${column(score.value_column)}: a proxy, not revenue`}
            />
          ) : (
            <Stat
              label="Contact budget"
              icon={Wallet}
              tone="warning"
              value={<AnimatedNumber value={score.contact_count} />}
              hint="Accounts on the shortlist"
            />
          )}
        </Reveal>
        <Reveal delay={0.15}>
          <Stat
            label="Model quality"
            icon={Gauge}
            tone="brand"
            value={
              <span className="flex items-center gap-2">
                {grade
                  ? `${grade.lift.toFixed(1)}×`
                  : run
                    ? metric(run.average_precision)
                    : '—'}
                {grade && <Badge tone={grade.tone}>{grade.band}</Badge>}
              </span>
            }
            hint={
              grade
                ? `Better than random at finding churners · ${model(run!.model)}`
                : run
                  ? `${model(run.model)} · avg. precision`
                  : 'No model'
            }
          />
        </Reveal>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Risk distribution"
          description={
            total > 500
              ? 'Risk scores of the 500 highest-ranked accounts.'
              : 'How risk scores spread across this batch.'
          }
          action={
            <div className="hidden items-center gap-3 text-xs text-slate-500 sm:flex">
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-rose-500" />≥ 0.7
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-amber-500" />
                0.4–0.7
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2 rounded-full bg-slate-400" />
                &lt; 0.4
              </span>
            </div>
          }
        >
          {sample.isPending ? (
            <div className="skeleton h-56" />
          ) : (
            <Histogram
              scores={customers.map((c) => c.risk_score)}
              height={240}
            />
          )}
        </Card>
        <Card
          title="Risk mix"
          description="Share of the batch in each band, by rank."
        >
          <Donut
            data={[
              { name: 'High', value: high, color: '#d7262e' },
              { name: 'Elevated', value: elevated, color: '#f2b91f' },
              {
                name: 'Lower',
                value: total - high - elevated,
                color: '#c3cbc5',
              },
            ]}
            center={{ value: number(total), label: 'accounts' }}
          />
          <div className="mt-4 space-y-2 text-sm">
            {(
              [
                ['High', high, 'bg-rose-500'],
                ['Elevated', elevated, 'bg-amber-500'],
                ['Lower', total - high - elevated, 'bg-slate-300'],
              ] as const
            ).map(([l, v, c]) => (
              <div key={l} className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-slate-600">
                  <span className={cn('size-2.5 rounded-sm', c)} />
                  {l}
                </span>
                <span className="font-medium text-slate-900 tabular">
                  {number(v)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card
          className="xl:col-span-2"
          title="Highest-risk accounts"
          description="Start your outreach here."
          action={
            <ButtonLink
              to={`/app/scores/${score.id}`}
              size="sm"
              trailing={ArrowUpRight}
            >
              View all {number(total)}
            </ButtonLink>
          }
        >
          {sample.isPending ? (
            <div className="skeleton h-72" />
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Rank</Th>
                  <Th>Account</Th>
                  <Th>Risk</Th>
                  <Th align="right">Risk score</Th>
                  {score.value_column && (
                    <Th align="right">{column(score.value_column)}</Th>
                  )}
                </tr>
              </thead>
              <tbody>
                {customers.slice(0, 8).map((c) => (
                  <Tr key={c.row_reference}>
                    <Td mono className="text-slate-400">
                      #{c.rank}
                    </Td>
                    <Td className="font-medium whitespace-nowrap text-slate-900">
                      {c.customer_id}
                    </Td>
                    <Td>
                      <RiskBadge level={riskLevel(c.rank, total)} />
                    </Td>
                    <Td align="right">
                      <ScoreBar value={c.risk_score} />
                    </Td>
                    {score.value_column && (
                      <Td align="right" mono>
                        {c.customer_value == null
                          ? '—'
                          : number(c.customer_value)}
                      </Td>
                    )}
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <div className="space-y-6">
          <Card title="Suggested next actions" icon={Sparkles}>
            <div className="-mx-2 space-y-1">
              {actions.map(([Icon, t, d, to]) => (
                <Link
                  key={t}
                  to={to}
                  className="group flex items-center gap-3 rounded-xl p-2 transition hover:bg-slate-50"
                >
                  <span className="grid size-9 place-items-center rounded-lg bg-brand-50 text-brand-600">
                    <Icon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium text-slate-900">
                      {t}
                    </span>
                    <span className="block text-xs text-slate-500">{d}</span>
                  </span>
                  <ArrowRight className="size-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-600" />
                </Link>
              ))}
              <button
                onClick={() => setAsk(true)}
                className="group flex w-full cursor-pointer items-center gap-3 rounded-xl p-2 text-left transition hover:bg-slate-50"
              >
                <span className="grid size-9 place-items-center rounded-lg bg-slate-900 text-brand-300">
                  <Sparkles className="size-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-slate-900">
                    Ask AI about this batch
                  </span>
                  <span className="block text-xs text-slate-500">
                    Answers checked against results
                  </span>
                </span>
                <ArrowRight className="size-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-600" />
              </button>
            </div>
          </Card>
          <RecentActivity />
        </div>
      </div>
    </>
  );
}
