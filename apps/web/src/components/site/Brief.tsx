import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { Check, EyeOff, Sparkles } from 'lucide-react';
import { cn } from '../../workspace/style';

/**
 * Nemotron's daily brief, written line by line and checked line by line. The withheld line shows
 * what the verifier does to a sentence the evidence does not support. Content mirrors a real
 * brief from the synthetic workspace; the accounts are invented.
 */
const LINES: { text: string; checked: string; withheld?: string }[] = [
  {
    text: 'Three accounts moved into “call first” overnight; Brightwater Logistics leads at a risk score of .688.',
    checked: '2 numbers matched',
  },
  {
    text: 'Usage change percent changed a lot since the model was trained, so this week’s ranking leans on activity.',
    checked: 'names a measured change',
  },
  {
    text: 'Calling them will cut churn by 42%.',
    checked: '',
    withheld:
      'Withheld: 42% is not in the evidence, and it claims an effect only a holdout can measure.',
  },
  {
    text: 'Recommended play: a usage check-in with the champion this week, from your “Usage drop” playbook.',
    checked: 'cites playbook passage P2',
  },
];

export function Brief({
  open,
  className,
}: {
  open: boolean;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!open || reduce) return;
    const timers = LINES.map((_, i) =>
      window.setTimeout(() => setShown(i + 1), 450 + i * 900),
    );
    return () => timers.forEach(window.clearTimeout);
  }, [open, reduce]);
  const visible = reduce ? LINES.length : shown;

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.section
          key="brief"
          initial={{ clipPath: 'inset(0 0 100% 0)', opacity: 0.4 }}
          animate={{ clipPath: 'inset(0 0 0% 0)', opacity: 1 }}
          exit={{ clipPath: 'inset(0 0 100% 0)', opacity: 0 }}
          transition={{ duration: reduce ? 0 : 0.9, ease: [0.16, 1, 0.3, 1] }}
          aria-live="polite"
          className={cn(
            'relative bg-stock text-tag-ink shadow-tag-lift',
            className,
          )}
        >
          <header className="flex flex-wrap items-center justify-between gap-3 bg-tag-ink px-6 py-4 text-stock sm:px-10">
            <p
              className="font-display text-[22px] font-[780]"
              style={{ fontStretch: '78%' }}
            >
              Today’s brief, written by Nemotron, checked by code
            </p>
            <span className="inline-flex items-center gap-2 font-stamp text-[11px] text-field-200">
              <Sparkles className="size-3.5 text-tag-amber" />
              NVIDIA Nemotron on Nebius · synthetic workspace
            </span>
          </header>
          <ol className="ruled divide-y divide-tag-ink/10 px-6 py-2 sm:px-10">
            {LINES.map((line, i) => (
              <li
                key={i}
                className="grid gap-2 py-4 sm:grid-cols-[1fr_15rem] sm:gap-8"
              >
                <AnimatePresence>
                  {visible > i && (
                    <motion.p
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.4 }}
                      className={cn(
                        'text-[16px] leading-relaxed',
                        line.withheld && 'relative',
                      )}
                    >
                      {line.withheld ? (
                        <span className="relative">
                          <span className="text-tag-slate line-through decoration-tag-red decoration-2">
                            {line.text}
                          </span>
                          <motion.span
                            aria-hidden="true"
                            initial={{ scaleX: 0 }}
                            animate={{ scaleX: 1 }}
                            transition={{
                              delay: 0.5,
                              duration: 0.5,
                              ease: [0.65, 0, 0.35, 1],
                            }}
                            className="absolute inset-y-0 -inset-x-1 origin-left bg-tag-ink"
                          />
                        </span>
                      ) : (
                        line.text
                      )}
                    </motion.p>
                  )}
                </AnimatePresence>
                {visible > i && (
                  <motion.p
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.35 }}
                    className={cn(
                      'flex items-start gap-2 font-stamp text-[11px] leading-relaxed',
                      line.withheld ? 'text-tag-red' : 'text-field-700',
                    )}
                  >
                    {line.withheld ? (
                      <EyeOff className="mt-0.5 size-3.5 shrink-0" />
                    ) : (
                      <Check
                        className="mt-0.5 size-3.5 shrink-0"
                        strokeWidth={3}
                      />
                    )}
                    {line.withheld ?? line.checked}
                  </motion.p>
                )}
              </li>
            ))}
          </ol>
          <span className="perf block h-3" aria-hidden="true" />
        </motion.section>
      )}
    </AnimatePresence>
  );
}
