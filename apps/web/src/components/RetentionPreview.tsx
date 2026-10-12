import { useState } from 'react';
import {
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  LayoutDashboard,
  ListFilter,
  MessageSquare,
  MoreHorizontal,
  Users,
} from 'lucide-react';

const accounts = [
  {
    name: 'Northstar',
    initials: 'N',
    color: 'violet',
    plan: 'Growth plan',
    risk: 'High',
    reason: 'Product activity is slowing down.',
    detail:
      'Weekly active users fell from 18 to 7 in this example. Start by checking whether the team is blocked or their needs have changed.',
    trend: '−61%',
    points: '0,12 30,20 60,14 90,35 120,31 150,48 180,61 210,67',
  },
  {
    name: 'Layers',
    initials: 'L',
    color: 'peach',
    plan: 'Business plan',
    risk: 'High',
    reason: 'An unresolved issue needs attention.',
    detail:
      'This example account has an open support issue ahead of renewal. Review the conversation with the account owner before recommending an action.',
    trend: '−38%',
    points: '0,14 30,12 60,29 90,24 120,38 150,35 180,51 210,49',
  },
  {
    name: 'Orbit Studio',
    initials: 'O',
    color: 'green',
    plan: 'Growth plan',
    risk: 'Medium',
    reason: 'A renewal is approaching.',
    detail:
      'The example renewal is in 14 days. Review recent activity and confirm the customer’s plans before deciding whether outreach is needed.',
    trend: '−12%',
    points: '0,28 30,25 60,31 90,20 120,33 150,29 180,36 210,35',
  },
] as const;

/** Fictional product concept; no backend calls or customer information. */
export function RetentionPreview() {
  const [selected, setSelected] = useState(0);
  const account = accounts[selected];
  return (
    <div className="retention-preview">
      <aside className="preview-sidebar" aria-hidden="true">
        <div className="preview-symbol">✳</div>
        <LayoutDashboard size={18} />
        <Users size={18} />
        <MessageSquare size={18} />
        <span className="preview-avatar">JD</span>
      </aside>
      <div className="preview-main">
        <div className="preview-toolbar">
          <span>
            Workspace <ChevronRight size={12} /> Customer overview
          </span>
          <span className="preview-label">Interactive preview</span>
        </div>
        <div className="preview-title">
          <div>
            <p>YOUR RETENTION WORKSPACE</p>
            <h3>A little clarity. A better next step.</h3>
          </div>
          <MoreHorizontal size={21} />
        </div>
        <div className="preview-metrics">
          <div>
            <span>Customers</span>
            <strong>
              248 <small>This month</small>
            </strong>
          </div>
          <div>
            <span>Need attention</span>
            <strong>
              24 <i className="metric-dot" />
            </strong>
          </div>
          <div>
            <span>Upcoming renewals</span>
            <strong>
              18 <small>Next 30 days</small>
            </strong>
          </div>
        </div>
        <div className="preview-workspace">
          <div className="preview-list">
            <div className="preview-list-heading">
              <strong>Your priorities</strong>
              <ListFilter size={15} />
            </div>
            <div className="preview-columns">
              <span>Customer</span>
              <span>Risk level</span>
            </div>
            {accounts.map((item, index) => (
              <button
                key={item.name}
                aria-pressed={selected === index}
                className={`preview-account ${selected === index ? 'is-selected' : ''}`}
                onClick={() => setSelected(index)}
              >
                <span className={`account-monogram ${item.color}`}>
                  {item.initials}
                </span>
                <span className="account-name">
                  <strong>{item.name}</strong>
                  <small>{item.plan}</small>
                </span>
                <span className={`risk-tag ${item.risk.toLowerCase()}`}>
                  {item.risk}
                </span>
                <ChevronRight size={14} />
              </button>
            ))}
            <div className="preview-list-footer">
              <Check size={13} /> Select a customer to explore the signals
            </div>
          </div>
          <div
            className="preview-insight"
            aria-live="polite"
            aria-atomic="true"
          >
            <div className="insight-heading">
              <span className="insight-star">✳</span>
              <strong>Behind the score</strong>
              <span>AI insight</span>
            </div>
            <h4>{account.reason}</h4>
            <div className="mini-chart">
              <div>
                <span>Weekly activity</span>
                <strong>
                  {account.trend} <ArrowDownRight size={15} />
                </strong>
              </div>
              <svg
                viewBox="0 0 210 78"
                role="img"
                aria-label={`Illustrative declining activity for ${account.name}`}
              >
                <path
                  d="M0 22H210M0 47H210M0 72H210"
                  stroke="#e4dce9"
                  strokeDasharray="3 4"
                />
                <polyline
                  points={account.points}
                  fill="none"
                  stroke="#78459b"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p>{account.detail}</p>
            <span className="insight-foot">
              Review the context before reaching out <ArrowUpRight size={13} />
            </span>
          </div>
        </div>
        <div className="preview-bottom">
          <span>
            <i /> A clearer view of who needs you
          </span>
          <span>Fictional data · Product concept</span>
        </div>
      </div>
    </div>
  );
}
