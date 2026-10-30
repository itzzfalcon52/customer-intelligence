import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Fingerprint,
  ListChecks,
  Loader2,
  Target,
  XCircle,
} from 'lucide-react';
import { post } from '../api';
import { number } from '../format';
import { useAction, useDatasets, useResource, useTasks } from '../queries';
import type { Profile, Task, TaskInput, TargetCheck } from '../types';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Card,
  Confirm,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  Tr,
} from '../ui';
import { cn } from '../style';
import { HowItWorks, NextStep, StagePill, WorkflowSteps } from '../workflow-ui';

/** Step 2 home: every saved churn definition, and where to make a new one. */
export function ChurnDefinitions() {
  const tasks = useTasks();
  const datasets = useDatasets();
  const name = (id: string) =>
    datasets.data?.find((d) => d.id === id)?.original_filename ?? 'Dataset';
  const pending = datasets.data?.filter(
    (d) => !tasks.data?.some((t) => t.dataset_id === d.id),
  );
  return (
    <>
      <WorkflowSteps current="target" />
      <PageHeader
        eyebrow={<StagePill stage="target" />}
        title="Define what churn means"
        description="A churn definition tells the model which column is the outcome, which value means “churned”, and which inputs it may learn from."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          {!!pending?.length && (
            <Card title="Datasets waiting for a definition" icon={Target}>
              <div className="-mx-2 space-y-1">
                {pending.map((d) => (
                  <Link
                    key={d.id}
                    to={`/app/data/${d.id}/churn`}
                    className="group flex items-center gap-3 rounded-xl p-3 transition hover:bg-slate-50"
                  >
                    <span className="grid size-9 place-items-center rounded-lg bg-amber-50 text-amber-600">
                      <Target className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-slate-900">
                        {d.original_filename}
                      </span>
                      <span className="block text-xs text-slate-500">
                        {number(d.row_count)} rows · {d.column_count} columns
                      </span>
                    </span>
                    <span className="flex items-center gap-1 text-[13px] font-medium text-brand-700">
                      Define churn{' '}
                      <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" />
                    </span>
                  </Link>
                ))}
              </div>
            </Card>
          )}
          <Card
            title="Saved churn definitions"
            description="Each one can be trained as many times as you like."
            icon={ListChecks}
          >
            {tasks.isPending ? (
              <div className="skeleton h-32" />
            ) : tasks.data?.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Outcome</Th>
                    <Th>Dataset</Th>
                    <Th align="right">Inputs</Th>
                    <Th>Customer ID</Th>
                    <Th />
                  </tr>
                </thead>
                <tbody>
                  {tasks.data.map((t) => (
                    <Tr key={t.id}>
                      <Td>
                        <span className="font-medium text-slate-900">
                          {t.target_column}
                        </span>
                        <span className="text-slate-400"> = </span>
                        <Badge tone="brand">{t.positive_label}</Badge>
                      </Td>
                      <Td className="max-w-56 truncate">
                        {name(t.dataset_id)}
                      </Td>
                      <Td align="right" mono>
                        {t.feature_columns.length}
                      </Td>
                      <Td className="font-mono text-xs text-slate-500">
                        {t.id_column ?? '—'}
                      </Td>
                      <Td align="right">
                        <ButtonLink
                          size="sm"
                          variant="primary"
                          to={`/app/models/new?task=${t.id}`}
                        >
                          Train model
                        </ButtonLink>
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <EmptyState
                compact
                icon={Target}
                title="No churn definitions yet"
                description="Upload a dataset first, then define churn for it."
                action={
                  <ButtonLink to="/app/data" variant="primary">
                    Go to customer data
                  </ButtonLink>
                }
              />
            )}
          </Card>
        </div>
        <HowItWorks
          points={[
            {
              title: 'Pick the outcome',
              body: 'A column with two values, such as Churn = Yes / No. Pick the value that means the customer left.',
            },
            {
              title: 'Keep IDs out',
              body: 'Customer IDs identify rows in the ranked list but are never used for learning.',
            },
            {
              title: 'Only use what you know in advance',
              body: 'Cancellation dates or reasons leak the answer. Exclude anything recorded after churn.',
            },
          ]}
        />
      </div>
      <NextStep
        title="Train and compare models"
        description="Four model families compete on the same split; the best one is selected."
        to={
          tasks.data?.[0]
            ? `/app/models/new?task=${tasks.data[0].id}`
            : '/app/churn'
        }
        label="Train a model"
        disabled={!tasks.data?.length}
      />
    </>
  );
}

export function DefineChurn() {
  const { id } = useParams();
  const data = useResource<Profile>(
    `/api/v1/datasets/${id}/profile`,
    Boolean(id),
  );
  if (data.isPending) return <Loading />;
  if (!data.data) return <Notice error={data.error} />;
  return <DefineForm key={id} id={id!} profile={data.data} />;
}

function Section({
  n,
  title,
  description,
  done,
  children,
}: {
  n: number;
  title: string;
  description: string;
  done: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="relative rounded-2xl bg-white p-6 shadow-card ring-1 ring-slate-200/80">
      <div className="flex items-start gap-4">
        <span
          className={cn(
            'grid size-8 shrink-0 place-items-center rounded-full text-sm font-semibold transition-colors',
            done ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-500',
          )}
        >
          {done ? <Check className="size-4" strokeWidth={3} /> : n}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
          <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>
          <div className="mt-5">{children}</div>
        </div>
      </div>
    </section>
  );
}

function DefineForm({ id, profile }: { id: string; profile: Profile }) {
  const suggestedTarget =
    profile.columns.find((c) => /^churn(ed)?(_within_\d+d)?$/i.test(c.name))
      ?.name || '';
  const suggestedId =
    profile.columns.find(
      (c) =>
        /^(snapshot_?id|customer_?id|account_?id|id)$/i.test(c.name) &&
        c.unique_count === profile.row_count &&
        c.missing_count === 0,
    )?.name || '';
  const [target, setTarget] = useState(suggestedTarget);
  const [positive, setPositive] = useState(suggestedTarget ? 'Yes' : '');
  const [identifier, setIdentifier] = useState(suggestedId);
  // Snapshot datasets carry a date column; evaluating in time order is then the honest default.
  const dateColumns = profile.columns
    .filter(
      (c) =>
        /(^|_)(date|day)$|_at$/i.test(c.name) && c.inferred_type === 'string',
    )
    .map((c) => c.name);
  const [time, setTime] = useState(
    dateColumns.find((c) => /^snapshot_?date$/i.test(c)) ?? '',
  );
  const eligible = (t: string, idc: string) =>
    profile.columns
      .filter(
        (c) =>
          c.name !== t &&
          c.name !== idc &&
          !dateColumns.includes(c.name) &&
          !/^account_?id$/i.test(c.name) &&
          c.unique_count > 1 &&
          c.inferred_type !== 'empty' &&
          (c.inferred_type === 'numeric' || c.unique_count <= 100) &&
          !/^(churn_?(date|reason)|cancellation_?(date|reason)|cancelled_?at|terminated_?at)$/i.test(
            c.name,
          ),
      )
      .map((c) => c.name);
  const [features, setFeatures] = useState<string[]>(() =>
    eligible(suggestedTarget, suggestedId),
  );
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const check = useAction<
    TargetCheck,
    { target_column: string; positive_label: string }
  >((body) => post(`/api/v1/datasets/${id}/target-check`, body));
  const save = useAction<Task, TaskInput>((body) =>
    post(`/api/v1/datasets/${id}/tasks`, body),
  );
  function changeTarget(value: string) {
    setTarget(value);
    setFeatures((prev) => prev.filter((n) => n !== value));
    check.reset();
    setConfirmed(false);
  }
  async function submit() {
    if (!check.data?.target_valid || !confirmed || !features.length) {
      setError(
        'Check the outcome, select at least one input and confirm before saving.',
      );
      return;
    }
    try {
      const task = await save.mutateAsync({
        target_column: target,
        positive_label: positive,
        id_column: identifier || null,
        feature_columns: features.filter((f) => f !== time),
        features_available_at_prediction: true,
        time_column: time || null,
      });
      navigate(`/app/models/new?task=${task.id}`);
    } catch {
      /* rendered */
    }
  }
  const counts = check.data ? Object.entries(check.data.class_counts) : [];
  const totalCount = counts.reduce((s, [, n]) => s + n, 0);
  const candidates = profile.columns.filter(
    (c) => c.name !== target && c.name !== identifier && c.name !== time,
  );
  return (
    <>
      <WorkflowSteps current="target" />
      <PageHeader
        back={{ to: `/app/data/${id}`, label: profile.original_filename }}
        eyebrow={<StagePill stage="target" />}
        title="Define what churn means"
        description="Three quick choices. We’ve pre-filled what looks right. Check each one before saving."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          <Section
            n={1}
            title="Which column is the outcome?"
            description="A column with exactly two values, such as Yes/No."
            done={Boolean(check.data?.target_valid)}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Outcome column">
                <Select
                  value={target}
                  onChange={(e) => changeTarget(e.target.value)}
                >
                  <option value="">Choose a column</option>
                  {profile.columns.map((c) => (
                    <option key={c.name}>{c.name}</option>
                  ))}
                </Select>
              </Field>
              <Field
                label="Value that means “churned”"
                hint="Exactly as it appears in the file."
              >
                <Input
                  value={positive}
                  onChange={(e) => {
                    setPositive(e.target.value);
                    check.reset();
                  }}
                  placeholder="e.g. Yes"
                />
              </Field>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                loading={check.isPending}
                disabled={!target || !positive}
                onClick={() =>
                  check.mutate({
                    target_column: target,
                    positive_label: positive,
                  })
                }
              >
                Check outcome
              </Button>
              {check.data &&
                (check.data.target_valid ? (
                  <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-700">
                    <CheckCircle2 className="size-4" /> Valid two-class outcome
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 text-sm font-medium text-rose-700">
                    <XCircle className="size-4" /> Needs attention
                  </span>
                ))}
            </div>
            <div className="mt-3">
              <Notice error={check.error} />
            </div>
            {check.data && counts.length > 0 && (
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-4 space-y-2"
              >
                {counts.map(([label, count]) => (
                  <div key={label} className="flex items-center gap-3 text-sm">
                    <span className="w-24 truncate font-medium text-slate-700">
                      {label}
                    </span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <motion.div
                        className={cn(
                          'h-full rounded-full',
                          label === positive ? 'bg-rose-500' : 'bg-slate-400',
                        )}
                        initial={{ width: 0 }}
                        animate={{
                          width: `${(count / Math.max(1, totalCount)) * 100}%`,
                        }}
                      />
                    </div>
                    <span className="w-24 text-right font-mono text-xs text-slate-500 tabular">
                      {number(count)} ·{' '}
                      {((count / Math.max(1, totalCount)) * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
                {check.data.blockers.map((b) => (
                  <Alert key={b} tone="danger">
                    {b}
                  </Alert>
                ))}
              </motion.div>
            )}
          </Section>

          <Section
            n={2}
            title="Which column identifies each customer?"
            description="Used to match scores back to accounts. Never used for learning."
            done={Boolean(identifier)}
          >
            <Field label="Customer ID column (optional)" className="max-w-sm">
              <Select
                value={identifier}
                onChange={(e) => {
                  setIdentifier(e.target.value);
                  setFeatures((prev) =>
                    prev.filter((f) => f !== e.target.value),
                  );
                }}
              >
                <option value="">No ID column</option>
                {profile.columns
                  .filter((c) => c.name !== target)
                  .map((c) => (
                    <option key={c.name}>{c.name}</option>
                  ))}
              </Select>
            </Field>
          </Section>

          <Section
            n={3}
            title="Which inputs may the model use?"
            description="Only fields that are known before a customer churns."
            done={features.length > 0}
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[13px] text-slate-500">
                <span className="font-semibold text-slate-900">
                  {features.length}
                </span>{' '}
                of {candidates.length} selected
              </span>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setFeatures(eligible(target, identifier))}
                >
                  Suggested
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setFeatures([])}
                >
                  Clear
                </Button>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {candidates.map((c) => {
                const on = features.includes(c.name);
                return (
                  <button
                    key={c.name}
                    type="button"
                    onClick={() =>
                      setFeatures((prev) =>
                        on
                          ? prev.filter((n) => n !== c.name)
                          : [...prev, c.name],
                      )
                    }
                    className={cn(
                      'flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-left ring-1 transition',
                      on
                        ? 'bg-brand-50/70 ring-brand-300'
                        : 'bg-white ring-slate-200 hover:ring-slate-300',
                    )}
                  >
                    <span
                      className={cn(
                        'grid size-5 shrink-0 place-items-center rounded-md transition',
                        on
                          ? 'bg-brand-600 text-white'
                          : 'ring-1 ring-slate-300',
                      )}
                    >
                      {on && <Check className="size-3.5" strokeWidth={3} />}
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-900">
                        {c.name}
                      </span>
                      <span className="block text-xs text-slate-500">
                        {c.inferred_type === 'numeric' ? 'Number' : 'Text'} ·{' '}
                        {number(c.unique_count)} distinct
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </Section>

          {dateColumns.length > 0 && (
            <Section
              n={4}
              title="Evaluate in time order?"
              description="For snapshot data, test on the most recent period, the way the model will be used."
              done={Boolean(time)}
            >
              <Field
                label="Date column"
                className="max-w-sm"
                hint="The newest dates become the final test set. Never used as an input."
              >
                <Select
                  value={time}
                  onChange={(e) => {
                    setTime(e.target.value);
                    setFeatures((prev) =>
                      prev.filter((f) => f !== e.target.value),
                    );
                  }}
                >
                  <option value="">No, use a random split</option>
                  {dateColumns.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </Select>
              </Field>
            </Section>
          )}

          <Confirm checked={confirmed} onChange={setConfirmed}>
            These inputs are known before a customer churns, and the outcome
            reflects what we want to predict.
          </Confirm>
          <Notice error={error || save.error} />
          <div className="flex items-center justify-end gap-3">
            <ButtonLink to={`/app/data/${id}`} variant="ghost">
              Cancel
            </ButtonLink>
            <Button
              variant="primary"
              size="lg"
              disabled={save.isPending}
              onClick={() => void submit()}
            >
              {save.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Fingerprint className="size-4" />
              )}
              Save and continue to training
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>
        <div className="space-y-6 lg:sticky lg:top-24 lg:self-start">
          <Card title="Summary">
            <dl className="space-y-3 text-sm">
              {[
                [
                  'Outcome',
                  target ? `${target} = ${positive || '…'}` : 'Not chosen',
                ],
                ['Customer ID', identifier || 'None'],
                ['Inputs', `${features.length} columns`],
                [
                  'Outcome check',
                  check.data
                    ? check.data.target_valid
                      ? 'Passed'
                      : 'Failed'
                    : 'Not run',
                ],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3">
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="truncate text-right font-medium text-slate-900">
                    {v}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>
          <HowItWorks
            title="Avoid these mistakes"
            points={[
              {
                title: 'Future information',
                body: 'Cancellation dates, reasons or “last login after churn” give away the answer and make results look too good.',
              },
              {
                title: 'IDs as inputs',
                body: 'An ID can’t predict behaviour; the model would just memorise rows.',
              },
              {
                title: 'Free text',
                body: 'Columns with hundreds of unique text values are left out by default.',
              },
            ]}
          />
        </div>
      </div>
    </>
  );
}
