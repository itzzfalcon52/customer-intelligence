import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { ArrowRight, Check, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from './style';
import { useWorkflow, type Stage, type StageKey } from './workflow';

function StepDot({ stage, current }: { stage: Stage; current: boolean }) {
  return (
    <span
      className={cn(
        'relative grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold transition-colors',
        stage.status === 'done' && 'bg-brand-600 text-white',
        stage.status === 'running' && 'bg-sky-500 text-white',
        stage.status === 'active' &&
          'bg-white text-brand-700 ring-2 ring-brand-500 animate-pulse-ring',
        stage.status === 'todo' &&
          'bg-white text-slate-400 ring-1 ring-slate-300',
        current && stage.status !== 'done' && 'ring-2 ring-brand-500',
      )}
    >
      {stage.status === 'done' ? (
        <Check className="size-3.5" strokeWidth={3} />
      ) : stage.status === 'running' ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : (
        stage.step
      )}
    </span>
  );
}

/** Horizontal pipeline shown on every workflow page. */
export function WorkflowSteps({ current }: { current?: StageKey }) {
  const { stages, ready } = useWorkflow();
  // A setup guide: once a first batch is scored, pages stand on their own.
  if (ready) return null;
  return (
    <nav
      aria-label="Workflow"
      className="mb-8 overflow-x-auto rounded-2xl bg-white p-2 shadow-card ring-1 ring-slate-200/80"
    >
      <ol className="flex min-w-[720px] items-center">
        {stages.map((stage, i) => {
          const here = stage.key === current;
          return (
            <li key={stage.key} className="flex flex-1 items-center">
              <Link
                to={stage.status === 'todo' ? stage.home : stage.to}
                className={cn(
                  'group flex flex-1 items-center gap-3 rounded-xl px-3 py-2.5 transition-colors',
                  here ? 'bg-brand-50/80' : 'hover:bg-slate-50',
                )}
              >
                <StepDot stage={stage} current={here} />
                <span className="min-w-0">
                  <span className="block text-[11px] font-medium text-slate-400">
                    Step {stage.step}
                  </span>
                  <span
                    className={cn(
                      'block truncate text-[13px] font-semibold',
                      here
                        ? 'text-brand-800'
                        : stage.status === 'todo'
                          ? 'text-slate-400'
                          : 'text-slate-700 group-hover:text-slate-900',
                    )}
                  >
                    {stage.title}
                  </span>
                </span>
              </Link>
              {i < stages.length - 1 && (
                <span className="mx-1 h-px w-6 shrink-0 bg-slate-200">
                  <motion.span
                    className="block h-px bg-brand-500"
                    initial={{ width: 0 }}
                    animate={{ width: stage.status === 'done' ? '100%' : 0 }}
                    transition={{ duration: 0.5, delay: i * 0.08 }}
                  />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/** Closing card on a workflow page: what to do once this step is done. */
export function NextStep({
  title,
  description,
  to,
  label,
  disabled,
}: {
  title: string;
  description: ReactNode;
  to: string;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div className="mt-8 flex flex-col items-start justify-between gap-4 rounded-2xl bg-gradient-to-r from-brand-50 via-white to-white p-5 ring-1 ring-brand-100 sm:flex-row sm:items-center">
      <div>
        <p className="text-xs font-semibold text-brand-700">Next step</p>
        <p className="mt-1 text-[15px] font-semibold text-slate-900">{title}</p>
        <p className="mt-0.5 text-sm text-slate-500">{description}</p>
      </div>
      {disabled ? (
        <span className="text-sm text-slate-400">Finish this step first</span>
      ) : (
        <Link
          to={to}
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white shadow-sm transition hover:bg-brand-700"
        >
          {label}
          <ArrowRight className="size-4" />
        </Link>
      )}
    </div>
  );
}

/** Explains a step in three short points: shown beside forms so no page feels bare. */
export function HowItWorks({
  title = 'How this step works',
  points,
  footer,
}: {
  title?: string;
  points: { title: string; body: string }[];
  footer?: ReactNode;
}) {
  return (
    <aside className="h-fit self-start rounded-2xl bg-slate-900 p-6 text-white shadow-lift">
      <p className="text-sm font-semibold">{title}</p>
      <ol className="mt-5 space-y-5">
        {points.map((p, i) => (
          <li key={p.title} className="flex gap-3">
            <span className="grid size-6 shrink-0 place-items-center rounded-full bg-white/10 text-xs font-semibold text-brand-300 ring-1 ring-white/15">
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-medium text-white">{p.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-slate-400">
                {p.body}
              </p>
            </div>
          </li>
        ))}
      </ol>
      {footer && (
        <div className="mt-6 border-t border-white/10 pt-4 text-xs leading-relaxed text-slate-400">
          {footer}
        </div>
      )}
    </aside>
  );
}

/** Small "Step N · Title" pill for stage page headers. */
export function StagePill({ stage }: { stage: StageKey }) {
  const { stages } = useWorkflow();
  const s = stages.find((x) => x.key === stage);
  if (!s) return null;
  return (
    <span className="inline-flex items-center gap-2 rounded-full bg-white py-1 pr-3 pl-1 text-xs font-medium text-slate-600 shadow-card ring-1 ring-slate-200">
      <span className="grid size-5 place-items-center rounded-full bg-brand-600 text-[11px] font-semibold text-white">
        {s.step}
      </span>
      Step {s.step} of 5 · {s.title}
    </span>
  );
}
