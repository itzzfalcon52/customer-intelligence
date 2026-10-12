import { useId, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUpRight,
  Check,
  FileSpreadsheet,
  MessageSquare,
  Radar,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import type { KeyboardEvent } from 'react';

const stages = [
  {
    title: 'See the signals',
    subtitle: 'A clearer view of your customers.',
    icon: FileSpreadsheet,
  },
  {
    title: 'Understand the why',
    subtitle: 'An answer you can investigate.',
    icon: Search,
  },
  {
    title: 'Make your next move',
    subtitle: 'The conversation starts with context.',
    icon: ArrowUpRight,
  },
];
const accounts = [
  {
    name: 'Northstar Studio',
    initials: 'NS',
    signal: 'Product activity slowed',
    action: 'Explore adoption barriers',
    color: 'lavender',
  },
  {
    name: 'Goodform',
    initials: 'G',
    signal: 'Renewal is approaching',
    action: 'Review the account together',
    color: 'peach',
  },
  {
    name: 'Orbit & Co.',
    initials: 'O',
    signal: 'Support conversation open',
    action: 'Follow up with the support team',
    color: 'mint',
  },
];

/** An explicitly illustrative concept, never an API response or a fabricated ML result. */
export function SignalExplorer({
  idPrefix = 'explorer',
}: {
  idPrefix?: string;
}) {
  const [stage, setStage] = useState(0);
  const [budget, setBudget] = useState(2);
  const uid = useId();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const prefix = `${idPrefix}-${uid}`;
  function onTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next =
      event.key === 'ArrowRight'
        ? (index + 1) % 3
        : event.key === 'ArrowLeft'
          ? (index + 2) % 3
          : event.key === 'Home'
            ? 0
            : event.key === 'End'
              ? 2
              : null;
    if (next === null) return;
    event.preventDefault();
    setStage(next);
    tabRefs.current[next]?.focus();
  }
  return (
    <div className="signal-explorer">
      <div
        className="explorer-tabs"
        role="tablist"
        aria-label="Explore the retention workflow"
      >
        {stages.map((item, index) => (
          <button
            key={item.title}
            type="button"
            role="tab"
            id={`${prefix}-tab-${index}`}
            aria-controls={`${prefix}-panel`}
            aria-selected={stage === index}
            tabIndex={stage === index ? 0 : -1}
            onKeyDown={(event) => onTabKey(event, index)}
            onClick={() => setStage(index)}
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
          >
            <span>0{index + 1}</span>
            {item.title}
          </button>
        ))}
      </div>
      <div
        className="explorer-panel"
        role="tabpanel"
        id={`${prefix}-panel`}
        aria-labelledby={`${prefix}-tab-${stage}`}
        tabIndex={0}
      >
        <div className="workspace-top">
          <span>
            <Radar size={18} /> YOUR RETENTION WORKSPACE
          </span>
          <span className="concept-label">Product concept</span>
        </div>
        <div className="workspace-heading">
          <h3>{stages[stage].subtitle}</h3>
          <span className="workspace-date">
            A little context goes a long way.
          </span>
        </div>
        {stage === 0 && (
          <div className="signal-table">
            <div className="signal-table-head">
              <span>ACCOUNT</span>
              <span>WORTH A LOOK</span>
            </div>
            {accounts.map((account) => (
              <div className="signal-row" key={account.name}>
                <span className={`mini-avatar ${account.color}`}>
                  {account.initials}
                </span>
                <strong>{account.name}</strong>
                <span className="signal-reason">
                  <i />
                  {account.signal}
                </span>
              </div>
            ))}
            <div className="source-line">
              <span>
                <FileSpreadsheet size={13} /> Customer sheet
              </span>
              <ArrowDown size={13} />
              <span>Connected signals on the roadmap</span>
            </div>
          </div>
        )}
        {stage === 1 && (
          <div className="copilot-preview">
            <div className="chat-question">
              What should I look into for Northstar?
            </div>
            <div className="chat-answer">
              <span className="copilot-icon">
                <MessageSquare size={16} />
              </span>
              <div>
                <strong>Start with the change in activity.</strong>
                <p>
                  In this example, product activity has slowed. Check whether
                  the team is blocked, changing its workflow, or needs help
                  getting value.
                </p>
                <div className="evidence-chip">
                  <Search size={12} /> Illustrative usage signal · not a causal
                  explanation
                </div>
              </div>
            </div>
            <div className="copilot-foot">
              The real copilot grounds answers in recorded tool results.
            </div>
          </div>
        )}
        {stage === 2 && (
          <div className="action-preview">
            <div className="budget-control">
              <label htmlFor={`${prefix}-budget`}>
                <SlidersHorizontal size={15} /> Conversations to prioritize{' '}
                <strong>{budget}</strong>
              </label>
              <input
                id={`${prefix}-budget`}
                type="range"
                min="1"
                max="3"
                value={budget}
                onChange={(event) => setBudget(Number(event.target.value))}
              />
            </div>
            {accounts.slice(0, budget).map((account, index) => (
              <div className="action-row" key={account.name}>
                <span>0{index + 1}</span>
                <div>
                  <strong>{account.name}</strong>
                  <small>{account.action}</small>
                </div>
                <Check size={16} />
              </div>
            ))}
            <div className="review-note">
              You review the next step. CRM actions are planned.
            </div>
          </div>
        )}
      </div>
      <p className="demo-caption">
        Try the tabs above. Fictional accounts and signals illustrate the
        product vision.
      </p>
    </div>
  );
}
