import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { ArrowRight, Check, Clock3, Plus } from 'lucide-react';
import { Grommet, TAG_SHAPE } from '../components/site/Tag';
import { TAG_BUTTON } from '../components/SiteLayout';
import { cn } from '../workspace/style';

const INCLUDED = [
  'Uploads up to 200 MB and 1 million rows',
  'Model comparison with a baseline and a reserved final test',
  'Daily scheduled checks, drift and measured accuracy',
  'Razorpay, Zoho Billing, Zoho CRM, Stripe and HubSpot connectors, synced daily',
  'Approved plays as Zoho CRM or HubSpot tasks',
  'A renewal radar: who renews soon, ranked by risk',
  'An email digest after every daily check',
  'Nemotron briefs, account notes and Ask AI, all checked',
  'Holdout groups and measured outreach lift',
  'Playbooks with citations',
  'Team workspaces with roles and an audit log',
  'Approvals, a token budget and a kill switch',
];

const SOON: [string, string][] = [
  [
    'More connectors',
    'Salesforce, Freshdesk, Chargebee, Intercom and Zendesk. Razorpay, Zoho, Stripe and HubSpot work today.',
  ],
  [
    'Slack digests',
    'Each morning’s brief in the channel your team already uses.',
  ],
  [
    'Hosted plans',
    'Today you run it yourself; hosted plans and prices come later.',
  ],
];

const QUESTIONS: [string, string][] = [
  [
    'Is it really free?',
    'Yes, while Holdfast is in preview. There are no paid plans yet. AI usage goes through your own Nebius account, capped by a daily token budget you set.',
  ],
  [
    'Do I need to know machine learning?',
    'No. You confirm what churn means and which columns exist before it happens; Holdfast compares the models, picks one fairly and explains the result in plain words.',
  ],
  [
    'Does the AI see my customers?',
    'It sees computed results and labels like A1, never raw rows or real account IDs. Columns you block in the privacy policy are never sent at all.',
  ],
  [
    'Will it contact my customers?',
    'Never on its own. It proposes plays; a person approves them, and the list goes to your team.',
  ],
  [
    'Can I prove it saved anyone?',
    'Only with a holdout group, and Holdfast says so. It compares contacted and held-back accounts once outcomes are known, with a 95% range, and says “no clear difference yet” when that is the honest answer.',
  ],
];

export function PricingPage() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <>
      <section className="bg-field-800 px-5 pt-[136px] pb-24 sm:px-8">
        <div className="mx-auto grid max-w-[1320px] gap-14 lg:grid-cols-[1fr_0.9fr] lg:items-start">
          <div>
            <h1
              className="text-[clamp(3.2rem,7.4vw,6rem)] leading-[0.86] font-[860] tracking-[-0.03em]"
              style={{ fontStretch: '66%' }}
            >
              Free while we’re in preview.
            </h1>
            <p className="mt-7 max-w-[34rem] text-[19px] leading-relaxed text-field-100">
              Every feature that works today is free to use. When paid plans
              arrive, they’ll be announced here first, and nothing you build now
              will be locked away.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-6">
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
                to="/product"
                className="text-[15px] text-field-100 underline-offset-4 hover:text-stock hover:underline"
              >
                See what you get
              </Link>
            </div>
          </div>
          <motion.div
            initial={{ rotate: -6, y: -40, opacity: 0 }}
            animate={{ rotate: 2, y: 0, opacity: 1 }}
            transition={{
              type: 'spring',
              stiffness: 80,
              damping: 11,
              delay: 0.15,
            }}
            className="origin-top"
          >
            <div
              className="relative bg-stock pt-12 text-tag-ink shadow-tag-lift"
              style={{ clipPath: TAG_SHAPE }}
            >
              <Grommet className="absolute top-4 left-1/2 size-5 -translate-x-1/2" />
              <div className="flex items-end justify-between bg-field-700 px-6 py-3 text-stock">
                <span
                  className="text-[22px] font-[820] uppercase"
                  style={{ fontStretch: '70%' }}
                >
                  Preview
                </span>
                <span className="font-stamp text-[13px]">$0 / month</span>
              </div>
              <ul className="ruled space-y-2.5 px-6 py-6 text-[15px]">
                {INCLUDED.map((t) => (
                  <li key={t} className="flex gap-2.5">
                    <Check
                      className="mt-0.5 size-4 shrink-0 text-field-700"
                      strokeWidth={3}
                    />{' '}
                    {t}
                  </li>
                ))}
              </ul>
              <span className="perf block h-3" aria-hidden="true" />
              <p className="bg-stock-200 px-6 py-4 text-[13px] text-[#3b4441]">
                Nebius AI usage is billed by Nebius to your own account.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      <section
        id="coming-soon"
        className="scroll-mt-20 bg-tag-amber px-5 py-24 text-tag-ink sm:px-8"
      >
        <div className="mx-auto max-w-[1320px]">
          <h2
            className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            Coming soon.
          </h2>
          <p className="mt-4 max-w-[36rem] text-[17px]">
            Not shipped yet, and never shown as if it were.
          </p>
          <div className="relative mt-14">
            <div
              aria-hidden="true"
              className="absolute inset-x-0 top-0 hidden h-[3px] rounded-full bg-tag-ink/70 md:block"
            />
            <ul className="grid gap-6 md:grid-cols-3 md:gap-5">
              {SOON.map(([title, text], i) => (
                <li
                  key={title}
                  className="relative origin-top bg-stock px-5 pt-11 pb-6 text-tag-ink shadow-tag"
                  style={{
                    clipPath: TAG_SHAPE,
                    transform: `rotate(${[-2, 1.5, -1, 2][i]}deg)`,
                    marginTop: `${[10, 28, 6, 22][i]}px`,
                  }}
                >
                  <Grommet className="absolute top-3.5 left-1/2 size-3.5 -translate-x-1/2" />
                  <p className="-mx-5 flex items-center gap-2 bg-tag-slate px-5 py-1.5 text-stock">
                    <Clock3 className="size-3.5" />
                    <span
                      className="text-[12px] font-[760] uppercase"
                      style={{ fontStretch: '76%' }}
                    >
                      Not yet
                    </span>
                  </p>
                  <p
                    className="mt-3 text-[21px] leading-tight font-[780]"
                    style={{ fontStretch: '76%' }}
                  >
                    {title}
                  </p>
                  <p className="mt-2 text-[14px] leading-snug text-[#3b4441]">
                    {text}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="bg-stock px-5 py-24 text-tag-ink sm:px-8">
        <div className="mx-auto grid max-w-[1320px] gap-12 lg:grid-cols-[0.8fr_1.4fr]">
          <h2
            className="text-[clamp(2.4rem,5vw,4.4rem)] leading-[0.92] font-[820]"
            style={{ fontStretch: '66%' }}
          >
            Straight answers.
          </h2>
          <div className="divide-y divide-tag-ink/12 border-y border-tag-ink/12">
            {QUESTIONS.map(([q, a], i) => (
              <div key={q}>
                <h3>
                  <button
                    type="button"
                    onClick={() => setOpen(open === i ? null : i)}
                    aria-expanded={open === i}
                    className="flex w-full cursor-pointer items-center justify-between gap-6 py-6 text-left text-[21px] font-[740]"
                    style={{ fontStretch: '80%' }}
                  >
                    {q}
                    <Plus
                      className={cn(
                        'size-5 shrink-0 transition-transform duration-300',
                        open === i && 'rotate-45',
                      )}
                    />
                  </button>
                </h3>
                <AnimatePresence initial={false}>
                  {open === i && (
                    <motion.p
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                      className="overflow-hidden"
                    >
                      <span className="block max-w-[62ch] pb-6 text-[16px] leading-relaxed text-[#3b4441]">
                        {a}
                      </span>
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
