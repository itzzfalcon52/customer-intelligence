import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, useInView, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, Clock3 } from 'lucide-react';
import { Grommet, MiniTag, TAG_SHAPE } from '../components/site/Tag';
import { AnimatedNumber } from '../workspace/ui';
import { StampStrip } from '../components/site/Strips';
import { ACCOUNTS } from '../components/site/tags';
import { TAG_BUTTON } from '../components/SiteLayout';
import { cn } from '../workspace/style';

const MOVES = [
  {
    id: 'detect',
    verb: 'Detect',
    title: 'Rank every account by how likely it is to leave.',
    body: 'Bring a CSV of past customers or a bundle of accounts, invoices, usage and tickets. Holdfast builds point-in-time snapshots, so a model only ever learns from what was known on each date, and compares a baseline, logistic regression, random forest and XGBoost on your newest data.',
    facts: [
      'Leaky columns flagged before training',
      'Tested on the newest months, not a random shuffle',
      'Quality shown as “times better than random”',
      'Up to 1 million rows per upload',
    ],
  },
  {
    id: 'explain',
    verb: 'Explain',
    title: 'Say why, for each account, in a sentence.',
    body: 'For the top of the list, Holdfast works out which inputs make each account stand out compared with a typical customer. Nemotron turns that into one plain note and points at the matching passage in your own playbook. Code checks every number before you see it.',
    facts: [
      'Per-account reasons, computed then written',
      'Citations from your playbooks',
      'Ask AI anything; answers are checked the same way',
      'Investigations test hypotheses against your data',
    ],
  },
  {
    id: 'act',
    verb: 'Act',
    title: 'Turn the list into plays your team runs.',
    body: 'Pick a play (or take the one Nemotron recommends in the morning brief), choose how many accounts, and send it for approval. Nothing reaches a customer; the approved list goes to your team as a CSV or as HubSpot tasks for each account owner.',
    facts: [
      'Approvals inbox for every proposed action',
      'Budget planner with your own assumptions',
      'Outreach drafts for review, never sent',
      'Daily limits and a kill switch for AI',
    ],
  },
  {
    id: 'measure',
    verb: 'Measure',
    title: 'Find out what actually worked.',
    body: 'Hold back a random group when you score. Once outcomes are known, Holdfast compares contacted and held-back accounts with a 95% range. It also watches whether your customers have changed since training and how the predictions held up.',
    facts: [
      'Holdout groups and measured lift',
      'Drift checks after every scheduled run',
      'Accuracy measured on real outcomes',
      'Retraining proposed, never forced',
    ],
  },
];

const SPEC: [string, [string, string][]][] = [
  [
    'Data',
    [
      ['Uploads', 'CSV up to 200 MB or Excel up to 50 MB, up to 1M rows'],
      [
        'Account sources',
        'Accounts, invoices, usage and tickets as a CSV bundle',
      ],
      ['Synthetic demo', 'A labelled 900-account SaaS company, one click'],
      ['Privacy policy', 'Columns you mark never reach the AI'],
    ],
  ],
  [
    'Models',
    [
      ['Families', 'Baseline, logistic regression, random forest, XGBoost'],
      ['Evaluation', 'Time-ordered splits; final test kept in reserve'],
      ['Active model', 'Promote and roll back in one click'],
      ['Monitoring', 'Drift, score shift and measured accuracy'],
    ],
  ],
  [
    'AI',
    [
      ['Model', 'NVIDIA Nemotron on Nebius'],
      ['Sees', 'Aggregates, computed drivers, labels like A1'],
      ['Checked', 'Numbers, causal wording, field names, relevance'],
      ['Controls', 'Consent, autonomy levels, token budget, kill switch'],
    ],
  ],
  [
    'Team',
    [
      ['Workspaces', 'Personal and team, fully separate'],
      ['Roles', 'Owner, admin, member, viewer, enforced by the server'],
      ['Audit log', 'Every change and every automated action'],
      ['Retention', 'Old data deleted on a schedule you set'],
    ],
  ],
];

export function FeaturesPage() {
  const reduce = useReducedMotion();
  return (
    <>
      <section className="bg-field-800 px-5 pt-[136px] pb-20 sm:px-8">
        <div className="mx-auto max-w-[1320px]">
          <h1
            className="max-w-[16ch] text-[clamp(3.2rem,7.4vw,6rem)] leading-[0.86] font-[860] tracking-[-0.03em]"
            style={{ fontStretch: '66%' }}
          >
            One board. Four moves.
          </h1>
          <p className="mt-7 max-w-[40rem] text-[19px] leading-relaxed text-field-100">
            Detect who is slipping, explain why, act on it with your team, and
            measure what changed. Everything below works in the product today,
            apart from what’s marked as coming soon.
          </p>
          <nav
            aria-label="The four moves"
            className="mt-12 flex flex-wrap gap-3"
          >
            {MOVES.map((m, i) => (
              <a
                key={m.id}
                href={`#${m.id}`}
                className="group inline-flex items-center gap-3 bg-stock py-2.5 pr-5 pl-4 text-tag-ink transition hover:-translate-y-0.5"
                style={{
                  clipPath: 'polygon(10px 0,100% 0,100% 100%,10px 100%,0 50%)',
                }}
              >
                <span className="font-stamp text-[12px] text-tag-slate">
                  {i + 1}
                </span>
                <span
                  className="text-[17px] font-[740]"
                  style={{ fontStretch: '80%' }}
                >
                  {m.verb}
                </span>
              </a>
            ))}
          </nav>
        </div>
      </section>

      {MOVES.map((move, i) => (
        <section
          key={move.id}
          id={move.id}
          className={cn(
            'scroll-mt-20 px-5 py-24 sm:px-8',
            i % 2 ? 'bg-stock text-tag-ink' : 'bg-field-900 text-stock',
          )}
        >
          <div
            className={cn(
              'mx-auto grid max-w-[1320px] items-center gap-14 lg:grid-cols-2',
              i % 2 === 1 && 'lg:[&>*:first-child]:order-2',
            )}
          >
            <div>
              <h2
                className="max-w-[18ch] text-[clamp(2.6rem,5vw,4.6rem)] leading-[0.92] font-[840] tracking-[-0.02em]"
                style={{ fontStretch: '66%' }}
              >
                {move.title}
              </h2>
              <p
                className={cn(
                  'mt-5 max-w-[36rem] text-[17px] leading-relaxed',
                  i % 2 ? 'text-[#3b4441]' : 'text-field-100',
                )}
              >
                {move.body}
              </p>
              <ul className="mt-8 grid gap-3 sm:grid-cols-2">
                {move.facts.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-[15px]">
                    <Check
                      className={cn(
                        'mt-0.5 size-4 shrink-0',
                        i % 2 ? 'text-field-700' : 'text-tag-amber',
                      )}
                      strokeWidth={3}
                    />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
            >
              <Specimen move={move.id} />
            </motion.div>
          </div>
        </section>
      ))}

      <StampStrip
        reverse
        className="bg-stock text-tag-ink"
        words={['Detect', 'Explain', 'Act', 'Measure']}
      />

      <section className="bg-field-800 px-5 py-24 sm:px-8">
        <div className="mx-auto max-w-[1320px]">
          <h2
            className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            The spec sheet.
          </h2>
          <div className="mt-12 grid gap-px bg-stock/15 md:grid-cols-2">
            {SPEC.map(([group, rows]) => (
              <div key={group} className="bg-field-800 p-6 sm:p-8">
                <h3
                  className="text-[22px] font-[780]"
                  style={{ fontStretch: '76%' }}
                >
                  {group}
                </h3>
                <dl className="mt-5 divide-y divide-stock/10">
                  {rows.map(([term, detail]) => (
                    <div
                      key={term}
                      className="grid grid-cols-[9rem_1fr] gap-4 py-3 text-[15px]"
                    >
                      <dt className="text-field-300">{term}</dt>
                      <dd>{detail}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
          <div className="mt-12 flex flex-wrap items-center gap-6">
            <Link
              to="/signup"
              className={cn(
                TAG_BUTTON,
                'h-12 bg-stock text-tag-ink hover:bg-white',
              )}
            >
              Start free <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/pricing#coming-soon"
              className="inline-flex items-center gap-2 text-[15px] text-field-100 hover:text-stock"
            >
              <Clock3 className="size-4" /> What’s coming soon
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}

/** A working fragment of the product for each move, cut as a tag, running its own loop. */
function SpecimenTag({
  bar,
  barText,
  label,
  children,
}: {
  bar: string;
  barText: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="relative mx-auto max-w-[560px] rotate-[1.5deg] bg-stock pt-12 text-tag-ink shadow-tag-lift"
      style={{ clipPath: TAG_SHAPE }}
    >
      <Grommet className="absolute top-4 left-1/2 size-5 -translate-x-1/2" />
      <div className={cn('flex items-center justify-between px-6 py-2.5', bar)}>
        <span
          className={cn('text-[17px] font-[820] uppercase', barText)}
          style={{ fontStretch: '72%' }}
        >
          {label}
        </span>
      </div>
      <div className="ruled px-6 pt-5 pb-6">{children}</div>
    </div>
  );
}

/** Re-runs a loop every `ms` while on screen; returns a key that changes each cycle. */
function useLoop(ms: number) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.4 });
  const reduce = useReducedMotion();
  const [cycle, setCycle] = useState(0);
  useEffect(() => {
    if (!inView || reduce) return;
    const timer = window.setInterval(() => setCycle((c) => c + 1), ms);
    return () => window.clearInterval(timer);
  }, [inView, reduce, ms]);
  return { ref, cycle, reduce };
}

function Specimen({ move }: { move: string }) {
  if (move === 'detect') return <DetectSpecimen />;
  if (move === 'explain')
    return (
      <div className="flex flex-wrap justify-center gap-5">
        {ACCOUNTS.slice(1, 3).map((a, i) => (
          <div key={a.id} style={{ transform: `rotate(${i ? 3 : -3}deg)` }}>
            <MiniTag account={a}>
              <p className="mt-2 font-stamp text-[10px] text-field-700">
                Playbook › {a.play}
              </p>
            </MiniTag>
          </div>
        ))}
      </div>
    );
  if (move === 'act') return <ActSpecimen />;
  return <MeasureSpecimen />;
}

const COMPARISON: [string, number, number][] = [
  ['XGBoost', 0.172, 2.2],
  ['Random forest', 0.168, 2.2],
  ['Logistic regression', 0.117, 1.5],
  ['Baseline (chance)', 0.078, 1.0],
];

function DetectSpecimen() {
  const { ref, cycle, reduce } = useLoop(7000);
  return (
    <div ref={ref}>
      <SpecimenTag
        bar="bg-field-700"
        barText="text-stock"
        label="Models compared"
      >
        <ul className="space-y-4" key={cycle}>
          {COMPARISON.map(([name, ap, lift], i) => (
            <li key={name}>
              <div className="flex items-baseline justify-between text-[15px]">
                <span className={cn(i === 0 && 'font-[740]')}>
                  {name}
                  {i === 0 && (
                    <span className="ml-2 font-stamp text-[11px] text-field-700">
                      selected
                    </span>
                  )}
                </span>
                <span className="font-stamp text-[13px] tabular-nums">
                  {lift.toFixed(1)}× chance
                </span>
              </div>
              <div className="mt-1.5 h-3 bg-stock-200">
                <motion.div
                  className={cn(
                    'h-full',
                    i === 0 ? 'bg-tag-red' : 'bg-field-500',
                  )}
                  initial={reduce ? false : { width: 0 }}
                  animate={{ width: `${(ap / 0.2) * 100}%` }}
                  transition={{
                    duration: 1.1,
                    delay: i * 0.12,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
        <p className="mt-5 text-[12px] text-tag-slate">
          Average precision from the synthetic demo run of October 29, 2026
          (newest snapshots). Real datasets vary.
        </p>
      </SpecimenTag>
    </div>
  );
}

function ActSpecimen() {
  const { ref, cycle, reduce } = useLoop(4200);
  const approved = reduce || cycle % 2 === 1;
  return (
    <div ref={ref}>
      <SpecimenTag
        bar="bg-tag-amber"
        barText="text-tag-ink"
        label="Waiting for approval"
      >
        <p className="text-[20px] font-[760]" style={{ fontStretch: '80%' }}>
          Run a retention play
        </p>
        <p className="mt-1 text-[15px] text-[#3b4441]">
          Usage check-in: 25 accounts from the contact list, as a CSV export.
          Holdout accounts are excluded.
        </p>
        <div className="relative mt-5 flex gap-2">
          <span className="bg-stock-200 px-3 py-1.5 text-[14px] font-[600]">
            Reject
          </span>
          <span className="bg-field-700 px-3 py-1.5 text-[14px] font-[600] text-stock">
            Approve
          </span>
          <motion.span
            aria-hidden="true"
            initial={false}
            animate={
              approved
                ? { opacity: 1, scale: 1, rotate: -8 }
                : { opacity: 0, scale: 1.6, rotate: -14 }
            }
            transition={{ type: 'spring', stiffness: 380, damping: 18 }}
            className="absolute -top-5 right-2 border-[3px] border-field-700 px-3 py-1 font-display text-[22px] font-[860] text-field-700 uppercase mix-blend-multiply"
            style={{ fontStretch: '70%' }}
          >
            Approved
          </motion.span>
        </div>
        <p className="mt-5 text-[12px] text-tag-slate">
          Only owners and admins can approve.
        </p>
      </SpecimenTag>
    </div>
  );
}

function MeasureSpecimen() {
  const { ref, cycle } = useLoop(6000);
  return (
    <div ref={ref}>
      <SpecimenTag
        bar="bg-tag-red"
        barText="text-stock"
        label="Did outreach work?"
      >
        <div key={cycle} className="grid grid-cols-3 gap-px bg-tag-ink/10">
          {[
            ['Contacted, churned', 12.5, '%'],
            ['Held back, churned', 40, '%'],
            ['Change', -27.5, ' pts'],
          ].map(([l, v, unit]) => (
            <div key={l as string} className="bg-stock p-3">
              <p className="text-[12px] text-tag-slate">{l as string}</p>
              <p className="mt-1 font-stamp text-[22px] font-bold tabular-nums">
                <AnimatedNumber
                  value={v as number}
                  format={(n) => `${n.toFixed(1)}${unit as string}`}
                />
              </p>
            </div>
          ))}
        </div>
        <p className="mt-5 text-[12px] text-tag-slate">
          Illustration in the format Holdfast reports.
        </p>
      </SpecimenTag>
    </div>
  );
}
