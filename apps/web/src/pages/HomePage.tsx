import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  Database,
  FileSpreadsheet,
  GitCompareArrows,
  MessageSquare,
  Play,
  ShieldCheck,
  Waypoints,
} from 'lucide-react';
import { Link, useOutletContext } from 'react-router-dom';
import { RetentionPreview } from '../components/RetentionPreview';
import type { SiteContext } from '../components/SiteLayout';

const steps = [
  {
    icon: FileSpreadsheet,
    number: '01',
    title: 'Bring your customer data.',
    body: 'Start with a CSV or Excel file. Find missing information and choose what you want to predict.',
  },
  {
    icon: GitCompareArrows,
    number: '02',
    title: 'Find the model that fits.',
    body: 'Compare models on your data. See how they perform, where they fall short, and which one earns your trust.',
  },
  {
    icon: Waypoints,
    number: '03',
    title: 'Know where to focus.',
    body: 'Rank your customers by risk, choose how many to review, and export a list your team can work with.',
  },
];
const faqs = [
  [
    'Who is Customer Intelligence for?',
    'Subscription and SaaS teams that want to use their customer history to prioritize retention. Start with a spreadsheet containing customer information and a clearly defined churn outcome.',
  ],
  [
    'Do I need to be a data scientist?',
    'You need to understand your customer data and what churn means for your business. The product is designed to guide model comparison and explain results in plain language.',
  ],
  [
    'What can I try today?',
    'You can explore the interactive product preview here. Data import, model comparison, scoring, and the AI assistant are implemented in the backend. Account access and the connected app screens are still being built.',
  ],
  [
    'Can I connect my CRM or billing tool?',
    'Those connections are planned. The current backend accepts CSV and Excel files. We are building toward shared customer timelines, reviewed follow-ups, and outcome tracking.',
  ],
];
export function HomePage() {
  const { openDemo } = useOutletContext<SiteContext>();
  return (
    <div className="saas-home">
      <section className="saas-hero">
        <div className="hero-orbit orbit-one" aria-hidden="true" />
        <div className="hero-orbit orbit-two" aria-hidden="true" />
        <div className="saas-hero-copy">
          <span className="saas-pill">
            <span /> CUSTOMER INTELLIGENCE FOR SAAS
          </span>
          <h1>
            Know who needs you.
            <br />
            <em>Before they leave.</em>
          </h1>
          <p>
            Turn customer data into a clear plan for retention.
            <br className="desktop-break" /> Spot risk, understand the signals,
            and give your team a place to start.
          </p>
          <div className="saas-hero-actions">
            <button className="button button-lime" onClick={openDemo}>
              Explore the product <ArrowUpRight size={19} />
            </button>
            <a href="#how-it-works" className="saas-secondary">
              <Play size={14} /> See how it works
            </a>
          </div>
          <div className="saas-hero-note">
            <Check size={13} /> Built for subscription teams <span>·</span> Your
            data. Clearer decisions.
          </div>
        </div>
        <div className="saas-product-stage">
          <div className="stage-caption">
            <span>
              <i /> FROM SPREADSHEET TO NEXT STEP
            </span>
            <span>
              Try selecting a customer <ArrowDownRight size={14} />
            </span>
          </div>
          <RetentionPreview />
        </div>
      </section>
      <section className="saas-foundation" aria-label="Platform foundation">
        <span>LESS GUESSWORK. MORE CONTEXT.</span>
        <div>
          <FileSpreadsheet size={19} /> CSV & Excel
        </div>
        <div>
          <GitCompareArrows size={19} /> Model comparison
        </div>
        <div>
          <MessageSquare size={19} /> NVIDIA Nemotron
        </div>
        <div>
          <Database size={19} /> Powered by Nebius
        </div>
      </section>
      <section className="saas-section" id="how-it-works">
        <div className="saas-section-heading">
          <div>
            <span className="saas-eyebrow">FROM DATA TO DIRECTION</span>
            <h2>
              Your next move,
              <br />
              <em>made clearer.</em>
            </h2>
          </div>
          <p>
            You have the customer history.
            <br />
            Put it to work, one step at a time.
          </p>
        </div>
        <div className="saas-step-grid">
          {steps.map(({ icon: Icon, number, title, body }) => (
            <article className="saas-step" key={number}>
              <div className="saas-step-top">
                <span>
                  <Icon size={25} />
                </span>
                <small>{number}</small>
              </div>
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
        <Link className="text-link" to="/features">
          See everything on the platform <ArrowRight size={17} />
        </Link>
      </section>
      <section className="saas-copilot saas-section">
        <div className="saas-copilot-copy">
          <span className="saas-eyebrow">MEET YOUR RETENTION COPILOT</span>
          <h2>
            Good questions.
            <br />
            <em>Useful answers.</em>
          </h2>
          <p>
            Ask what a result means, why a model was selected, or which
            customers to review. Get explanations tied to your data and saved
            results.
          </p>
          <ul>
            <li>
              <Check size={16} /> Understand the numbers in plain language
            </li>
            <li>
              <Check size={16} /> Follow the evidence behind an answer
            </li>
            <li>
              <Check size={16} /> Keep the final decision with your team
            </li>
          </ul>
          <span className="saas-provider">
            NVIDIA Nemotron <span>on</span> Nebius
          </span>
        </div>
        <div className="saas-chat">
          <div className="saas-chat-header">
            <span className="chat-mark">✳</span>
            <div>
              <strong>Your copilot</strong>
              <small>Context for every decision</small>
            </div>
            <span className="saas-chat-label">Example</span>
          </div>
          <div className="chat-question">
            Why should I look at Northstar first?
          </div>
          <div className="chat-answer">
            <span>✳</span>
            <div>
              <p>Its activity has dropped, making it worth a closer look.</p>
              <p>
                Check whether the team is blocked before deciding how to follow
                up. A risk score alone can’t tell us why they might leave.
              </p>
              <div className="chat-source">
                <FileSpreadsheet size={13} /> Example activity history{' '}
                <ArrowUpRight size={12} />
              </div>
            </div>
          </div>
          <button onClick={openDemo} className="chat-prompt">
            Explore the product tour <ArrowRight size={18} />
          </button>
          <small className="chat-disclaimer">
            Illustrative conversation. Connected activity signals are planned.
          </small>
        </div>
      </section>
      <section className="saas-roadmap saas-section">
        <div>
          <span className="saas-eyebrow">BUILT FOR THE BIGGER PICTURE</span>
          <h2>
            One customer.
            <br />
            <em>The whole story.</em>
          </h2>
          <p>
            We’re bringing billing, product activity, and support together—so
            your next conversation starts with context.
          </p>
          <Link to="/features#roadmap" className="text-link">
            Explore the roadmap <ArrowUpRight size={17} />
          </Link>
        </div>
        <div className="saas-connectors">
          <div className="connector-center">
            <Waypoints size={30} />
            <strong>Customer Intelligence</strong>
          </div>
          <div className="connector-grid">
            {[
              'Billing & renewals',
              'Product activity',
              'Support history',
              'CRM & follow-ups',
            ].map((label) => (
              <div key={label}>
                <span>{label}</span>
                <small>Planned</small>
              </div>
            ))}
          </div>
          <p>
            <ShieldCheck size={15} /> Review suggested actions before anything
            is sent.
          </p>
        </div>
      </section>
      <section className="saas-faq saas-section">
        <div>
          <span className="saas-eyebrow">A FEW THINGS TO KNOW</span>
          <h2>Good questions.</h2>
        </div>
        <div>
          {faqs.map(([question, answer]) => (
            <details key={question}>
              <summary>
                {question}
                <span>+</span>
              </summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>
      </section>
      <section className="saas-final">
        <div aria-hidden="true" className="saas-final-star">
          ✳
        </div>
        <span className="saas-eyebrow">MAKE YOUR NEXT CONVERSATION COUNT</span>
        <h2>
          Keep your best customers
          <br />
          <em>closer.</em>
        </h2>
        <p>Start with a clearer view of who needs your attention.</p>
        <button className="button button-lime" onClick={openDemo}>
          Take a look inside <ArrowUpRight size={19} />
        </button>
        <span className="saas-final-note">
          Explore the product preview. No account needed.
        </span>
      </section>
    </div>
  );
}
