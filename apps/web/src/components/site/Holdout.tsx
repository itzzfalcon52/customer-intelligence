import { useRef } from 'react';
import { motion, useInView, useReducedMotion } from 'motion/react';
import { cn } from '../../workspace/style';

/**
 * How Holdfast proves outreach worked: the contact list is split at random; one group is
 * contacted, one is held back, and the churn difference is reported with its 95% range.
 * The figures are an illustration in the shape the product reports, not a measured result.
 */
const CONTACTED = { size: 40, churned: 5 };
const HELD = { size: 10, churned: 4 };

function Group({
  label,
  size,
  churned,
  delay,
  inView,
}: {
  label: string;
  size: number;
  churned: number;
  delay: number;
  inView: boolean;
}) {
  const reduce = useReducedMotion();
  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <span
          className="font-display text-[18px] font-[760]"
          style={{ fontStretch: '80%' }}
        >
          {label}
        </span>
        <span className="font-stamp text-[12px] tabular-nums">
          {churned} of {size} churned
        </span>
      </div>
      <div className="grid grid-cols-10 gap-1.5">
        {Array.from({ length: size }, (_, i) => {
          const lost = i < churned;
          return (
            <motion.span
              key={i}
              aria-hidden="true"
              initial={reduce ? false : { opacity: 0, y: -8 }}
              animate={inView ? { opacity: 1, y: 0 } : undefined}
              transition={{ delay: delay + i * 0.025, duration: 0.3 }}
              className={cn(
                'block aspect-[3/4] [clip-path:polygon(18%_0,82%_0,100%_14%,100%_100%,0_100%,0_14%)]',
                lost ? 'bg-tag-red' : 'bg-stock',
              )}
            />
          );
        })}
      </div>
    </div>
  );
}

export function Holdout({ className }: { className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduce = useReducedMotion();
  // Contacted 12.5% vs held back 40%: −27.5 points, with an illustrative 95% range.
  const low = -52;
  const high = -4;
  const point = -27.5;
  const scale = (v: number) => ((v + 60) / 70) * 100;
  return (
    <div ref={ref} className={cn('text-stock', className)}>
      <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        <Group label="Contacted" inView={inView} delay={0} {...CONTACTED} />
        <Group
          label="Held back at random"
          inView={inView}
          delay={0.6}
          {...HELD}
        />
      </div>
      <div className="mt-10">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[14px] text-field-200">
            Churn change when contacted, with its 95% range
          </span>
          <span className="font-stamp text-[22px] font-bold tabular-nums">
            −27.5 pts
          </span>
        </div>
        <div className="relative mt-4 h-10" aria-hidden="true">
          <div className="absolute inset-x-0 top-1/2 h-px bg-field-600" />
          <div
            className="absolute top-0 bottom-0 w-px bg-field-300"
            style={{ left: `${scale(0)}%` }}
          />
          <span
            className="absolute -bottom-5 -translate-x-1/2 font-stamp text-[10px] text-field-300"
            style={{ left: `${scale(0)}%` }}
          >
            no effect
          </span>
          <motion.div
            className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full bg-tag-amber"
            style={{
              left: `${scale(low)}%`,
              width: `${scale(high) - scale(low)}%`,
            }}
            initial={reduce ? false : { scaleX: 0 }}
            animate={inView ? { scaleX: 1 } : undefined}
            transition={{ delay: 1.2, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          />
          <motion.div
            className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-stock"
            style={{ left: `${scale(point)}%` }}
            initial={reduce ? false : { opacity: 0 }}
            animate={inView ? { opacity: 1 } : undefined}
            transition={{ delay: 1.8 }}
          />
        </div>
        <p className="mt-8 max-w-[60ch] text-[13px] leading-relaxed text-field-200">
          Illustration in the format Holdfast reports. The range sits entirely
          below zero, so fewer contacted accounts churned. When the range
          crosses zero, Holdfast says “no clear difference yet”, never a saving
          it didn’t measure.
        </p>
      </div>
    </div>
  );
}
