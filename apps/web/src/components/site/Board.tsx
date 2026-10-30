import { useEffect, useRef, useState } from 'react';
import {
  AnimatePresence,
  motion,
  useInView,
  useReducedMotion,
} from 'motion/react';
import { cn } from '../../workspace/style';
import { MiniTag } from './Tag';
import { ACCOUNTS, LEVEL, type Level } from './tags';

const COLUMNS: Level[] = ['call', 'watch', 'lower'];

/**
 * The morning board. While it is on screen, tags arrive one at a time and hang themselves on the
 * hook rail for their triage level: the product sorting a fresh scoring batch (attract loop).
 */
export function Board({ className }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  // A loop while on screen: tags drop in one by one, the full board holds, then it re-sorts.
  // Off screen (and with reduced motion) the board is always full, so it is never seen empty.
  const inView = useInView(ref, { amount: 0.35 });
  const reduce = useReducedMotion();
  const [count, setCount] = useState(ACCOUNTS.length);
  useEffect(() => {
    if (reduce) return;
    if (!inView) {
      const settle = window.setTimeout(() => setCount(ACCOUNTS.length), 0);
      return () => window.clearTimeout(settle);
    }
    const hold = 8;
    let step = 0;
    const timer = window.setInterval(() => {
      step = (step + 1) % (ACCOUNTS.length + hold);
      setCount(Math.min(step, ACCOUNTS.length));
    }, 650);
    return () => window.clearInterval(timer);
  }, [inView, reduce]);
  const hung = ACCOUNTS.slice(0, Math.min(count, ACCOUNTS.length));
  return (
    <div
      ref={ref}
      className={cn(
        'pegboard relative overflow-hidden rounded-[6px] bg-field-800 p-4 ring-1 ring-field-950/60 sm:p-6',
        className,
      )}
    >
      <div className="grid gap-6 md:grid-cols-3">
        {COLUMNS.map((level) => {
          const tags = hung.filter((a) => a.level === level);
          return (
            <div key={level} className="min-w-0">
              <div className="mb-3 flex items-center justify-between">
                <span
                  className="font-display text-[15px] font-[780] tracking-[0.04em] text-stock uppercase"
                  style={{ fontStretch: '72%' }}
                >
                  {LEVEL[level].label}
                </span>
                <span className="font-stamp text-[11px] text-field-200 tabular-nums">
                  {tags.length} on hook
                </span>
              </div>
              {/* The hook rail. */}
              <div className="h-1.5 rounded-full bg-gradient-to-b from-[#d6dbd7] to-[#8f9a96] shadow-[0_2px_3px_rgba(0,0,0,0.4)]" />
              <div className="relative flex min-h-[260px] flex-col items-center pt-1 md:min-h-[520px]">
                <AnimatePresence>
                  {tags.map((account, i) => (
                    <motion.div
                      key={account.id}
                      initial={
                        reduce ? false : { y: -180, rotate: -8, opacity: 0 }
                      }
                      animate={{ y: 0, rotate: i % 2 ? 2 : -2, opacity: 1 }}
                      exit={{
                        opacity: 0,
                        y: 30,
                        transition: { duration: 0.3 },
                      }}
                      transition={{
                        type: 'spring',
                        stiffness: 170,
                        damping: 14,
                      }}
                      className={cn('origin-top', i > 0 && '-mt-[68px]')}
                      style={{ zIndex: i }}
                    >
                      <MiniTag account={account} />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
