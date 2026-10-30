import {
  useEffect,
  useId,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useTransform,
} from 'motion/react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Info,
  Loader2,
  X,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import {
  buttonClass,
  cn,
  type RiskLevel,
  type Size,
  type Variant,
} from './style';

/* ------------------------------------------------------------------ Buttons */

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  icon: Icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <button
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        Icon && <Icon className="size-4" strokeWidth={2} />
      )}
      {children}
    </button>
  );
}
export function ButtonLink({
  variant = 'secondary',
  size = 'md',
  icon: Icon,
  trailing: Trailing,
  className,
  children,
  ...rest
}: LinkProps & {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  trailing?: LucideIcon;
}) {
  return (
    <Link className={buttonClass(variant, size, className)} {...rest}>
      {Icon && <Icon className="size-4" strokeWidth={2} />}
      {children}
      {Trailing && <Trailing className="size-4" strokeWidth={2} />}
    </Link>
  );
}

/* ------------------------------------------------------------------ Surfaces */

export function Card({
  title,
  description,
  action,
  icon: Icon,
  children,
  className,
  bodyClassName,
  footer,
}: {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: LucideIcon;
  children?: ReactNode;
  className?: string;
  bodyClassName?: string;
  footer?: ReactNode;
}) {
  return (
    <section
      className={cn(
        'flex min-w-0 flex-col rounded-2xl bg-white shadow-card ring-1 ring-slate-200/80',
        className,
      )}
    >
      {(title || action) && (
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
          <div className="flex min-w-0 items-start gap-3">
            {Icon && (
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg bg-slate-50 text-slate-500 ring-1 ring-slate-200/70">
                <Icon className="size-4" strokeWidth={1.9} />
              </span>
            )}
            <div className="min-w-0">
              {title && (
                <h2
                  className="text-[17px] leading-tight font-[760] text-tag-ink"
                  style={{ fontStretch: '82%' }}
                >
                  {title}
                </h2>
              )}
              {description && (
                <p className="mt-0.5 text-[13px] leading-relaxed text-slate-500">
                  {description}
                </p>
              )}
            </div>
          </div>
          {action && <div className="flex shrink-0 gap-2">{action}</div>}
        </header>
      )}
      <div className={cn('flex-1 p-5', bodyClassName)}>{children}</div>
      {footer && (
        <footer className="rounded-b-2xl border-t border-slate-100 bg-slate-50/60 px-5 py-3">
          {footer}
        </footer>
      )}
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  back,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  back?: { to: string; label: string };
}) {
  return (
    <div className="mb-6">
      {back && (
        <Link
          to={back.to}
          className="mb-3 inline-flex items-center gap-1 text-[13px] font-medium text-slate-500 transition hover:text-slate-900"
        >
          <ChevronLeft className="size-4" />
          {back.label}
        </Link>
      )}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 max-w-3xl">
          {eyebrow && <div className="mb-2">{eyebrow}</div>}
          <h1
            className="text-[32px] leading-[0.95] font-[840] tracking-[-0.015em] text-balance text-tag-ink [word-spacing:0.08em] sm:text-[42px]"
            style={{ fontStretch: '68%' }}
          >
            {title}
          </h1>
          {description && (
            <p className="mt-2 text-[15px] leading-relaxed text-pretty text-slate-500">
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        )}
      </div>
    </div>
  );
}

const TONES = {
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
  brand: 'bg-brand-50 text-brand-700 ring-brand-200',
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
  info: 'bg-field-50 text-field-700 ring-field-200',
  violet: 'bg-tag-ink text-stock ring-tag-ink',
} as const;
const DOTS = {
  neutral: 'bg-slate-400',
  brand: 'bg-brand-500',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
  info: 'bg-field-500',
  violet: 'bg-tag-amber',
} as const;
export type Tone = keyof typeof TONES;
export function Badge({
  tone = 'neutral',
  dot,
  children,
  className,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex h-6 items-center gap-1.5 rounded-[3px] px-2 font-sans text-xs font-[620] whitespace-nowrap ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {dot && <span className={cn('size-1.5 rotate-45', DOTS[tone])} />}
      {children}
    </span>
  );
}
const JOB_TONE: Record<string, Tone> = {
  succeeded: 'success',
  running: 'info',
  queued: 'warning',
  failed: 'danger',
  cancelled: 'neutral',
};
export function StateBadge({ state }: { state: string }) {
  return (
    <Badge tone={JOB_TONE[state] ?? 'neutral'} dot>
      {state[0].toUpperCase() + state.slice(1)}
    </Badge>
  );
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  return (
    <Badge
      dot
      tone={
        level === 'high'
          ? 'danger'
          : level === 'elevated'
            ? 'warning'
            : 'neutral'
      }
    >
      {level === 'high' ? 'High' : level === 'elevated' ? 'Elevated' : 'Lower'}
    </Badge>
  );
}
export function ScoreBar({ value }: { value: number }) {
  const tone =
    value >= 0.7
      ? 'bg-rose-500'
      : value >= 0.4
        ? 'bg-amber-500'
        : 'bg-slate-400';
  return (
    <div className="flex items-center justify-end gap-2.5">
      <div className="h-2 w-20 overflow-hidden bg-slate-100">
        <motion.div
          className={cn('h-full', tone)}
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(2, value * 100)}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>
      <span className="w-11 text-right font-mono text-[13px] tabular">
        {value.toFixed(3)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ Numbers */

export function AnimatedNumber({
  value,
  format = (n) => Math.round(n).toLocaleString(),
}: {
  value: number;
  format?: (n: number) => string;
}) {
  const count = useMotionValue(0);
  const text = useTransform(count, format);
  useEffect(() => {
    const controls = animate(count, value, { duration: 0.9, ease: 'easeOut' });
    return () => controls.stop();
  }, [count, value]);
  return <motion.span>{text}</motion.span>;
}

export function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'neutral',
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: 'neutral' | 'brand' | 'danger' | 'warning' | 'info' | 'violet';
  children?: ReactNode;
}) {
  const iconTone = {
    neutral: 'bg-slate-100 text-slate-600',
    brand: 'bg-brand-50 text-brand-600',
    danger: 'bg-rose-50 text-rose-600',
    warning: 'bg-amber-50 text-amber-600',
    info: 'bg-field-50 text-field-600',
    violet: 'bg-tag-ink text-tag-amber',
  }[tone];
  return (
    <div className="relative flex flex-col overflow-hidden rounded-2xl bg-white p-5 shadow-card ring-1 ring-slate-200/80">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[12px] font-[680] tracking-[0.06em] text-slate-500 uppercase">
          {label}
        </span>
        {Icon && (
          <span
            className={cn(
              'grid size-8 place-items-center rounded-lg',
              iconTone,
            )}
          >
            <Icon className="size-4" strokeWidth={2} />
          </span>
        )}
      </div>
      <div className="mt-2 font-mono text-[26px] leading-9 font-bold text-tag-ink tabular">
        {value}
      </div>
      {hint && <div className="mt-1 text-[13px] text-slate-500">{hint}</div>}
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ Feedback */

export function Alert({
  tone = 'info',
  title,
  children,
  action,
  className,
}: {
  tone?: 'info' | 'warning' | 'danger' | 'success';
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  const styles = {
    info: ['bg-sky-50/70 ring-sky-200/80 text-sky-900', Info, 'text-sky-500'],
    warning: [
      'bg-amber-50/80 ring-amber-200/80 text-amber-950',
      AlertTriangle,
      'text-amber-500',
    ],
    danger: [
      'bg-rose-50 ring-rose-200 text-rose-900',
      XCircle,
      'text-rose-500',
    ],
    success: [
      'bg-emerald-50 ring-emerald-200 text-emerald-900',
      CheckCircle2,
      'text-emerald-500',
    ],
  } as const;
  const [box, Icon, iconColor] = styles[tone];
  return (
    <div
      role={tone === 'danger' ? 'alert' : undefined}
      className={cn(
        'flex items-start gap-3 rounded-xl px-4 py-3 text-[13.5px] leading-relaxed ring-1 ring-inset',
        box,
        className,
      )}
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', iconColor)} />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        {children && (
          <div className={cn(Boolean(title) && 'mt-0.5 opacity-90')}>
            {children}
          </div>
        )}
      </div>
      {action}
    </div>
  );
}
/** Renders an error (string, Error or null) as a danger alert. */
export function Notice({ error }: { error?: unknown }) {
  if (!error) return null;
  const message =
    typeof error === 'string'
      ? error
      : error instanceof Error
        ? error.message
        : 'Something went wrong.';
  return <Alert tone="danger">{message}</Alert>;
}
/** Limitations and honesty notes, never styled as errors. */
export function Caveats({ items }: { items?: string[] | null }) {
  if (!items?.length) return null;
  return (
    <Alert tone="warning" title="Keep in mind">
      <ul className="ml-4 list-disc space-y-0.5">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </Alert>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <Loader2 className={cn('size-4 animate-spin text-slate-400', className)} />
  );
}
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="space-y-4" role="status" aria-label={label}>
      <div className="skeleton h-8 w-72" />
      <div className="skeleton h-4 w-96 max-w-full" />
      <div className="grid gap-4 pt-2 sm:grid-cols-3">
        <div className="skeleton h-28 rounded-2xl" />
        <div className="skeleton h-28 rounded-2xl" />
        <div className="skeleton h-28 rounded-2xl" />
      </div>
      <div className="skeleton h-64 rounded-2xl" />
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center text-center',
        compact ? 'py-8' : 'py-14',
      )}
    >
      <div className="relative mb-5">
        <div className="absolute inset-0 -m-3 rounded-full bg-brand-100/50 blur-xl" />
        <div className="relative grid size-14 place-items-center rounded-2xl bg-white shadow-lift ring-1 ring-slate-200">
          <Icon className="size-6 text-brand-600" strokeWidth={1.8} />
        </div>
      </div>
      <h3 className="text-base font-semibold text-slate-900">{title}</h3>
      {description && (
        <p className="mt-1.5 max-w-md text-sm leading-relaxed text-slate-500">
          {description}
        </p>
      )}
      {action && (
        <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Forms */

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      <span className="text-[13px] font-medium text-slate-700">{label}</span>
      {children}
      {hint && (
        <span className="text-xs leading-relaxed text-slate-500">{hint}</span>
      )}
    </label>
  );
}
const control =
  'w-full rounded-lg border-0 bg-white text-sm text-slate-900 shadow-card ring-1 ring-inset ring-slate-200 transition placeholder:text-slate-400 hover:ring-slate-300 focus:ring-2 focus:ring-brand-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500';
export function Input({
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(control, 'h-9 px-3', className)} {...rest} />;
}
export function Textarea({
  className,
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(control, 'min-h-24 px-3 py-2 leading-relaxed', className)}
      {...rest}
    />
  );
}
export function Select({
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={cn(
          control,
          'h-9 cursor-pointer appearance-none pr-9 pl-3',
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-slate-400" />
    </div>
  );
}
export function Checkbox({
  checked,
  onChange,
  disabled,
  children,
  description,
  className,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
  description?: ReactNode;
  className?: string;
}) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-3 text-sm text-slate-700',
        disabled && 'cursor-not-allowed opacity-60',
        className,
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5 size-4 shrink-0 cursor-pointer rounded border-slate-300 accent-brand-600"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="leading-relaxed">{children}</span>
        {description && (
          <span className="mt-0.5 block text-xs text-slate-500">
            {description}
          </span>
        )}
      </span>
    </label>
  );
}
/** A highlighted confirmation box for consent and irreversible steps. */
export function Confirm({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        'rounded-xl p-4 ring-1 transition-colors',
        checked
          ? 'bg-brand-50/70 ring-brand-200'
          : 'bg-slate-50 ring-slate-200',
      )}
    >
      <Checkbox checked={checked} onChange={onChange}>
        {children}
      </Checkbox>
    </div>
  );
}

/* ------------------------------------------------------------------ Tabs */

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: { value: T; label: ReactNode; icon?: LucideIcon; count?: number }[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const id = useId();
  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex max-w-full gap-1 overflow-x-auto border-b-2 border-slate-200',
        className,
      )}
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cn(
              'relative inline-flex h-10 cursor-pointer items-center gap-2 px-3 text-[14px] font-[640] whitespace-nowrap transition-colors',
              active ? 'text-tag-ink' : 'text-slate-500 hover:text-slate-800',
            )}
          >
            {active && (
              <motion.span
                layoutId={`tab-${id}`}
                className="absolute inset-x-1 -bottom-[2px] h-[3px] bg-tag-red"
                transition={{ type: 'spring', bounce: 0.15, duration: 0.4 }}
              />
            )}
            <span className="relative flex items-center gap-2">
              {tab.icon && <tab.icon className="size-4" />}
              {tab.label}
              {tab.count != null && (
                <span className="rounded-full bg-slate-200/80 px-1.5 text-[11px] text-slate-600">
                  {tab.count}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ Tables */

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="-mx-5 -mb-5 overflow-x-auto first:-mt-5">
      <table className="w-full border-collapse text-left text-[13.5px]">
        {children}
      </table>
    </div>
  );
}
export function Th({
  children,
  align = 'left',
  className,
}: {
  children?: ReactNode;
  align?: 'left' | 'right';
  className?: string;
}) {
  return (
    <th
      className={cn(
        'h-10 border-b border-slate-100 bg-slate-50/70 px-5 text-xs font-medium whitespace-nowrap text-slate-500',
        align === 'right' && 'text-right',
        className,
      )}
    >
      {children}
    </th>
  );
}
export function Td({
  children,
  align = 'left',
  className,
  mono,
}: {
  children?: ReactNode;
  align?: 'left' | 'right';
  className?: string;
  mono?: boolean;
}) {
  return (
    <td
      className={cn(
        'h-12 border-b border-slate-100 px-5 text-slate-700',
        align === 'right' && 'text-right',
        mono && 'font-mono text-[13px] tabular',
        className,
      )}
    >
      {children}
    </td>
  );
}
export function Tr({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <tr
      className={cn(
        'transition-colors last:[&>td]:border-b-0 hover:bg-slate-50/70',
        className,
      )}
    >
      {children}
    </tr>
  );
}
export function Pagination({
  page,
  setPage,
  count,
  size = 25,
}: {
  page: number;
  setPage: (page: number) => void;
  count: number;
  size?: number;
}) {
  if (page === 0 && count < size) return null;
  return (
    <div className="mt-4 flex items-center justify-between">
      <span className="text-[13px] text-slate-500">Page {page + 1}</span>
      <div className="flex gap-2">
        <Button
          size="sm"
          icon={ChevronLeft}
          disabled={page === 0}
          onClick={() => setPage(page - 1)}
        >
          Previous
        </Button>
        <Button
          size="sm"
          disabled={count < size}
          onClick={() => setPage(page + 1)}
        >
          Next
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Misc */

export function Progress({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'h-1.5 overflow-hidden rounded-full bg-slate-100',
        className,
      )}
    >
      <motion.div
        className="h-full rounded-full bg-brand-500"
        initial={{ width: 0 }}
        animate={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      />
    </div>
  );
}
export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="divide-y divide-slate-100">
      {items.map(([k, v], i) => (
        <div
          key={i}
          className="flex items-center justify-between gap-4 py-2.5 text-sm"
        >
          <dt className="text-slate-500">{k}</dt>
          <dd className="text-right font-medium text-slate-900">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
export function JsonDetails({
  data,
  label = 'Technical details',
}: {
  data: unknown;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  if (data == null) return null;
  return (
    <div className="rounded-xl ring-1 ring-slate-200">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left text-[13px] font-medium text-slate-600 hover:text-slate-900"
      >
        {label}
        <ChevronDown
          className={cn('size-4 transition-transform', open && 'rotate-180')}
        />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <pre className="max-h-96 overflow-auto border-t border-slate-100 bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-700">
              {JSON.stringify(data, null, 2)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-slate-200 bg-white px-1 font-sans text-[11px] font-medium text-slate-500 shadow-sm">
      {children}
    </kbd>
  );
}
export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 grid place-items-center p-4">
          <motion.button
            aria-label="Close"
            className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-pop ring-1 ring-slate-200"
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.18 }}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
              <button
                onClick={onClose}
                className="cursor-pointer rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close"
              >
                <X className="size-4" />
              </button>
            </div>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
/** Stagger children into view. */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}
