import { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, Lock, Scissors } from 'lucide-react';
import { HangingTag } from '../components/site/HangingTag';
import { Brief } from '../components/site/Brief';
import { StampStrip, TagStrip } from '../components/site/Strips';
import { Board } from '../components/site/Board';
import { Holdout } from '../components/site/Holdout';
import { Grommet, TAG_SHAPE } from '../components/site/Tag';
import { TAG_BUTTON } from '../components/SiteLayout';
import { cn } from '../workspace/style';

const H2 =
  'text-[clamp(2.4rem,5vw,4.6rem)] leading-[0.92] font-[820] tracking-[-0.02em] text-balance';

export function HomePage() {
  const [torn, setTorn] = useState(false);
  return (
    <>
      <Hero torn={torn} onTear={() => setTorn(true)} />
      <section aria-label="Today's brief" className="bg-field-800 px-5 sm:px-8">
        <div className="mx-auto max-w-[1100px]">
          <Brief open={torn} className="mb-24" />
          {!torn && (
            <div className="flex justify-center pb-20">
              <button
                type="button"
                onClick={() => setTorn(true)}
                className="inline-flex cursor-pointer items-center gap-2 border-b-2 border-dashed border-field-300 pb-1 text-[15px] font-[600] text-field-100 transition hover:border-stock hover:text-stock"
              >
                <Scissors className="size-4" /> Or open today’s brief without
                tearing
              </button>
            </div>
          )}
        </div>
      </section>
      <StampStrip
        className="bg-tag-amber text-tag-ink"
        words={[
          'Measured, not guessed',
          'Explained, then checked',
          'Proven against a holdout',
          'Nothing sent without approval',
        ]}
      />
      <MorningBoard />
      <WritesAndChecks />
      <Proof />
      <Chain />
      <Close />
    </>
  );
}

function Hero({ torn, onTear }: { torn: boolean; onTear: () => void }) {
  const reduce = useReducedMotion();
  const rise = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 18 },
          animate: { opacity: 1, y: 0 },
          transition: {
            delay,
            duration: 0.8,
            ease: [0.16, 1, 0.3, 1] as const,
          },
        };
  return (
    <section className="relative overflow-hidden bg-field-800 pt-[72px]">
      <div className="mx-auto grid max-w-[1320px] grid-cols-[minmax(0,1fr)] items-start gap-8 px-5 pt-10 sm:px-8 lg:grid-cols-12 lg:pt-4">
        <div className="min-w-0 lg:col-span-5 lg:pt-20">
          <motion.h1
            {...rise(0.05)}
            className="text-[clamp(3.2rem,6.4vw,5.6rem)] leading-[0.88] font-[860] tracking-[-0.03em] text-balance"
            style={{ fontStretch: '68%' }}
          >
            Know who’s slipping <span className="text-tag-amber">before</span>{' '}
            they let go.
          </motion.h1>
          <motion.p
            {...rise(0.18)}
            className="mt-7 max-w-[34rem] text-[19px] leading-relaxed text-field-100"
          >
            Holdfast ranks every customer account by churn risk, has NVIDIA
            Nemotron explain each one in plain words, and proves what your
            outreach actually changed. Every number is checked against your data
            before you see it.
          </motion.p>
          <motion.div
            {...rise(0.3)}
            className="mt-9 flex flex-wrap items-center gap-x-6 gap-y-4"
          >
            <Link
              to="/signup"
              className={cn(
                TAG_BUTTON,
                'h-12 bg-stock text-[16px] text-tag-ink hover:bg-white',
              )}
            >
              Start free <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/nemotron"
              className="group inline-flex items-center gap-2 text-[16px] font-[620] text-stock"
            >
              <span className="border-b-2 border-tag-red pb-0.5">
                How Nemotron is used
              </span>
              <ArrowRight className="size-4 transition group-hover:translate-x-1" />
            </Link>
          </motion.div>
          <motion.ul
            {...rise(0.42)}
            className="mt-10 grid max-w-[34rem] gap-2.5 text-[14px] text-field-200 sm:grid-cols-2"
          >
            {[
              'Free while in preview',
              'Synthetic demo in one click',
              'CSV or Excel, up to 1M rows',
              'Real IDs never reach the AI',
            ].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <Check className="size-4 text-tag-amber" strokeWidth={3} /> {t}
              </li>
            ))}
          </motion.ul>
        </div>
        <motion.div
          className="min-w-0 lg:col-span-7"
          initial={reduce ? false : { y: -120, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{
            type: 'spring',
            stiffness: 60,
            damping: 12,
            delay: 0.2,
          }}
        >
          <HangingTag torn={torn} onTear={onTear} />
        </motion.div>
      </div>
      <TagStrip className="-mt-4" />
    </section>
  );
}

function MorningBoard() {
  return (
    <section className="bg-field-900 px-5 py-28 sm:px-8">
      <div className="mx-auto grid max-w-[1320px] gap-14 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.6fr)]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <h2 className={H2} style={{ fontStretch: '66%' }}>
            Every account, triaged before your first coffee.
          </h2>
          <p className="mt-6 max-w-[30rem] text-[17px] leading-relaxed text-field-100">
            Each morning Holdfast re-scores your accounts with the model you
            made active and hangs them where they belong: call first, watch, or
            lower. Each tag carries the score, what stands out and the play your
            own playbook suggests.
          </p>
          <dl className="mt-10 grid max-w-[30rem] grid-cols-2 gap-x-8 gap-y-6 border-t border-stock/15 pt-8">
            {[
              ['Ranks by', 'a model compared fairly against a baseline'],
              ['Checks', 'whether your customers changed since training'],
              ['Tells you', 'which of last month’s calls actually worked'],
              ['Never', 'emails a customer on its own'],
            ].map(([term, detail]) => (
              <div key={term}>
                <dt className="font-stamp text-[11px] tracking-wide text-tag-amber uppercase">
                  {term}
                </dt>
                <dd className="mt-1.5 text-[15px] leading-snug text-field-100">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <Board />
      </div>
    </section>
  );
}

function WritesAndChecks() {
  return (
    <section className="bg-stock px-5 py-28 text-tag-ink sm:px-8">
      <div className="mx-auto max-w-[1320px]">
        <div className="grid gap-10 lg:grid-cols-2 lg:items-end">
          <h2 className={H2} style={{ fontStretch: '66%' }}>
            Nemotron writes. Code checks every sentence.
          </h2>
          <p className="max-w-[34rem] text-[17px] leading-relaxed text-[#3b4441]">
            The models do the measuring. Nemotron reads only those measured
            results and turns them into a brief a person can act on. Then plain
            code reads every sentence back against the evidence and withholds
            anything it can’t support.
          </p>
        </div>
        <div className="mt-16 grid gap-6 lg:grid-cols-[1.15fr_1fr]">
          <div className="relative bg-field-800 p-6 text-stock sm:p-10">
            <h3
              className="text-[26px] font-[780]"
              style={{ fontStretch: '74%' }}
            >
              What Nemotron sees, and what stays with you
            </h3>
            <div className="mt-8 grid gap-4 sm:grid-cols-2">
              <div className="bg-field-950/60 p-5">
                <p className="font-stamp text-[11px] tracking-wide text-tag-amber uppercase">
                  Sent to the model
                </p>
                <p className="mt-3 font-stamp text-[13px] leading-relaxed">
                  A1 · risk 0.688
                  <br />
                  logins 4 (typical 124)
                  <br />
                  days since active 9 (typical 3)
                </p>
              </div>
              <div className="bg-stock p-5 text-tag-ink">
                <p className="flex items-center gap-1.5 font-stamp text-[11px] tracking-wide text-tag-red uppercase">
                  <Lock className="size-3" /> Stays on your server
                </p>
                <p className="mt-3 font-stamp text-[13px] leading-relaxed">
                  A1 = Brightwater Logistics
                  <br />
                  ACME-0757 · raw rows
                  <br />
                  contact names, emails
                </p>
              </div>
            </div>
            <p className="mt-6 text-[14px] text-field-200">
              Accounts travel as labels like A1. The server maps them back after
              the answer passes its checks.
            </p>
          </div>
          <ol className="divide-y divide-tag-ink/12 border-y border-tag-ink/12">
            {[
              [
                'Every number must exist in the evidence.',
                'An invented “42%” is withheld, not shown.',
              ],
              [
                'No cause-and-effect claims.',
                '“Stands out” and “linked to” pass. “Drives churn” does not.',
              ],
              [
                'Changes must name what changed.',
                'A “what changed” line has to point at an input that really moved.',
              ],
              [
                'No internal field names.',
                'If it reads like a database column, it is withheld.',
              ],
            ].map(([rule, example]) => (
              <li key={rule} className="grid grid-cols-[2.5rem_1fr] gap-3 py-6">
                <Check className="mt-1 size-6 text-field-700" strokeWidth={3} />
                <div>
                  <p
                    className="text-[20px] leading-snug font-[720]"
                    style={{ fontStretch: '82%' }}
                  >
                    {rule}
                  </p>
                  <p className="mt-1.5 text-[15px] text-[#3b4441]">{example}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
        <Link
          to="/nemotron"
          className="group mt-12 inline-flex items-center gap-2 text-[17px] font-[680]"
        >
          <span className="border-b-2 border-tag-red pb-0.5">
            See every place Nemotron is used
          </span>
          <ArrowRight className="size-4 transition group-hover:translate-x-1" />
        </Link>
      </div>
    </section>
  );
}

function Proof() {
  return (
    <section className="bg-field-950 px-5 py-28 sm:px-8">
      <div className="mx-auto grid max-w-[1320px] gap-14 lg:grid-cols-[0.9fr_1.4fr]">
        <div>
          <h2 className={H2} style={{ fontStretch: '66%' }}>
            Then prove the calls worked.
          </h2>
          <p className="mt-6 max-w-[30rem] text-[17px] leading-relaxed text-field-100">
            Tick “hold back 20%” when you score. Holdfast sets a random group
            aside, you call the rest, and once outcomes are known it compares
            the two, with an honest range around the difference. That is the
            only basis it will ever use for “it worked”.
          </p>
        </div>
        <Holdout />
      </div>
    </section>
  );
}

const STEPS = [
  [
    'Bring history',
    'A CSV of past customers, or a bundle of accounts, invoices, usage and tickets.',
  ],
  [
    'Define churn',
    'Pick the outcome and the inputs known in advance. Leaky columns get flagged.',
  ],
  [
    'Compare models',
    'A baseline, logistic regression, random forest and XGBoost, tested on your newest data.',
  ],
  [
    'Score today',
    'Every current account ranked, with what stands out and a checked note.',
  ],
  ['Act and measure', 'Approve a play, keep a holdout, and read the result.'],
];

/** The workflow as tags strung along one wire, each hanging at its own height. */
function Chain() {
  const reduce = useReducedMotion();
  return (
    <section className="relative overflow-hidden bg-field-800 px-5 py-28 sm:px-8">
      <div className="mx-auto max-w-[1320px]">
        <h2 className={cn(H2, 'max-w-[18ch]')} style={{ fontStretch: '66%' }}>
          From a spreadsheet to Monday’s calls.
        </h2>
        <div className="relative mt-16">
          <svg
            aria-hidden="true"
            viewBox="0 0 1000 80"
            preserveAspectRatio="none"
            className="absolute inset-x-0 top-0 hidden h-20 w-full lg:block"
          >
            <path
              d="M0 6 Q 500 90 1000 6"
              fill="none"
              stroke="#c9cfcb"
              strokeWidth="2"
            />
          </svg>
          <ol className="grid gap-6 lg:grid-cols-5 lg:gap-4">
            {STEPS.map(([title, text], i) => (
              <motion.li
                key={title}
                initial={reduce ? false : { y: -40, opacity: 0, rotate: -6 }}
                whileInView={{
                  y: 0,
                  opacity: 1,
                  rotate: [2, -1.5, 1, -1][i % 4],
                }}
                viewport={{ once: true, amount: 0.4 }}
                transition={{
                  type: 'spring',
                  stiffness: 120,
                  damping: 12,
                  delay: i * 0.12,
                }}
                className="origin-top lg:[margin-top:var(--drop)]"
                style={
                  {
                    '--drop': `${[24, 52, 64, 52, 24][i]}px`,
                  } as React.CSSProperties
                }
              >
                <div
                  className="relative bg-stock px-5 pt-10 pb-6 text-tag-ink shadow-tag"
                  style={{ clipPath: TAG_SHAPE }}
                >
                  <Grommet className="absolute top-3 left-1/2 size-3.5 -translate-x-1/2" />
                  <p className="-mx-5 flex items-center justify-between bg-field-700 px-5 py-1.5 text-stock">
                    <span className="sr-only">Step {i + 1} of 5</span>
                    <span
                      aria-hidden="true"
                      className="font-stamp text-[12px] font-semibold"
                    >
                      #{i + 1}
                    </span>
                  </p>
                  <p
                    className="mt-2 text-[22px] leading-tight font-[780]"
                    style={{ fontStretch: '78%' }}
                  >
                    {title}
                  </p>
                  <p className="mt-2 text-[14px] leading-snug text-[#3b4441]">
                    {text}
                  </p>
                </div>
              </motion.li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function Close() {
  return (
    <section className="bg-field-800 px-5 pb-28 sm:px-8">
      <div className="mx-auto max-w-[1100px]">
        <div
          className="relative bg-tag-red px-6 pt-16 pb-10 text-stock shadow-tag-lift sm:px-14"
          style={{
            clipPath:
              'polygon(6% 0, 94% 0, 100% 12%, 100% 100%, 0 100%, 0 12%)',
          }}
        >
          <Grommet className="absolute top-5 left-1/2 size-6 -translate-x-1/2" />
          <h2
            className="text-[clamp(2.6rem,6vw,5.4rem)] leading-[0.9] font-[860] tracking-[-0.02em] text-balance"
            style={{ fontStretch: '64%' }}
          >
            See your own accounts triaged by tomorrow morning.
          </h2>
          <div className="mt-10 flex flex-wrap items-center gap-6">
            <Link
              to="/signup"
              className={cn(
                TAG_BUTTON,
                'h-12 bg-stock text-[16px] text-tag-ink hover:bg-white',
              )}
            >
              Start free <ArrowRight className="size-4" />
            </Link>
            <p className="text-[15px] text-stock/90">
              No card. Try it first on a labelled synthetic SaaS company.
            </p>
          </div>
          <span
            className="perf mt-10 block h-3 opacity-60"
            aria-hidden="true"
          />
        </div>
      </div>
    </section>
  );
}
