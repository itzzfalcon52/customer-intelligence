import { useRef, useState } from 'react';
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
  useTransform,
} from 'motion/react';
import { Check, Scissors } from 'lucide-react';
import { cn } from '../../workspace/style';
import { Grommet, TAG_SHAPE } from './Tag';
import { ACCOUNTS } from './tags';

/**
 * The hero object: one large triage tag hanging from its wire in real 3D. It tilts toward the
 * pointer, sways on its own while idle (the attract loop), and its perforated stub can be torn
 * off, which tells the page to unfold Nemotron's brief.
 */
/** The red bar has been torn partway along its right end, as a used triage tag is. */
const TORN_BAR =
  'polygon(0 0, 100% 0, 100% 38%, 97% 46%, 99% 55%, 95.5% 64%, 98% 74%, 94% 86%, 96% 100%, 0 100%)';

/** The rank, rubber-stamped onto the stock: slightly rotated, uneven ink. */
function RankStamp({ rank }: { rank: number }) {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute right-4 bottom-2 sm:right-8 sm:bottom-3 z-10 grid size-[72px] sm:size-[92px] rotate-[-9deg] place-items-center rounded-full border-[3px] border-tag-red/80 bg-stock/0 text-tag-red/85 mix-blend-multiply"
      style={{
        maskImage:
          'radial-gradient(circle at 30% 40%, #000 55%, rgb(0 0 0 / 0.75) 100%)',
      }}
    >
      <span className="text-center leading-none">
        <span className="block font-stamp text-[10px] font-semibold tracking-[0.12em]">
          RANK
        </span>
        <span
          className="block font-display text-[28px] font-[880] sm:text-[38px]"
          style={{ fontStretch: '70%' }}
        >
          #{rank}
        </span>
      </span>
    </span>
  );
}

export function HangingTag({
  torn,
  onTear,
}: {
  torn: boolean;
  onTear: () => void;
}) {
  const account = ACCOUNTS[0];
  const reduce = useReducedMotion();
  const box = useRef<HTMLDivElement>(null);
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const rotateY = useSpring(useTransform(px, [-1, 1], [-16, 16]), {
    stiffness: 120,
    damping: 18,
  });
  const rotateX = useSpring(useTransform(py, [-1, 1], [10, -10]), {
    stiffness: 120,
    damping: 18,
  });
  const sheen = useTransform(
    px,
    [-1, 1],
    [
      'linear-gradient(105deg, rgb(255 255 255 / 0) 30%, rgb(255 255 255 / 0.35) 45%, rgb(255 255 255 / 0) 60%)',
      'linear-gradient(105deg, rgb(255 255 255 / 0) 50%, rgb(255 255 255 / 0.35) 65%, rgb(255 255 255 / 0) 80%)',
    ],
  );
  const [tearing, setTearing] = useState(false);

  function move(event: React.PointerEvent) {
    if (reduce || !box.current) return;
    const rect = box.current.getBoundingClientRect();
    px.set(((event.clientX - rect.left) / rect.width) * 2 - 1);
    py.set(((event.clientY - rect.top) / rect.height) * 2 - 1);
  }
  function leave() {
    animate(px, 0, { duration: 0.9, ease: [0.16, 1, 0.3, 1] });
    animate(py, 0, { duration: 0.9, ease: [0.16, 1, 0.3, 1] });
  }
  function tear() {
    if (torn || tearing) return;
    setTearing(true);
    window.setTimeout(onTear, reduce ? 0 : 380);
  }

  return (
    <div
      ref={box}
      onPointerMove={move}
      onPointerLeave={leave}
      className="relative mx-auto flex w-full max-w-[680px] flex-col items-center [perspective:1600px]"
    >
      {/* The wire: from the top edge of the viewport down through the grommet. */}
      <svg
        aria-hidden="true"
        viewBox="0 0 120 120"
        className="pointer-events-none -mb-3 h-16 w-28 sm:h-20"
        preserveAspectRatio="none"
      >
        <path
          d="M60 0 C 58 40, 46 70, 52 104 C 56 120, 70 118, 66 100"
          fill="none"
          stroke="#c9cfcb"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
      </svg>
      <motion.div
        style={{
          rotateX,
          rotateY,
          transformStyle: 'preserve-3d',
          transformOrigin: '50% 0%',
        }}
        animate={reduce ? undefined : { rotateZ: [-1.6, 1.4, -1.6] }}
        transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut' }}
        className="relative w-full"
      >
        {/* Card thickness: a darker sheet a few pixels behind the face. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-stock-300"
          style={{
            clipPath: TAG_SHAPE,
            transform: 'translateZ(-7px) translateY(3px)',
          }}
        />
        <article
          className="relative bg-stock pt-16 text-tag-ink shadow-tag-lift"
          style={{ clipPath: TAG_SHAPE }}
          aria-label="Example triage tag for a synthetic account"
        >
          <Grommet className="absolute top-5 left-1/2 size-6 -translate-x-1/2" />
          <div
            className="flex items-end justify-between bg-tag-red px-5 py-3 text-stock sm:px-8 sm:py-4"
            style={{ clipPath: TORN_BAR }}
          >
            <span
              className="font-display text-[22px] leading-none font-[820] sm:text-[30px] tracking-[0.02em] uppercase"
              style={{ fontStretch: '72%' }}
            >
              Call first
            </span>
            <span className="font-stamp text-[11px] font-semibold sm:text-[14px]">
              of 610 accounts
            </span>
          </div>
          <div className="ruled relative px-5 pt-5 pb-5 sm:px-8 sm:pt-6 sm:pb-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2
                  className="font-display text-[24px] leading-[1.02] sm:text-[36px] font-[780] text-balance"
                  style={{ fontStretch: '86%' }}
                >
                  {account.name}
                </h2>
                <p className="mt-1.5 font-stamp text-[11px] text-tag-slate sm:text-[13px]">
                  {account.id} · {account.plan} · {account.mrr}/mo
                </p>
              </div>
              <div className="text-right">
                <p className="font-stamp text-[30px] leading-none sm:text-[42px] font-bold text-tag-red tabular-nums">
                  .688
                </p>
                <p className="mt-1.5 text-[12px] font-medium tracking-wide text-tag-slate uppercase">
                  risk score
                </p>
              </div>
            </div>
            <table className="mt-5 w-full text-[14px] sm:mt-6 sm:text-[16px]">
              <caption className="sr-only">
                What stands out for this account
              </caption>
              <thead>
                <tr className="text-left text-[12px] tracking-[0.08em] text-tag-slate uppercase">
                  <th className="pb-1.5 font-semibold">Stands out</th>
                  <th className="pb-1.5 text-right font-semibold">
                    This account
                  </th>
                  <th className="pb-1.5 text-right font-semibold">Typical</th>
                </tr>
              </thead>
              <tbody>
                {account.stands.map(([label, value, typical]) => (
                  <tr key={label} className="border-t border-tag-ink/10">
                    <td className="py-1.5">{label}</td>
                    <td className="py-1.5 text-right font-stamp font-semibold tabular-nums">
                      {value}
                    </td>
                    <td className="py-1.5 text-right font-stamp text-tag-slate tabular-nums">
                      {typical}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-5 rounded-md bg-field-900 px-4 py-3 text-[14px] sm:px-5 sm:py-4 sm:text-[16px] leading-snug text-field-50">
              <p className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold tracking-[0.08em] text-field-200 uppercase">
                <span className="grid size-3.5 place-items-center rounded-full bg-tag-amber text-tag-ink">
                  <Check className="size-2.5" strokeWidth={3.5} />
                </span>
                Nemotron · 3 numbers checked
              </p>
              {account.note}{' '}
              <span className="text-field-300">Playbook: {account.play}.</span>
            </div>
          </div>
          <RankStamp rank={account.rank} />
          {/* The tear-off stub. */}
          <motion.button
            type="button"
            onClick={tear}
            disabled={torn}
            aria-label="Tear off the stub to read today's Nemotron brief"
            animate={
              tearing
                ? { y: 140, rotate: 14, opacity: 0 }
                : { y: 0, rotate: 0, opacity: 1 }
            }
            transition={{ duration: reduce ? 0 : 0.6, ease: [0.4, 0, 0.2, 1] }}
            whileHover={tearing ? undefined : { y: 3, rotate: -0.6 }}
            className={cn(
              'group relative block w-full cursor-pointer text-left focus-visible:outline-offset-[-6px]',
              torn && 'pointer-events-none',
            )}
          >
            <span className="perf block h-3" aria-hidden="true" />
            <span className="flex items-center justify-between bg-stock-200 px-5 py-3.5 sm:px-8 sm:py-4">
              <span className="flex items-center gap-2 font-display text-[17px] font-[700]">
                <Scissors className="size-4 text-tag-red transition-transform group-hover:-rotate-12" />
                Tear here for today’s brief
              </span>
            </span>
          </motion.button>
        </article>
        <motion.div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 mix-blend-soft-light"
          style={{ background: sheen, clipPath: TAG_SHAPE }}
        />
      </motion.div>
      <p className="mt-4 text-center text-[11px] text-field-300">
        Synthetic demo account. Every company on this site is invented.
      </p>
    </div>
  );
}
