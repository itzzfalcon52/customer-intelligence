import { useEffect, useRef, useState } from 'react';
import { motion, useInView, useReducedMotion } from 'motion/react';
import { EyeOff } from 'lucide-react';
import { Grommet, TAG_SHAPE } from './Tag';

/**
 * Items the verifier withheld, as tags on a wire. While on screen, each tag loops: the logged
 * line is struck through in red, then the reason appears beneath it (attract loop).
 */
export function WithheldTags({ items }: { items: [string, string][] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.3 });
  const reduce = useReducedMotion();
  // One step per tag, then two held steps before the loop starts over. Starts complete, so the
  // finished state shows before the loop runs and wherever motion is reduced.
  const cycle = items.length * 2 + 2;
  const [phase, setPhase] = useState(cycle - 1);
  useEffect(() => {
    if (!inView || reduce) return;
    const timer = window.setInterval(
      () => setPhase((p) => (p + 1) % cycle),
      900,
    );
    return () => window.clearInterval(timer);
  }, [inView, reduce, cycle]);
  return (
    <div ref={ref} className="relative">
      <svg
        aria-hidden="true"
        viewBox="0 0 1000 40"
        preserveAspectRatio="none"
        className="absolute inset-x-0 top-0 hidden h-10 w-full sm:block"
      >
        <path
          d="M0 4 Q 500 50 1000 4"
          fill="none"
          stroke="#c9cfcb"
          strokeWidth="2"
        />
      </svg>
      <ul className="grid gap-5 pt-4 sm:grid-cols-2">
        {items.map(([log, meaning], i) => {
          const redacted = reduce || phase > i * 2;
          return (
            <li
              key={log}
              className="relative bg-stock px-5 pt-10 pb-5 text-tag-ink shadow-tag"
              style={{
                clipPath: TAG_SHAPE,
                transform: `rotate(${[-1.5, 1.2, 1, -1.2][i % 4]}deg)`,
              }}
            >
              <Grommet className="absolute top-3 left-1/2 size-3.5 -translate-x-1/2" />
              <p className="relative font-stamp text-[13px] break-words">
                {log}
                <motion.span
                  aria-hidden="true"
                  initial={false}
                  animate={{ scaleX: redacted ? 1 : 0 }}
                  transition={{
                    duration: reduce ? 0 : 0.45,
                    ease: [0.65, 0, 0.35, 1],
                  }}
                  className="absolute top-1/2 -right-1 -left-1 h-[2px] origin-left bg-tag-red"
                />
              </p>
              <motion.p
                initial={false}
                animate={{ opacity: redacted ? 1 : 0.15 }}
                className="mt-3 flex gap-2 text-[15px] leading-snug text-tag-red"
              >
                <EyeOff className="mt-0.5 size-4 shrink-0" />
                <span>
                  <span className="sr-only">Withheld: </span>
                  {meaning}
                </span>
              </motion.p>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
