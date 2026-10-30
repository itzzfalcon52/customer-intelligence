import { cn } from '../workspace/style';

/** Holdfast: a triage tag on its wire loop, the red bar marking the account to hold on to. */
export function Logo({
  dark = false,
  compact = false,
}: {
  dark?: boolean;
  compact?: boolean;
}) {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden="true">
        <path
          d="M16 1.8c-3.4 0-4.6 3.2-2.4 5.6"
          fill="none"
          stroke={dark ? 'var(--color-wire)' : 'var(--color-tag-slate)'}
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <path
          d="M10.5 6.5h11l3 3.6V29a1.5 1.5 0 0 1-1.5 1.5H9A1.5 1.5 0 0 1 7.5 29V10.1z"
          fill={dark ? '#f5f7f4' : '#0c4a47'}
        />
        <circle cx="16" cy="10.4" r="1.9" fill={dark ? '#0c4a47' : '#f5f7f4'} />
        <rect x="7.5" y="15" width="17" height="5" fill="#d7262e" />
        <path
          d="M9.5 24.5h13"
          stroke={dark ? '#0c4a47' : '#f5f7f4'}
          strokeWidth="1.3"
          strokeDasharray="1.4 1.6"
        />
      </svg>
      {!compact && (
        <span
          className={cn(
            'font-display text-[19px] leading-none font-[780] tracking-[-0.02em]',
            dark ? 'text-stock' : 'text-tag-ink',
          )}
          style={{ fontStretch: '86%' }}
        >
          Holdfast
        </span>
      )}
    </span>
  );
}
