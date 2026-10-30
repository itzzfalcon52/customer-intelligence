import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, Lock, Sparkles } from 'lucide-react';
import { TAG_BUTTON } from '../components/SiteLayout';
import { StampStrip } from '../components/site/Strips';
import { Grommet, TAG_SHAPE } from '../components/site/Tag';
import { WithheldTags } from '../components/site/Withheld';
import { cn } from '../workspace/style';

const JOBS: [string, string, string][] = [
  [
    'Daily brief',
    'After each scheduled check',
    'Headline, what changed, accounts to call first and a recommended play cited from your playbooks.',
  ],
  [
    'Account notes',
    'At-risk accounts list',
    'One plain sentence per top account, built from its computed drivers.',
  ],
  [
    'Ask AI',
    'Anywhere, ⌘J',
    'Plans which tools to call (data, models, scores, playbooks, memory), then answers with evidence.',
  ],
  [
    'Investigations',
    '“Why do they churn?”',
    'Plans hypotheses, runs deterministic analyses, writes a report that a verifier checks.',
  ],
  [
    'Input review',
    'Before training',
    'Reads column names and statistics to flag inputs recorded after churn (leakage).',
  ],
  [
    'Briefings and drafts',
    'Retention plays',
    'Executive summaries, rule-versus-model checks and outreach drafts for review, never sent.',
  ],
];

const WITHHELD: [string, string][] = [
  [
    '“what changed: unsupported numbers: 0.275”',
    'An invented figure in a change summary.',
  ],
  ['“caveat: causal wording”', 'A sentence claiming one thing caused another.'],
  [
    '“headline: unsupported numbers: 20”',
    'A headline with a number from nowhere; a computed headline replaced it.',
  ],
  [
    '“what changed: not about a measured change”',
    'A plausible line about an input that never moved.',
  ],
];

const GUARDS: [string, string][] = [
  [
    'Explicit consent',
    'Every AI action asks first; automatic briefs need an admin to switch them on.',
  ],
  [
    'Pseudonymous labels',
    'Accounts travel as A1, A2…; real IDs and raw rows never leave your server.',
  ],
  ['Privacy policy', 'Columns you mark are never sent, even as statistics.'],
  [
    'Daily token budget',
    'Every AI call stops when the workspace’s budget for the day is used.',
  ],
  [
    'Kill switch',
    'One click pauses every AI call, scheduled check and proposal.',
  ],
  [
    'Approval for actions',
    'The AI can propose training or plays; only a person can approve them.',
  ],
];

export function NemotronPage() {
  const reduce = useReducedMotion();
  return (
    <>
      <section className="relative overflow-hidden bg-field-900 px-5 pt-[136px] pb-24 sm:px-8">
        <div className="mx-auto grid max-w-[1320px] gap-12 lg:grid-cols-[1.25fr_1fr] lg:items-end">
          <div>
            <h1
              className="text-[clamp(3.2rem,7.4vw,6rem)] leading-[0.86] font-[860] tracking-[-0.03em] text-balance"
              style={{ fontStretch: '66%' }}
            >
              The models measure.{' '}
              <span className="text-tag-amber">Nemotron</span> explains. Code
              checks.
            </h1>
            <p className="mt-7 max-w-[38rem] text-[19px] leading-relaxed text-field-100">
              Holdfast uses NVIDIA Nemotron, served on Nebius, as its analyst:
              it reads what the churn models and statistics computed and writes
              the part a person acts on. It never computes a number itself, and
              every sentence it writes is checked before you see it.
            </p>
          </div>
          <div
            className="relative rotate-[2deg] bg-stock pt-14 text-tag-ink shadow-tag-lift"
            style={{ clipPath: TAG_SHAPE }}
          >
            <Grommet className="absolute top-4 left-1/2 size-5 -translate-x-1/2" />
            <div className="flex items-center justify-between bg-tag-amber px-6 py-2.5">
              <span
                className="text-[17px] font-[820] uppercase"
                style={{ fontStretch: '72%' }}
              >
                Model in use
              </span>
              <span className="font-stamp text-[11px]">via Nebius</span>
            </div>
            <div className="ruled px-6 pt-5 pb-6">
              <p className="font-stamp text-[18px] font-bold break-all">
                nvidia/Nemotron-3_5-Lightning
              </p>
              <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-tag-ink/10 pt-5 text-[14px]">
                <div>
                  <dt className="text-tag-slate">Served by</dt>
                  <dd className="font-[700]">Nebius</dd>
                </div>
                <div>
                  <dt className="text-tag-slate">Jobs in the product</dt>
                  <dd className="font-[700]">{JOBS.length}</dd>
                </div>
                <div>
                  <dt className="text-tag-slate">Calls routed by</dt>
                  <dd className="font-[700]">one gateway</dd>
                </div>
                <div>
                  <dt className="text-tag-slate">Every call</dt>
                  <dd className="font-[700]">traced</dd>
                </div>
              </dl>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-field-800 px-5 py-24 sm:px-8">
        <div className="mx-auto max-w-[1320px]">
          <h2
            className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            Where it does the work.
          </h2>
          <ol className="mt-12 divide-y divide-stock/12 border-y border-stock/12">
            {JOBS.map(([job, where, what], i) => (
              <motion.li
                key={job}
                initial={reduce ? false : { opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.6 }}
                transition={{
                  duration: 0.6,
                  delay: i * 0.05,
                  ease: [0.16, 1, 0.3, 1],
                }}
                className="grid gap-2 py-6 md:grid-cols-[18rem_14rem_1fr] md:items-baseline md:gap-8"
              >
                <span
                  className="text-[26px] font-[780]"
                  style={{ fontStretch: '74%' }}
                >
                  {job}
                </span>
                <span className="font-stamp text-[12px] text-tag-amber">
                  {where}
                </span>
                <span className="text-[16px] leading-relaxed text-field-100">
                  {what}
                </span>
              </motion.li>
            ))}
          </ol>
        </div>
      </section>

      <section
        id="what-it-sees"
        className="scroll-mt-20 bg-stock px-5 py-24 text-tag-ink sm:px-8"
      >
        <div className="mx-auto max-w-[1320px]">
          <h2
            className="max-w-[18ch] text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            What it sees, and what never leaves.
          </h2>
          <div className="mt-12 grid gap-6 lg:grid-cols-[1fr_auto_1fr] lg:items-stretch">
            <div className="bg-field-800 p-6 text-stock sm:p-8">
              <p className="flex items-center gap-2 font-stamp text-[12px] text-tag-amber uppercase">
                <Sparkles className="size-3.5" /> Sent to Nemotron
              </p>
              <ul className="mt-5 space-y-3 text-[16px]">
                {[
                  'Model results: average precision, chance level',
                  'Which inputs changed since training, in words',
                  'Per-account drivers under labels A1…A15',
                  'Passages from your own playbooks',
                  'Your question and saved assumptions',
                ].map((t) => (
                  <li key={t} className="flex gap-2">
                    <Check
                      className="mt-1 size-4 shrink-0 text-tag-amber"
                      strokeWidth={3}
                    />{' '}
                    {t}
                  </li>
                ))}
              </ul>
            </div>
            <div className="hidden items-center lg:flex" aria-hidden="true">
              <span className="block h-full w-px border-l-2 border-dashed border-tag-ink/30" />
            </div>
            <div className="bg-field-900 p-6 text-stock ring-2 ring-tag-red sm:p-8">
              <p className="flex items-center gap-2 font-stamp text-[12px] text-tag-amber uppercase">
                <Lock className="size-3.5" /> Stays on your server
              </p>
              <ul className="mt-5 space-y-3 text-[16px]">
                {[
                  'Raw customer rows and uploaded files',
                  'Real account IDs and company names',
                  'Columns your privacy policy blocks',
                  'Contact details',
                  'The trained models themselves',
                ].map((t) => (
                  <li key={t} className="flex gap-2">
                    <Lock className="mt-1 size-4 shrink-0 text-tag-amber" /> {t}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <StampStrip
        className="bg-tag-amber text-tag-ink"
        words={[
          'No invented numbers',
          'No causal claims',
          'No field names',
          'No real IDs',
        ]}
      />

      <section
        id="checks"
        className="scroll-mt-20 bg-field-950 px-5 py-24 sm:px-8"
      >
        <div className="mx-auto grid max-w-[1320px] gap-14 lg:grid-cols-[0.9fr_1.3fr]">
          <div>
            <h2
              className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
              style={{ fontStretch: '66%' }}
            >
              Caught by the checks.
            </h2>
            <p className="mt-6 max-w-[32rem] text-[17px] leading-relaxed text-field-100">
              These are real items the verifier withheld during live runs on the
              synthetic workspace on October 30, 2026, as recorded in the
              workspace’s agent traces and the project’s backend notes. In the
              same runs, 15 of 15 account notes passed, and each brief had 13 to
              24 numbers checked against the evidence.
            </p>
          </div>
          <WithheldTags items={WITHHELD} />
        </div>
      </section>

      <section className="bg-field-800 px-5 py-24 sm:px-8">
        <div className="mx-auto max-w-[1320px]">
          <h2
            className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            The guardrails around it.
          </h2>
          <dl className="mt-12 grid border-t-2 border-stock/80 md:grid-cols-2 md:gap-x-12">
            {GUARDS.map(([term, detail]) => (
              <div
                key={term}
                className="grid grid-cols-[11rem_1fr] items-baseline gap-4 border-b border-stock/15 py-5"
              >
                <dt
                  className={cn(
                    'text-[20px] leading-tight font-[780]',
                    term === 'Kill switch' && 'text-tag-amber',
                  )}
                  style={{ fontStretch: '74%' }}
                >
                  {term}
                </dt>
                <dd className="text-[15px] leading-relaxed text-field-100">
                  {detail}
                </dd>
              </div>
            ))}
          </dl>
          <div className="mt-14 flex flex-wrap items-center gap-6">
            <Link
              to="/signup"
              className={cn(
                TAG_BUTTON,
                'h-12 bg-stock text-tag-ink hover:bg-white',
              )}
            >
              Try it on synthetic data <ArrowRight className="size-4" />
            </Link>
            <Link
              to="/product"
              className="inline-flex items-center gap-2 text-[15px] text-field-100 hover:text-stock"
            >
              See the whole product <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
