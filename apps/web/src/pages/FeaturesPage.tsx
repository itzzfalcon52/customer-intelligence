import { useState } from 'react';
import { ArrowUpRight, Check, CircleDot, Sparkle } from 'lucide-react';
import { useOutletContext } from 'react-router-dom';
import { capabilities } from '../lib/content';
import { FinalCTA } from '../components/FinalCTA';
import { SignalExplorer } from '../components/SignalExplorer';
import type { SiteContext } from '../components/SiteLayout';

export function FeaturesPage() {
  const [filter, setFilter] = useState<'all' | 'available' | 'planned'>('all');
  const { openDemo } = useOutletContext<SiteContext>();
  return (
    <>
      <section className="page-hero features-hero">
        <span className="eyebrow">THE CUSTOMER INTELLIGENCE PLATFORM</span>
        <h1>
          Connect the dots.
          <br />
          <em>Keep the people.</em>
        </h1>
        <div className="page-hero-bottom">
          <p>
            From your first customer sheet to a more connected retention
            workspace. Every step should make the next decision a little
            clearer.
          </p>
          <button onClick={openDemo} className="button button-dark">
            Take a closer look <ArrowUpRight size={18} />
          </button>
        </div>
        <span className="page-hero-star" aria-hidden="true">
          ✳
        </span>
      </section>
      <section className="capability-section section-wrap">
        <div className="capability-toolbar">
          <span className="eyebrow">THE PLATFORM, STEP BY STEP</span>
          <div
            className="filter-group"
            role="group"
            aria-label="Filter capabilities"
          >
            {(['all', 'available', 'planned'] as const).map((value) => (
              <button
                key={value}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
              >
                {value === 'all'
                  ? 'The whole picture'
                  : value === 'available'
                    ? 'Built today'
                    : 'Coming next'}
              </button>
            ))}
          </div>
        </div>
        <p className="scope-note">
          “Built today” describes the working backend. The app screens are next;
          connected signals and actions are planned.
        </p>
        <div className="capability-list">
          {capabilities
            .filter((item) => filter === 'all' || item.status === filter)
            .map((item) => (
              <article
                key={item.id}
                className={`capability-row ${item.status === 'planned' ? 'capability-planned' : ''}`}
              >
                <span className="capability-number">{item.number}</span>
                <div>
                  <div className="capability-label">
                    <span>{item.category}</span>
                    <span className="status-pill">
                      {item.status === 'available' ? (
                        <CircleDot size={11} />
                      ) : (
                        <Sparkle size={11} />
                      )}
                      {item.status === 'available'
                        ? 'Built today · backend'
                        : 'On the roadmap'}
                    </span>
                  </div>
                  <h2>{item.title}</h2>
                  <p>{item.description}</p>
                </div>
                <ul>
                  {item.details.map((detail) => (
                    <li key={detail}>
                      <Check size={15} />
                      {detail}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
        </div>
      </section>
      <section className="features-demo experience-section" data-reveal>
        <div className="experience-heading">
          <div>
            <span className="eyebrow">EXPLORE THE PRODUCT VISION</span>
            <h2>
              A signal is just
              <br />
              <em>the beginning.</em>
            </h2>
          </div>
          <p>
            Try an illustrative account journey.
            <br />
            The live workspace comes next.
          </p>
        </div>
        <SignalExplorer />
      </section>
      <section
        className="principles-section section-wrap"
        id="roadmap"
        data-reveal
      >
        <div>
          <span className="eyebrow">WHERE WE GO NEXT</span>
          <h2>
            Thoughtful by design.
            <br />
            <em>Connected by ambition.</em>
          </h2>
        </div>
        <div className="principle-columns">
          <article>
            <span>01 / CONNECT</span>
            <h3>Bring the story together.</h3>
            <p>
              Planned billing, usage, support, and CRM connectors build on the
              spreadsheet foundation, with explicit schema mapping and account
              timelines.
            </p>
          </article>
          <article>
            <span>02 / REVIEW</span>
            <h3>Keep people in the loop.</h3>
            <p>
              Playbook-informed action drafts and reviewed CRM tasks help teams
              move thoughtfully. Your team approves a next step before it leaves
              the workspace.
            </p>
          </article>
          <article>
            <span>03 / LEARN</span>
            <h3>Measure what helps.</h3>
            <p>
              Track conversations and run retention experiments. Predicted risk
              helps prioritize; measured outcomes tell you whether an
              intervention made a difference.
            </p>
          </article>
        </div>
      </section>
      <FinalCTA />
    </>
  );
}
