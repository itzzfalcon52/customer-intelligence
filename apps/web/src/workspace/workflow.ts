import { useNavigate } from 'react-router-dom';
import {
  Database,
  Target,
  BrainCircuit,
  ListOrdered,
  HeartHandshake,
  type LucideIcon,
} from 'lucide-react';
import { post, request } from './api';
import {
  useAction,
  useAnalyses,
  useDatasets,
  useJobs,
  useRuns,
  useScores,
  useTasks,
} from './queries';
import type { Dataset, Job, Task } from './types';

export type StageKey = 'data' | 'target' | 'train' | 'score' | 'act';
export type StageStatus = 'done' | 'active' | 'running' | 'todo';
export interface Stage {
  key: StageKey;
  step: number;
  title: string;
  verb: string;
  summary: string;
  icon: LucideIcon;
  /** Where the step's work happens. */
  to: string;
  /** Where its section lives in navigation. */
  home: string;
  status: StageStatus;
}

const COPY: Record<
  StageKey,
  Pick<Stage, 'title' | 'verb' | 'summary' | 'icon' | 'home'>
> = {
  data: {
    title: 'Customer data',
    verb: 'Upload customer history',
    summary:
      'A CSV or Excel export of past customers, including whether each one churned.',
    icon: Database,
    home: '/app/data',
  },
  target: {
    title: 'Churn definition',
    verb: 'Define what churn means',
    summary:
      'Pick the outcome column, the value that means “churned”, and the inputs known in advance.',
    icon: Target,
    home: '/app/churn',
  },
  train: {
    title: 'Models',
    verb: 'Train and compare models',
    summary:
      'Four model families are trained on the same split and compared fairly. The best one is selected.',
    icon: BrainCircuit,
    home: '/app/models',
  },
  score: {
    title: 'Risk scores',
    verb: 'Score current customers',
    summary:
      'Apply the model to today’s customers and get a ranked list of who is most at risk.',
    icon: ListOrdered,
    home: '/app/scores',
  },
  act: {
    title: 'Retention plays',
    verb: 'Plan who to contact',
    summary:
      'Set a contact budget, test cost assumptions and prepare reviewable outreach drafts.',
    icon: HeartHandshake,
    home: '/app/plays',
  },
};
export const STAGE_ORDER: StageKey[] = [
  'data',
  'target',
  'train',
  'score',
  'act',
];
export const stageCopy = (key: StageKey) => COPY[key];

/** The five-step workflow, derived from what exists in the workspace. */
export function useWorkflow() {
  const datasets = useDatasets();
  const tasks = useTasks();
  const runs = useRuns();
  const scores = useScores();
  const analyses = useAnalyses();
  const jobs = useJobs();
  const dataset = datasets.data?.[0];
  const task = tasks.data?.[0];
  const run = runs.data?.find((r) => !r.error);
  const score = scores.data?.[0];
  const active = (kind: string) =>
    jobs.data?.some(
      (j) => j.kind === kind && ['queued', 'running'].includes(j.state),
    );
  const acted = analyses.data?.some((a) =>
    ['campaign', 'executive_briefing', 'rule_challenger'].includes(
      String(a.kind),
    ),
  );
  const done: Record<StageKey, boolean> = {
    data: Boolean(dataset),
    target: Boolean(task),
    train: Boolean(run),
    score: Boolean(score),
    act: Boolean(acted),
  };
  const running: Record<StageKey, boolean> = {
    data: false,
    target: false,
    train: Boolean(active('train')),
    score: Boolean(active('score')),
    act: false,
  };
  const to: Record<StageKey, string> = {
    data: '/app/data',
    target: dataset ? `/app/data/${dataset.id}/churn` : '/app/data',
    train: task ? `/app/models/new?task=${task.id}` : '/app/churn',
    score: run ? `/app/scores/new?run=${run.run_id}` : '/app/models',
    act: run ? `/app/plays?run=${run.run_id}` : '/app/scores',
  };
  const firstOpen = STAGE_ORDER.find((k) => !done[k]);
  const stages: Stage[] = STAGE_ORDER.map((key, i) => ({
    key,
    step: i + 1,
    ...COPY[key],
    to: to[key],
    status: running[key]
      ? 'running'
      : done[key]
        ? 'done'
        : key === firstOpen
          ? 'active'
          : 'todo',
  }));
  const completed = STAGE_ORDER.filter((k) => done[k]).length;
  return {
    stages,
    next: stages.find((s) => s.status === 'active' || s.status === 'running'),
    completed,
    ready: done.score,
    latest: { dataset, task, run, score },
    runs: runs.data ?? [],
    jobs: jobs.data ?? [],
    isPending:
      datasets.isPending ||
      tasks.isPending ||
      runs.isPending ||
      scores.isPending,
    error: datasets.error || tasks.error || runs.error || scores.error,
  };
}

/** Explicitly synthetic demo data. Deterministic; never presented as a real connection. */
export function demoCSV() {
  const rows = [
    'customerID,tenure,usage_minutes,support_ticket_count,MonthlyCharges,Contract,Churn',
  ];
  let state = 47291;
  const random = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 4294967296;
  };
  for (let i = 0; i < 600; i++) {
    const tenure = 1 + Math.floor(random() * 60),
      usage = Math.floor(random() * 1200),
      tickets = Math.floor(random() * 6),
      spend = 20 + Math.floor(random() * 100);
    const risk =
      1 / (1 + Math.exp(-(-1.7 + tickets * 0.42 - usage / 900 - tenure / 60)));
    const churn = random() < risk;
    rows.push(
      [
        `DEMO-${String(i + 1).padStart(4, '0')}`,
        tenure,
        usage,
        tickets,
        spend,
        i % 3 ? 'Monthly' : 'Annual',
        churn ? 'Yes' : 'No',
      ].join(','),
    );
  }
  return rows.join('\n');
}

export function useUploadDemo() {
  return useAction<Dataset, undefined>(async () => {
    const body = new FormData();
    body.append(
      'file',
      new File([demoCSV()], 'DEMO-synthetic-saas-customers.csv', {
        type: 'text/csv',
      }),
    );
    return request('/api/v1/datasets/upload', { method: 'POST', body });
  });
}

/**
 * One click: upload the synthetic demo, save the obvious churn definition, and queue
 * training with the default plan. Each step is a real API call the user could make by hand.
 */
export function useDemoPipeline() {
  const navigate = useNavigate();
  const action = useAction<Job, undefined>(async () => {
    const body = new FormData();
    body.append(
      'file',
      new File([demoCSV()], 'DEMO-synthetic-saas-customers.csv', {
        type: 'text/csv',
      }),
    );
    const dataset = await request<Dataset>('/api/v1/datasets/upload', {
      method: 'POST',
      body,
    });
    const task = await post<Task>(`/api/v1/datasets/${dataset.id}/tasks`, {
      target_column: 'Churn',
      positive_label: 'Yes',
      id_column: 'customerID',
      feature_columns: [
        'tenure',
        'usage_minutes',
        'support_ticket_count',
        'MonthlyCharges',
        'Contract',
      ],
      features_available_at_prediction: true,
    });
    return post<Job>('/api/v1/jobs/train', {
      task_id: task.id,
      search_trials: 0,
      threshold: 0.5,
      cv_folds: 3,
      generate_briefing: false,
      threshold_policy: 'f1',
      minimum_recall: 0.5,
      idempotency_key: crypto.randomUUID(),
    });
  });
  return {
    ...action,
    start: async () => {
      try {
        await action.mutateAsync(undefined);
        navigate('/app/jobs');
      } catch {
        /* the error is rendered by the caller */
      }
    },
  };
}

export const JOB_LABEL: Record<string, string> = {
  train: 'Model training',
  score: 'Customer scoring',
  evaluate: 'Final evaluation',
  diagnostics: 'Model diagnostics',
  calibrate: 'Score calibration',
  explain: 'Customer explanation',
  'leakage-demo': 'Leakage demonstration',
  leakage_demo: 'Leakage demonstration',
};
export function jobResultLink(job: Job) {
  if (!job.result_id) return '/app/jobs';
  if (['train', 'calibrate', 'evaluate'].includes(job.kind))
    return `/app/models/${job.result_id}`;
  if (job.kind === 'score') return `/app/scores/${job.result_id}`;
  return `/app/analyses/${job.result_id}`;
}
