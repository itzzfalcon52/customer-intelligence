import { cn } from '../../workspace/style';
import { MiniTag } from './Tag';
import { ACCOUNTS } from './tags';

/** A moving strip of tags, the way new accounts slide onto the board every morning. */
export function TagStrip({ className }: { className?: string }) {
  const row = [...ACCOUNTS, ...ACCOUNTS];
  return (
    <div
      className={cn(
        'group relative overflow-hidden py-6 [mask-image:linear-gradient(90deg,transparent,#000_8%,#000_92%,transparent)]',
        className,
      )}
      aria-label="Example tags from the synthetic demo workspace"
    >
      <div className="flex w-max animate-strip gap-5 group-hover:[animation-play-state:paused]">
        {row.map((account, i) => (
          <div
            key={`${account.id}-${i}`}
            aria-hidden={i >= ACCOUNTS.length}
            style={{ transform: `rotate(${((i * 37) % 7) - 3}deg)` }}
          >
            <MiniTag account={account} />
          </div>
        ))}
      </div>
    </div>
  );
}

/** A stamped-text strip: what Holdfast promises, set like a hazard band. */
export function StampStrip({
  words,
  reverse = false,
  className,
}: {
  words: string[];
  reverse?: boolean;
  className?: string;
}) {
  const row = [...words, ...words, ...words, ...words];
  return (
    <div
      className={cn(
        'overflow-hidden border-y-2 border-tag-ink py-3',
        className,
      )}
      aria-label={words.join('. ')}
    >
      <div
        className={cn(
          'flex w-max items-center gap-8',
          reverse ? 'animate-strip-reverse' : 'animate-strip',
        )}
        aria-hidden="true"
      >
        {row.map((word, i) => (
          <span key={i} className="flex items-center gap-8">
            <span
              className="font-display text-[clamp(1.6rem,3.6vw,3rem)] leading-none font-[820] whitespace-nowrap uppercase"
              style={{ fontStretch: '64%' }}
            >
              {word}
            </span>
            <svg viewBox="0 0 20 20" className="size-5 shrink-0 text-tag-red">
              <rect
                x="3"
                y="3"
                width="14"
                height="14"
                fill="currentColor"
                transform="rotate(45 10 10)"
              />
            </svg>
          </span>
        ))}
      </div>
    </div>
  );
}
