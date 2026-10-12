import { ArrowUpRight, Check, Minus, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import { FinalCTA } from '../components/FinalCTA';

const plans = [
  {
    name: 'Explore',
    eyebrow: 'FOR THE FIRST GOOD QUESTION',
    price: 'Early access',
    description:
      'Get to know the approach. Start with your data and a clearer view of what’s possible.',
    items: [
      'Spreadsheet-first workflow',
      'Model comparison and evidence',
      'Customer scoring and shortlist exports',
      'Nemotron evidence copilot',
    ],
    cta: 'Explore the preview',
    highlight: true,
    note: 'Product preview · no payment required',
  },
  {
    name: 'Grow',
    eyebrow: 'FOR YOUR NEXT CHAPTER',
    price: 'Coming next',
    description:
      'A shared retention workspace for the team behind your customer relationships.',
    items: [
      'Planned team workspaces and roles',
      'Planned connected SaaS signals',
      'Planned account timelines',
      'Planned reviewed action drafts',
    ],
    cta: 'See the roadmap',
    highlight: false,
    note: 'Planned tier · pricing to be announced',
  },
  {
    name: 'Partner',
    eyebrow: 'FOR A MORE CONNECTED FUTURE',
    price: 'Let’s shape it',
    description:
      'Help shape deeper workflows around your business, your data, and your customers.',
    items: [
      'Future CRM and billing workflows',
      'Future playbook context',
      'Future outcome experiments',
      'Future integration requirements',
    ],
    cta: 'Explore the vision',
    highlight: false,
    note: 'Future offering · not available for purchase',
  },
];
export function PricingPage() {
  return (
    <>
      <section className="page-hero pricing-hero">
        <span className="eyebrow">ROOM TO START. SPACE TO GROW.</span>
        <h1>
          Good relationships
          <br />
          <em>start somewhere.</em>
        </h1>
        <p>
          We’re building for subscription teams at every stage.
          <br />
          Start with the preview. Help shape what comes next.
        </p>
        <div className="pricing-note">
          <span className="live-dot" /> Early product preview. Paid plans are
          not live.
        </div>
      </section>
      <section className="pricing-section section-wrap">
        <div className="pricing-grid">
          {plans.map((plan) => (
            <article
              key={plan.name}
              className={`pricing-card ${plan.highlight ? 'pricing-featured' : ''}`}
            >
              <span className="eyebrow">{plan.eyebrow}</span>
              <h2>
                {plan.name}
                {plan.highlight && <span aria-hidden="true">✳</span>}
              </h2>
              <p>{plan.description}</p>
              <div className="plan-price">{plan.price}</div>
              <Link
                to={plan.highlight ? '/signup' : '/features#roadmap'}
                className={`button ${plan.highlight ? 'button-lime' : 'button-outline'}`}
              >
                {plan.cta}
                <ArrowUpRight size={17} />
              </Link>
              <small>{plan.note}</small>
              <ul>
                {plan.items.map((item) => (
                  <li key={item}>
                    <Check size={15} />
                    {item}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
        <p className="pricing-disclosure">
          Accounts are available. Paid plans and checkout are not connected.
          Backend capabilities are implemented; the customer workflow screens,
          team accounts, and paid plans are upcoming.
        </p>
      </section>
      <section className="pricing-faq section-wrap" data-reveal>
        <div>
          <span className="eyebrow">NO GUESSWORK HERE, EITHER</span>
          <h2>
            Before you
            <br />
            <em>jump in.</em>
          </h2>
        </div>
        <div className="faq-list">
          {[
            [
              'Will I be charged?',
              'No. This frontend is a product preview with no checkout or payment collection. Prices and plan limits have not been announced.',
            ],
            [
              'Can I create an account now?',
              'Yes. Create an account with email and password, then verify your email. Google sign-in is available when configured. Paid plans are not active.',
            ],
            [
              'What can the backend do today?',
              'Import CSV/Excel data, check readiness, compare binary classification models, score current customers, export ranked contacts, and explain recorded evidence through the copilot. The next milestone connects these workflows to the app screens.',
            ],
            [
              'What will determine future pricing?',
              'We plan to learn from pilot needs: account volume, integrations, collaboration, and support. There are no committed paid plan features or prices yet.',
            ],
          ].map(([q, a]) => (
            <details key={q}>
              <summary>
                {q}
                <Plus className="faq-plus" size={18} />
                <Minus className="faq-minus" size={18} />
              </summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>
      <FinalCTA />
    </>
  );
}
