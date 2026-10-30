import { useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowRight,
  CheckCircle2,
  Columns3,
  Copy,
  Database,
  FileSpreadsheet,
  Hash,
  PlayCircle,
  Rows3,
  Search,
  Target,
  Trash2,
  Plug,
  Type,
  UploadCloud,
  X,
} from 'lucide-react';
import {
  DEFAULT_LIMITS,
  request,
  validateFile,
  type UploadLimits,
} from '../api';
import { number } from '../format';
import { useAction, useDatasets, useResource, useTasks } from '../queries';
import type { Dataset, Profile as ProfileData } from '../types';
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  Caveats,
  Checkbox,
  EmptyState,
  Field,
  Input,
  Loading,
  Modal,
  Notice,
  Pagination,
  PageHeader,
  Progress,
  Reveal,
  Stat,
  Table,
  Tabs,
  Td,
  Th,
  Tr,
} from '../ui';
import { cn } from '../style';
import { HowItWorks, NextStep, StagePill, WorkflowSteps } from '../workflow-ui';
import { useUploadDemo } from '../workflow';

export function Datasets() {
  const [page, setPage] = useState(0);
  const data = useDatasets(page);
  const tasks = useTasks();
  const [file, setFile] = useState<File | null>(null);
  const [sheet, setSheet] = useState('');
  const [error, setError] = useState('');
  const [drag, setDrag] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const demo = useUploadDemo();
  const capabilities = useResource<{ limits: UploadLimits }>(
    '/api/v1/capabilities',
  );
  const limits = capabilities.data?.limits ?? DEFAULT_LIMITS;
  const upload = useAction<Dataset, File>(async (selected) => {
    validateFile(selected, limits);
    const body = new FormData();
    body.append('file', selected);
    return request<Dataset>(
      `/api/v1/datasets/upload${sheet.trim() ? `?sheet_name=${encodeURIComponent(sheet.trim())}` : ''}`,
      { method: 'POST', body },
    );
  });
  function pick(selected?: File) {
    if (!selected) return;
    try {
      validateFile(selected, limits);
      setFile(selected);
      setSheet('');
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function submit() {
    if (!file) return;
    try {
      const result = await upload.mutateAsync(file);
      navigate(`/app/data/${result.id}`);
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
  const defined = new Set(tasks.data?.map((t) => t.dataset_id));
  return (
    <>
      <WorkflowSteps current="data" />
      <PageHeader
        eyebrow={<StagePill stage="data" />}
        title="Upload customer history"
        description="Start with an export of past customers that includes whether each one churned. We check the file’s quality before anything is trained."
        actions={
          <div className="flex flex-wrap gap-2">
            <ButtonLink
              to="/app/sources#connectors"
              variant="primary"
              icon={Plug}
            >
              Connect billing or CRM
            </ButtonLink>
            <ButtonLink to="/app/sources">Multi-table CSV bundle</ButtonLink>
          </div>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6">
          <Reveal>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                pick(e.dataTransfer.files[0]);
              }}
              className={cn(
                'relative overflow-hidden rounded-2xl border-2 border-dashed bg-white p-10 text-center transition-colors',
                drag
                  ? 'border-brand-500 bg-brand-50/50'
                  : 'border-slate-200 hover:border-slate-300',
              )}
            >
              <div className="grid-bg pointer-events-none absolute inset-0 opacity-50 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" />
              <div className="relative">
                <motion.div
                  animate={drag ? { y: -4, scale: 1.05 } : { y: 0, scale: 1 }}
                  className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-600 text-white shadow-lift"
                >
                  <UploadCloud className="size-6" />
                </motion.div>
                <AnimatePresence mode="wait">
                  {file ? (
                    <motion.div
                      key="file"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                    >
                      <div className="mx-auto mt-5 flex max-w-sm items-center gap-3 rounded-xl bg-slate-50 p-3 text-left ring-1 ring-slate-200">
                        <FileSpreadsheet className="size-8 shrink-0 text-brand-600" />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-slate-900">
                            {file.name}
                          </p>
                          <p className="text-xs text-slate-500">
                            {file.size > 1024 * 1024
                              ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                              : `${(file.size / 1024).toFixed(1)} KB`}{' '}
                            · ready to import
                            {file.size > 50 * 1024 * 1024 &&
                              ' · large file: checking and training will take longer'}
                          </p>
                        </div>
                        <button
                          onClick={() => setFile(null)}
                          className="cursor-pointer rounded p-1 text-slate-400 hover:text-slate-700"
                          aria-label="Remove file"
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                      {file.name.toLowerCase().endsWith('.xlsx') && (
                        <div className="mx-auto mt-4 max-w-sm text-left">
                          <Field label="Excel sheet name (optional)">
                            <Input
                              value={sheet}
                              onChange={(e) => setSheet(e.target.value)}
                              placeholder="Leave blank to use the first sheet"
                            />
                          </Field>
                        </div>
                      )}
                      <Button
                        variant="primary"
                        size="lg"
                        className="mt-5"
                        loading={upload.isPending}
                        onClick={() => void submit()}
                      >
                        {upload.isPending
                          ? 'Importing…'
                          : 'Import and check quality'}
                        {!upload.isPending && <ArrowRight className="size-4" />}
                      </Button>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                    >
                      <p className="mt-5 text-base font-semibold text-slate-900">
                        Drag your customer file here
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        CSV up to {limits.upload_mib} MB or Excel (.xlsx) up to{' '}
                        {limits.excel_mib} MB · {number(limits.rows)} rows
                      </p>
                      <div className="mt-5 flex flex-wrap justify-center gap-2">
                        <Button
                          variant="primary"
                          onClick={() => input.current?.click()}
                        >
                          Browse files
                        </Button>
                        <Button
                          icon={PlayCircle}
                          loading={demo.isPending}
                          onClick={() => void loadDemo()}
                        >
                          Use synthetic demo data
                        </Button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
                <input
                  ref={input}
                  type="file"
                  accept=".csv,.xlsx"
                  className="hidden"
                  aria-label="Choose customer file"
                  onChange={(e) => pick(e.target.files?.[0])}
                />
              </div>
            </div>
          </Reveal>
          <Notice error={error || upload.error || demo.error} />
          <Card
            title="Your datasets"
            description="Open one to check its quality and define churn."
            icon={Database}
          >
            {data.isPending ? (
              <div className="skeleton h-32" />
            ) : data.data?.length ? (
              <>
                <Table>
                  <thead>
                    <tr>
                      <Th>File</Th>
                      <Th align="right">Rows</Th>
                      <Th align="right">Columns</Th>
                      <Th>Status</Th>
                      <Th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.data.map((d) => (
                      <Tr key={d.id}>
                        <Td>
                          <Link
                            to={`/app/data/${d.id}`}
                            className="flex items-center gap-3 font-medium text-slate-900 hover:text-brand-700"
                          >
                            <span className="grid size-8 place-items-center rounded-lg bg-emerald-50 text-emerald-600">
                              <FileSpreadsheet className="size-4" />
                            </span>
                            <span className="truncate">
                              {d.original_filename}
                            </span>
                            {d.original_filename.startsWith('DEMO-') && (
                              <Badge tone="violet">Synthetic</Badge>
                            )}
                          </Link>
                        </Td>
                        <Td align="right" mono>
                          {number(d.row_count)}
                        </Td>
                        <Td align="right" mono>
                          {d.column_count}
                        </Td>
                        <Td>
                          {defined.has(d.id) ? (
                            <Badge tone="success" dot>
                              Churn defined
                            </Badge>
                          ) : (
                            <Badge
                              tone={defined.size ? 'neutral' : 'warning'}
                              dot
                            >
                              {defined.size
                                ? 'No churn definition'
                                : 'Needs churn definition'}
                            </Badge>
                          )}
                        </Td>
                        <Td align="right">
                          <ButtonLink
                            size="sm"
                            variant={defined.size ? 'secondary' : 'primary'}
                            to={
                              defined.has(d.id) || defined.size
                                ? `/app/data/${d.id}`
                                : `/app/data/${d.id}/churn`
                            }
                          >
                            {defined.has(d.id) || defined.size
                              ? 'Open'
                              : 'Define churn'}
                          </ButtonLink>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
                <Pagination
                  page={page}
                  setPage={setPage}
                  count={data.data.length}
                />
              </>
            ) : (
              <EmptyState
                compact
                icon={FileSpreadsheet}
                title="No datasets yet"
                description="Upload a file above, or try the synthetic demo to see the whole workflow."
              />
            )}
          </Card>
        </div>
        <div className="space-y-6">
          <HowItWorks
            points={[
              {
                title: 'Export past customers',
                body: 'One row per customer, from your billing system or CRM. Include customers who stayed and who left.',
              },
              {
                title: 'Include the outcome',
                body: 'A column such as “Churn” with values like Yes/No. This is what the model learns to predict.',
              },
              {
                title: 'We check quality',
                body: 'Missing values, duplicates and column types are profiled before any training.',
              },
            ]}
            footer="Files stay in your private workspace. Raw rows are never sent to the AI provider."
          />
          <Card title="Example file" bodyClassName="p-0">
            <div className="overflow-x-auto">
              <table className="w-full font-mono text-[11.5px]">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    {['id', 'tenure', 'plan', 'tickets', 'Churn'].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-slate-700">
                  {[
                    ['A-104', '23', 'Annual', '0', 'No'],
                    ['A-221', '4', 'Monthly', '5', 'Yes'],
                    ['A-310', '41', 'Monthly', '1', 'No'],
                  ].map((r) => (
                    <tr key={r[0]} className="border-t border-slate-100">
                      {r.map((c, i) => (
                        <td
                          key={i}
                          className={cn(
                            'px-3 py-2',
                            i === 4 && 'font-semibold text-brand-700',
                          )}
                        >
                          {c}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
      <NextStep
        title="Define what churn means"
        description="Choose the outcome column and the inputs the model may use."
        to={data.data?.[0] ? `/app/data/${data.data[0].id}/churn` : '/app/data'}
        label="Define churn"
        disabled={!data.data?.length}
      />
    </>
  );
}

const TYPE_ICON = { numeric: Hash, string: Type, empty: X } as const;

export function Profile() {
  const { id } = useParams();
  const query = useResource<ProfileData>(
    `/api/v1/datasets/${id}/profile`,
    Boolean(id),
  );
  const tasks = useTasks();
  const [tab, setTab] = useState<'columns' | 'preview'>('columns');
  const [search, setSearch] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [cascade, setCascade] = useState(false);
  const navigate = useNavigate();
  const remove = useAction<void, void>(() =>
    request(`/api/v1/datasets/${id}${cascade ? '?cascade=true' : ''}`, {
      method: 'DELETE',
    }),
  );
  if (query.isPending) return <Loading />;
  if (!query.data) return <Notice error={query.error} />;
  const d = query.data;
  const cells = d.row_count * d.column_count;
  const missing = d.columns.reduce((sum, c) => sum + c.missing_count, 0);
  const completeness = cells ? 100 - (missing / cells) * 100 : 100;
  const hasTask = tasks.data?.some((t) => t.dataset_id === id);
  async function destroy() {
    try {
      await remove.mutateAsync();
      navigate('/app/data');
    } catch {
      /* rendered */
    }
  }
  return (
    <>
      <WorkflowSteps current="data" />
      <PageHeader
        back={{ to: '/app/data', label: 'All datasets' }}
        eyebrow={<StagePill stage="data" />}
        title={d.original_filename}
        description="Check that the data looks right before you define churn and train a model."
        actions={
          <>
            <Button
              variant="ghost"
              icon={Trash2}
              onClick={() => setDeleting(true)}
            >
              Delete
            </Button>
            <ButtonLink
              variant="primary"
              to={`/app/data/${id}/churn`}
              icon={Target}
              trailing={ArrowRight}
            >
              {hasTask ? 'Define churn again' : 'Define churn'}
            </ButtonLink>
          </>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Reveal>
          <Stat
            label="Rows"
            icon={Rows3}
            tone="info"
            value={number(d.row_count)}
            hint="Customers in the file"
          />
        </Reveal>
        <Reveal delay={0.05}>
          <Stat
            label="Columns"
            icon={Columns3}
            tone="violet"
            value={d.column_count}
            hint={`${d.columns.filter((c) => c.inferred_type === 'numeric').length} numeric`}
          />
        </Reveal>
        <Reveal delay={0.1}>
          <Stat
            label="Completeness"
            icon={CheckCircle2}
            tone="brand"
            value={`${completeness.toFixed(1)}%`}
            hint={`${number(missing)} missing cells`}
          >
            <Progress value={completeness} className="mt-3" />
          </Stat>
        </Reveal>
        <Reveal delay={0.15}>
          <Stat
            label="Duplicate rows"
            icon={Copy}
            tone={d.duplicate_row_count ? 'warning' : 'neutral'}
            value={number(d.duplicate_row_count)}
            hint={
              d.duplicate_row_count ? 'Review before training' : 'None found'
            }
          />
        </Reveal>
      </div>
      <div className="mt-6">
        {d.warnings.length ? (
          <Caveats items={d.warnings} />
        ) : (
          <div className="flex items-center gap-2 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800 ring-1 ring-emerald-200">
            <CheckCircle2 className="size-4 text-emerald-600" />
            No quality warnings. Still confirm what each field means and when it
            is known.
          </div>
        )}
      </div>
      <Card
        className="mt-6"
        title={tab === 'columns' ? 'Column health' : 'Data preview'}
        description={
          tab === 'columns'
            ? 'Type, completeness and distinct values for each column.'
            : 'First rows, as imported. Private: not sent to the AI.'
        }
        action={
          <div className="flex items-center gap-2">
            {tab === 'columns' && (
              <div className="relative hidden sm:block">
                <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Find a column"
                  className="w-52 pl-9"
                  aria-label="Find a column"
                />
              </div>
            )}
            <Tabs
              value={tab}
              onChange={setTab}
              tabs={[
                { value: 'columns', label: 'Columns' },
                { value: 'preview', label: 'Preview' },
              ]}
            />
          </div>
        }
      >
        <Table>
          {tab === 'columns' ? (
            <>
              <thead>
                <tr>
                  <Th>Column</Th>
                  <Th>Type</Th>
                  <Th>Completeness</Th>
                  <Th align="right">Distinct</Th>
                  <Th align="right">Range</Th>
                </tr>
              </thead>
              <tbody>
                {d.columns
                  .filter((c) =>
                    c.name.toLowerCase().includes(search.toLowerCase()),
                  )
                  .map((c) => {
                    const Icon = TYPE_ICON[c.inferred_type];
                    const present = 100 - c.missing_percentage;
                    return (
                      <Tr key={c.name}>
                        <Td className="font-medium text-slate-900">{c.name}</Td>
                        <Td>
                          <span className="inline-flex items-center gap-1.5 text-slate-600">
                            <Icon className="size-3.5 text-slate-400" />
                            {c.inferred_type === 'numeric'
                              ? 'Number'
                              : c.inferred_type === 'string'
                                ? 'Text'
                                : 'Empty'}
                          </span>
                        </Td>
                        <Td>
                          <div className="flex items-center gap-3">
                            <div className="h-1.5 w-28 overflow-hidden rounded-full bg-slate-100">
                              <div
                                className={cn(
                                  'h-full rounded-full',
                                  present > 95
                                    ? 'bg-emerald-500'
                                    : present > 70
                                      ? 'bg-amber-500'
                                      : 'bg-rose-500',
                                )}
                                style={{ width: `${present}%` }}
                              />
                            </div>
                            <span className="font-mono text-xs text-slate-500 tabular">
                              {present.toFixed(1)}%
                            </span>
                          </div>
                        </Td>
                        <Td align="right" mono>
                          {number(c.unique_count)}
                        </Td>
                        <Td align="right" mono className="text-slate-500">
                          {c.numeric_summary
                            ? `${c.numeric_summary.minimum ?? '—'} – ${c.numeric_summary.maximum ?? '—'}`
                            : '—'}
                        </Td>
                      </Tr>
                    );
                  })}
              </tbody>
            </>
          ) : (
            <>
              <thead>
                <tr>
                  {d.columns.map((c) => (
                    <Th key={c.name}>{c.name}</Th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.preview.map((row, index) => (
                  <Tr key={index}>
                    {d.columns.map((c) => (
                      <Td key={c.name} className="whitespace-nowrap">
                        {row[c.name] ?? (
                          <span className="text-slate-400 italic">missing</span>
                        )}
                      </Td>
                    ))}
                  </Tr>
                ))}
              </tbody>
            </>
          )}
        </Table>
      </Card>
      <NextStep
        title="Define what churn means for this file"
        description="Pick the outcome column and confirm which inputs are known in advance."
        to={`/app/data/${id}/churn`}
        label="Define churn"
      />
      <Modal
        open={deleting}
        onClose={() => setDeleting(false)}
        title={`Delete ${d.original_filename}?`}
      >
        <p className="text-sm text-slate-600">
          This cannot be undone. Active jobs must finish or be cancelled first.
        </p>
        <Checkbox className="mt-4" checked={cascade} onChange={setCascade}>
          Also delete dependent churn definitions, models, scores and
          conversations.
        </Checkbox>
        <div className="mt-4">
          <Notice error={remove.error} />
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button onClick={() => setDeleting(false)}>Keep dataset</Button>
          <Button
            variant="danger"
            loading={remove.isPending}
            onClick={() => void destroy()}
          >
            Delete permanently
          </Button>
        </div>
      </Modal>
    </>
  );
}
