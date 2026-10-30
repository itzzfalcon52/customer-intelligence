import type { ReactNode } from 'react';
import { cn } from '../../workspace/style';
import { LEVEL, type DemoAccount } from './tags';

/** The grommet the wire passes through: a punched hole with a metal ring. */
export function Grommet({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'block rounded-full bg-field-950 ring-[3px] ring-[#c9cfcb] shadow-[inset_0_1px_2px_rgba(0,0,0,0.6)]',
        className,
      )}
    />
  );
}

/** The cut-corner tag outline every tag in the world shares. */
export const TAG_SHAPE =
  'polygon(14% 0, 86% 0, 100% 9%, 100% 100%, 0 100%, 0 9%)';

/** A small triage tag as it appears on the board and the moving strip. */
export function MiniTag({
  account,
  className,
  children,
}: {
  account: DemoAccount;
  className?: string;
  children?: ReactNode;
}) {
  const level = LEVEL[account.level];
  return (
    <article
      className={cn(
        'relative w-[214px] shrink-0 bg-stock pt-7 text-tag-ink shadow-tag',
        className,
      )}
      style={{ clipPath: TAG_SHAPE }}
      aria-label={`${account.name}, rank ${account.rank}, ${level.label}`}
    >
      <Grommet className="absolute top-2.5 left-1/2 size-3 -translate-x-1/2" />
      <div
        className={cn(
          'flex items-center justify-between px-3 py-1.5',
          level.bar,
        )}
      >
        <span
          className={cn(
            'font-display text-[11px] font-[760] tracking-[0.06em] uppercase',
            account.level === 'watch' ? 'text-tag-ink' : 'text-stock',
          )}
          style={{ fontStretch: '80%' }}
        >
          {level.label}
        </span>
        <span
          className={cn(
            'font-stamp text-[11px] font-semibold',
            account.level === 'watch' ? 'text-tag-ink' : 'text-stock',
          )}
        >
          #{account.rank}
        </span>
      </div>
      <div className="ruled px-3 pt-2.5 pb-3">
        <p
          className="font-display text-[15px] leading-tight font-[720]"
          style={{ fontStretch: '88%' }}
        >
          {account.name}
        </p>
        <p className="mt-0.5 font-stamp text-[10px] text-tag-slate">
          {account.id} · risk {account.risk.toFixed(3)}
        </p>
        <p className="mt-2 text-[12px] leading-snug text-[#3b4441]">
          {account.note}
        </p>
        {children}
      </div>
    </article>
  );
}
