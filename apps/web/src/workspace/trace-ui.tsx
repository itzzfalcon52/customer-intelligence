import { useState } from 'react';
import {
  Check,
  ChevronDown,
  CircleAlert,
  Cpu,
  Loader2,
  Wrench,
} from 'lucide-react';
import type { StreamEvent } from './api';
import { useResource } from './queries';
import type { TraceDetail } from './types';
import { cn } from './style';

function label(name: string) {
  if (name === 'assistant') return 'Reviewing the evidence';
  if (name === 'assistant:synthesis') return 'Writing the answer';
  if (name.startsWith('structured:'))
    return `Generating ${name
      .split(':')[1]
      .replace(/([a-z])([A-Z])/g, '$1 $2')
      .toLowerCase()}`;
  return name.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
}
const seconds = (ms: unknown) =>
  typeof ms === 'number' ? `${(ms / 1000).toFixed(1)}s` : '';

interface Step {
  kind: 'model' | 'tool';
  name: string;
  done: boolean;
  failed: boolean;
  duration?: unknown;
}
function steps(events: StreamEvent[]) {
  const rows: Step[] = [];
  for (const event of events) {
    const kind = event.type.startsWith('tool') ? 'tool' : 'model';
    const name = String(event.name ?? '');
    if (event.type.endsWith('_start'))
      rows.push({ kind, name, done: false, failed: false });
    else {
      const open = [...rows]
        .reverse()
        .find((r) => !r.done && r.kind === kind && r.name === name);
      if (open) {
        open.done = true;
        open.failed = event.status === 'failed';
        open.duration = event.duration_ms;
      }
    }
  }
  return rows;
}

/** Live progress of the current turn, built from streamed model/tool events. */
export function LiveSteps({ events }: { events: StreamEvent[] }) {
  const rows = steps(events);
  return (
    <ol
      className="space-y-2 rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70"
      aria-live="polite"
    >
      {!rows.length && (
        <li className="flex items-center gap-2 text-[13px] text-slate-500">
          <Loader2 className="size-3.5 animate-spin" /> Starting…
        </li>
      )}
      {rows.map((row, i) => {
        const Kind = row.kind === 'tool' ? Wrench : Cpu;
        return (
          <li
            key={i}
            className="flex items-center gap-2 text-[13px] text-slate-700"
          >
            {!row.done ? (
              <Loader2 className="size-3.5 animate-spin text-brand-600" />
            ) : row.failed ? (
              <CircleAlert className="size-3.5 text-amber-500" />
            ) : (
              <Check className="size-3.5 text-emerald-600" />
            )}
            <Kind className="size-3.5 text-slate-400" />
            <span className="flex-1">{label(row.name)}</span>
            <span className="font-mono text-[11px] text-slate-400">
              {seconds(row.duration)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/** Saved trace of a turn: every model and tool call with latency and token usage. */
export function TracePanel({ traceId }: { traceId: string }) {
  const [open, setOpen] = useState(false);
  const detail = useResource<TraceDetail>(
    `/api/v1/assistant/traces/${traceId}`,
    open,
  );
  const trace = detail.data?.trace;
  const tokens =
    trace && trace.input_tokens != null
      ? `${trace.input_tokens + (trace.output_tokens ?? 0)} tokens`
      : null;
  return (
    <div className="rounded-lg ring-1 ring-slate-200">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-slate-500 hover:text-slate-800"
      >
        <span>
          Agent trace
          {trace &&
            ` · ${trace.model_calls} model calls · ${trace.tool_calls} tools · ${seconds(trace.duration_ms)}${tokens ? ` · ${tokens}` : ''}${trace.cost_usd != null ? ` · $${trace.cost_usd.toFixed(4)}` : ''}`}
        </span>
        <ChevronDown
          className={cn('size-3.5 transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="border-t border-slate-100 p-3">
          {detail.isLoading && (
            <p className="text-xs text-slate-500">Loading trace…</p>
          )}
          {detail.error && (
            <p className="text-xs text-rose-600">Trace unavailable.</p>
          )}
          {detail.data && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-slate-500">
                  <tr>
                    {[
                      '#',
                      'Step',
                      'Model',
                      'Time',
                      'Tokens in/out',
                      'Status',
                    ].map((h) => (
                      <th key={h} className="px-2 py-1.5 text-left font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="text-slate-700">
                  {detail.data.spans.map((span) => (
                    <tr key={span.id} className="border-t border-slate-100">
                      <td className="px-2 py-1.5 font-mono text-slate-400">
                        {span.sequence}
                      </td>
                      <td className="px-2 py-1.5">
                        {span.parent && (
                          <span className="text-slate-400">↳ </span>
                        )}
                        {label(span.name)}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {span.model ?? '—'}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {seconds(span.duration_ms)}
                      </td>
                      <td className="px-2 py-1.5 font-mono">
                        {span.input_tokens != null
                          ? `${span.input_tokens}/${span.output_tokens ?? 0}`
                          : '—'}
                      </td>
                      <td className="px-2 py-1.5">
                        {span.status}
                        {span.attempts > 1 && ` (${span.attempts} attempts)`}
                        {span.error_code && ` · ${span.error_code}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {trace?.prompt_version && (
                <p className="mt-2 text-[11px] text-slate-400">
                  Prompt {trace.prompt_version}
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
