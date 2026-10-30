/** Class helpers shared by the kit and pages (kept apart for fast refresh). */
export const cn = (...parts: (string | false | null | undefined)[]) =>
  parts.filter(Boolean).join(' ');

export type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'dark';
export type Size = 'sm' | 'md' | 'lg';
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-field-700 text-stock pl-5 [clip-path:polygon(8px_0,100%_0,100%_100%,8px_100%,0_50%)] hover:bg-field-800 active:bg-field-900 disabled:bg-field-700/50',
  secondary:
    'bg-white text-tag-ink ring-1 ring-inset ring-tag-ink/20 hover:ring-tag-ink/45 disabled:text-slate-400',
  ghost:
    'text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400',
  danger: 'bg-tag-red text-stock hover:bg-rose-600 disabled:bg-tag-red/50',
  dark: 'bg-tag-ink text-stock hover:bg-field-900 disabled:bg-tag-ink/50',
};
const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-[13px]',
  md: 'h-9 gap-2 rounded-lg px-3.5 text-sm',
  lg: 'h-11 gap-2 rounded-xl px-5 text-[15px]',
};
export function buttonClass(
  variant: Variant = 'secondary',
  size: Size = 'md',
  extra?: string,
) {
  return cn(
    'inline-flex shrink-0 cursor-pointer items-center justify-center font-[640] whitespace-nowrap transition-colors duration-150 disabled:cursor-not-allowed',
    VARIANTS[variant],
    SIZES[size],
    extra,
  );
}

export type RiskLevel = 'high' | 'elevated' | 'low';
/** Relative rank within the batch: top 10% high, next 20% elevated. Not a probability. */
export function riskLevel(rank: number, total: number): RiskLevel {
  const share = rank / Math.max(1, total);
  return share <= 0.1 ? 'high' : share <= 0.3 ? 'elevated' : 'low';
}
