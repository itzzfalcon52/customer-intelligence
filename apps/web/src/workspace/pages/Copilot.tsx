import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowUp,
  CheckCircle2,
  Database,
  ShieldAlert,
  Sparkles,
  Wrench,
} from 'lucide-react';
import { jobKey, streamPost, type StreamEvent } from '../api';
import { date, model } from '../format';
import {
  useAction,
  useAnalyses,
  useResource,
  useScores,
  useTasks,
} from '../queries';
import { useWorkspaceStore } from '../store';
import type { Conversation, Dataset, Message, RunSummary } from '../types';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Field,
  Notice,
  PageHeader,
  Select,
} from '../ui';
import { cn } from '../style';
import { LiveSteps, TracePanel } from '../trace-ui';

const STARTERS = [
  'How good is the model at finding churners?',
  'Which accounts should we contact first and why?',
  'Are there data quality issues I should fix?',
  'Explain the precision and recall tradeoff simply.',
];

function Verification({ v }: { v: NonNullable<Message['verification']> }) {
  if (v.grounded)
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="size-3.5" />
        {v.numbers_checked} numbers checked against tool outputs
        {v.revised ? ' (revised once)' : ''}
      </span>
    );
  const parts = [];
  if (v.ungrounded.length)
    parts.push(`not found in any tool output: ${v.ungrounded.join(', ')}`);
  if (v.causal_claims?.length)
    parts.push(
      `causal wording the evidence doesn’t support (${v.causal_claims.join(', ')})`,
    );
  return (
    <span className="inline-flex items-start gap-1.5 text-xs font-medium text-amber-700">
      <ShieldAlert className="mt-0.5 size-3.5 shrink-0" />
      Unverified: {parts.join('; ')}.
    </span>
  );
}

export function Copilot({
  compact = false,
  initial = {},
}: {
  /** Drawer mode: no page heading, context folded into a single row. */
  compact?: boolean;
  initial?: { dataset?: string; run?: string; score?: string };
}) {
  const [params] = useSearchParams();
  const [dataset, setDataset] = useState(
    initial.dataset || params.get('dataset') || '',
  );
  const [task, setTask] = useState(params.get('task') || '');
  const [run, setRun] = useState(initial.run || params.get('run') || '');
  const [score, setScore] = useState(initial.score || '');
  const [analysis, setAnalysis] = useState('');
  const [conversation, setConversation] = useState('');
  const [question, setQuestion] = useState(params.get('question') || '');
  const [previous, setPrevious] = useState('');
  const [training, setTraining] = useState(false);
  const [actions, setActions] = useState(false);
  const [key, setKey] = useState(jobKey);
  const [steps, setSteps] = useState<StreamEvent[]>([]);
  const consent = useWorkspaceStore((s) => s.providerConsent);
  const grantConsent = useWorkspaceStore((s) => s.consent);
  const datasets = useResource<Dataset[]>('/api/v1/datasets?limit=100');
  const tasks = useTasks();
  const runs = useResource<RunSummary[]>('/api/v1/runs?limit=100');
  const scores = useScores();
  const analyses = useAnalyses();
  const conversations = useResource<{ id: string; created_at: string }[]>(
    `/api/v1/assistant/conversations?dataset_id=${dataset}`,
    Boolean(dataset),
  );
  const history = useResource<Conversation>(
    `/api/v1/assistant/conversations/${conversation}`,
    Boolean(conversation),
  );
  const end = useRef<HTMLDivElement>(null);
  const send = useAction<Message, string>(async (text) => {
    setSteps([]);
    const final = await streamPost(
      '/api/v1/assistant/messages/stream',
      {
        dataset_id: dataset,
        task_id: task || null,
        run_id: run || null,
        score_id: score || null,
        analysis_id: analysis || null,
        conversation_id: conversation || null,
        idempotency_key: key,
        question: text,
        allow_training: training,
        allow_actions: actions,
        workspace_tools: true,
      },
      (event) => setSteps((current) => [...current, event]),
    );
    return final.response as Message;
  });
  // A run or scoring batch from the current page implies its dataset and task
  // (state adjusted during render once the catalog loads; see React "derived state").
  if (!dataset) {
    const runId =
      run ||
      scores.data?.find((s) => s.id === score)?.run_id ||
      runs.data?.find((r) => !r.error)?.run_id ||
      '';
    const taskId = runs.data?.find((r) => r.run_id === runId)?.task_id;
    const owner = tasks.data?.find((t) => t.id === taskId);
    if (owner) {
      setDataset(owner.dataset_id);
      setTask(owner.id);
      if (runId && runId !== run) setRun(runId);
    } else if (
      !runs.isPending &&
      !tasks.isPending &&
      !scores.isPending &&
      datasets.data?.[0]
    )
      setDataset(datasets.data[0].id);
  }
  const turns = [...(history.data?.turns || [])];
  if (
    send.data &&
    !turns.some((t) => t.response.turn_id === send.data!.turn_id)
  )
    turns.push({ question: previous, response: send.data, created_at: '' });
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, send.isPending, steps.length]);
  async function submit(text = question.trim()) {
    if (!text || !dataset || !consent) return;
    setPrevious(text);
    setQuestion('');
    try {
      const response = await send.mutateAsync(text);
      setConversation(response.conversation_id);
      setKey(jobKey());
    } catch {
      setQuestion(text); /* same idempotency key retained for retry */
    }
  }
  const reset = () => {
    send.reset();
    setKey(jobKey());
  };
  const runLabel = runs.data?.find((r) => r.run_id === run);
  const contextPanel = (
    <div className="space-y-4">
      <Field label="Dataset">
        <Select
          value={dataset}
          onChange={(e) => {
            setDataset(e.target.value);
            setTask('');
            setRun('');
            setScore('');
            setAnalysis('');
            setConversation('');
            setTraining(false);
            reset();
          }}
        >
          <option value="">Choose a dataset</option>
          {datasets.data?.map((d) => (
            <option value={d.id} key={d.id}>
              {d.original_filename}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Model (optional)">
        <Select
          value={run}
          onChange={(e) => {
            setRun(e.target.value);
            setTask(
              runs.data?.find((r) => r.run_id === e.target.value)?.task_id ||
                '',
            );
            setScore('');
            setAnalysis('');
            setConversation('');
            reset();
          }}
        >
          <option value="">No model</option>
          {runs.data
            ?.filter(
              (r) =>
                !r.error &&
                tasks.data?.some(
                  (t) => t.dataset_id === dataset && t.id === r.task_id,
                ),
            )
            .map((r) => (
              <option value={r.run_id} key={r.run_id}>
                {model(r.model)} · {date(r.created_at)}
              </option>
            ))}
        </Select>
      </Field>
      <Field label="Scoring batch (optional)">
        <Select
          value={score}
          onChange={(e) => {
            setScore(e.target.value);
            setKey(jobKey());
          }}
        >
          <option value="">No scoring batch</option>
          {scores.data
            ?.filter((s) => s.dataset_id === dataset || s.run_id === run)
            .map((s) => (
              <option value={s.id} key={s.id}>
                {s.row_count} accounts · {date(s.created_at)}
              </option>
            ))}
        </Select>
      </Field>
      <Field label="Analysis (optional)">
        <Select
          value={analysis}
          onChange={(e) => {
            setAnalysis(e.target.value);
            setKey(jobKey());
          }}
        >
          <option value="">No analysis</option>
          {analyses.data
            ?.filter(
              (a) =>
                a.run_id === run || a.task_id === task || a.score_id === score,
            )
            .map((a, i) => (
              <option value={a.id} key={a.id}>
                {String(a.kind ?? 'Analysis').replaceAll('_', ' ')} {i + 1}
              </option>
            ))}
        </Select>
      </Field>
      <Field label="Conversation">
        <Select
          value={conversation}
          onChange={(e) => {
            setConversation(e.target.value);
            reset();
          }}
        >
          <option value="">New conversation</option>
          {conversations.data?.map((c) => (
            <option key={c.id} value={c.id}>
              Conversation · {date(c.created_at)}
            </option>
          ))}
        </Select>
      </Field>
      <div className="space-y-3 border-t border-slate-100 pt-4">
        <Checkbox
          checked={actions}
          onChange={(v) => {
            setActions(v);
            setKey(jobKey());
          }}
          description="Schema review, rule checks, general drafts, budget maths. Nothing is sent to customers."
        >
          Allow AI actions
        </Checkbox>
        <Checkbox
          checked={training}
          disabled={!task}
          onChange={(v) => {
            setTraining(v);
            setKey(jobKey());
          }}
          description="Only the fixed default training plan."
        >
          Allow queuing a training run
        </Checkbox>
      </div>
    </div>
  );
  const chat = (
    <div
      className={cn(
        'flex min-h-0 flex-col',
        compact
          ? 'h-full'
          : 'h-[calc(100vh-15rem)] min-h-[560px] rounded-2xl bg-white shadow-card ring-1 ring-slate-200/80',
      )}
    >
      {compact && (
        <details className="border-b border-slate-100 px-5 py-3">
          <summary className="flex cursor-pointer items-center gap-2 text-xs font-medium text-slate-500">
            <Database className="size-3.5" />
            <span className="truncate">
              Context:{' '}
              {datasets.data?.find((d) => d.id === dataset)
                ?.original_filename ?? 'none'}
              {runLabel && ` · ${model(runLabel.model)}`}
            </span>
          </summary>
          <div className="pt-4">{contextPanel}</div>
        </details>
      )}
      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-5 py-6">
        {!consent ? (
          <div className="mx-auto max-w-sm py-6 text-center">
            <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-900 shadow-lift">
              <Sparkles className="size-5 text-brand-300" />
            </span>
            <h3 className="mt-4 text-base font-semibold text-slate-900">
              Before you ask
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-500">
              Your question, aggregate profiles, settings, results and recent
              conversation are sent to Nemotron on Nebius. Raw customer sheets
              are never sent. Don’t include passwords or personal data.
            </p>
            <Button
              className="mt-5"
              variant="dark"
              onClick={() => grantConsent()}
            >
              I understand, enable Ask AI
            </Button>
          </div>
        ) : turns.length || send.isPending ? (
          turns.map((t, index) => (
            <div key={t.response.turn_id || index} className="space-y-3">
              <div className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-2.5 text-sm text-white">
                  {t.question}
                </p>
              </div>
              <motion.div
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex gap-3"
              >
                <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-brand-50 ring-1 ring-brand-200">
                  <Sparkles className="size-3.5 text-brand-600" />
                </span>
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="prose-chat text-[14.5px] text-slate-700">
                    <ReactMarkdown
                      skipHtml
                      disallowedElements={['img']}
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {t.response.answer}
                    </ReactMarkdown>
                  </div>
                  {t.response.verification && (
                    <Verification v={t.response.verification} />
                  )}
                  {t.response.events.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {t.response.events.map((event, i) => {
                        const badge = (
                          <Badge key={i} className="font-mono text-[11px]">
                            <Wrench className="size-3" />{' '}
                            {event.tool.replaceAll('_', ' ')}
                          </Badge>
                        );
                        const playbook = event.evidence_path?.match(
                          /^\/api\/v1\/playbooks\/([0-9a-f-]{36})/,
                        );
                        return playbook ? (
                          <Link key={i} to={`/app/playbooks/${playbook[1]}`}>
                            {badge}
                          </Link>
                        ) : (
                          badge
                        );
                      })}
                    </div>
                  )}
                  {t.response.trace_id && (
                    <TracePanel traceId={t.response.trace_id} />
                  )}
                </div>
              </motion.div>
            </div>
          ))
        ) : (
          <div className="py-4">
            <div className="text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-2xl bg-brand-50 ring-1 ring-brand-200">
                <Sparkles className="size-5 text-brand-600" />
              </span>
              <h3 className="mt-4 text-base font-semibold text-slate-900">
                What would you like to know?
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                Answers use your saved results. Numbers are checked before you
                see them.
              </p>
            </div>
            <div
              className={cn('mt-6 grid gap-2', !compact && 'sm:grid-cols-2')}
            >
              {STARTERS.map((s) => (
                <button
                  key={s}
                  disabled={!dataset}
                  onClick={() => void submit(s)}
                  className="cursor-pointer rounded-xl px-4 py-3 text-left text-[13px] text-slate-600 ring-1 ring-slate-200 transition hover:bg-slate-50 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {send.isPending && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <p className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-900 px-4 py-2.5 text-sm text-white">
                {previous}
              </p>
            </div>
            <LiveSteps events={steps} />
          </div>
        )}
        <Notice error={send.error || history.error || datasets.error} />
        <div ref={end} />
      </div>
      <form
        className="border-t border-slate-100 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="flex items-end gap-2 rounded-xl bg-white p-2 shadow-card ring-1 ring-slate-200 focus-within:ring-2 focus-within:ring-brand-500">
          <textarea
            value={question}
            rows={1}
            onChange={(e) => {
              setQuestion(e.target.value);
              setKey(jobKey());
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
            maxLength={2000}
            placeholder={
              dataset
                ? 'Ask about your data or results…'
                : 'Upload a dataset to start asking'
            }
            aria-label="Question"
            disabled={!consent || send.isPending}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={
              !dataset || !consent || !question.trim() || send.isPending
            }
            className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-lg bg-brand-600 text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
        <p className="mt-2 text-center text-[11px] text-slate-400">
          AI can be wrong. Check the attached evidence before acting.
        </p>
      </form>
    </div>
  );
  if (compact) return chat;
  return (
    <>
      <PageHeader
        eyebrow={
          <Badge tone="violet">
            <Sparkles className="size-3" /> Nemotron · Nebius
          </Badge>
        }
        title="Ask AI"
        description="Ask anything about your data, models and scores. Every number in an answer is checked against the tool outputs that produced it."
      />
      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
        {chat}
        <Card
          title="Context"
          icon={Database}
          description="What the assistant can look at."
        >
          {contextPanel}
        </Card>
      </div>
    </>
  );
}
