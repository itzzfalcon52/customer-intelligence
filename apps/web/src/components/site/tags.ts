/**
 * Demonstration accounts for the marketing site. Every company here is synthetic, matching the
 * labelled synthetic SaaS workspace the product ships with; the copy says so wherever they appear.
 * Reasons and numbers have the shape the product really produces (computed drivers, a checked
 * Nemotron note, a playbook citation), not results from any real customer.
 */
export type Level = 'call' | 'watch' | 'lower';

export interface DemoAccount {
  id: string;
  name: string;
  rank: number;
  risk: number;
  level: Level;
  plan: string;
  mrr: string;
  stands: [string, string, string][];
  note: string;
  play: string;
}

export const LEVEL: Record<
  Level,
  { label: string; bar: string; text: string }
> = {
  call: { label: 'Call first', bar: 'bg-tag-red', text: 'text-tag-red' },
  watch: { label: 'Watch', bar: 'bg-tag-amber', text: 'text-tag-ink' },
  lower: { label: 'Lower', bar: 'bg-tag-slate', text: 'text-tag-slate' },
};

export const ACCOUNTS: DemoAccount[] = [
  {
    id: 'ACME-0757',
    name: 'Brightwater Logistics',
    rank: 1,
    risk: 0.688,
    level: 'call',
    plan: 'Growth · 40 seats',
    mrr: '$2,400',
    stands: [
      ['Logins, 30 days', '4', '124'],
      ['Days since active', '9', '3'],
      ['Billing tickets, 90 days', '1', '0'],
    ],
    note: 'Barely logging in (4 logins in 30 days vs a typical 124) and inactive for 9 days.',
    play: 'Usage drop',
  },
  {
    id: 'ACME-0629',
    name: 'Kestrel Health',
    rank: 2,
    risk: 0.667,
    level: 'call',
    plan: 'Growth · 25 seats',
    mrr: '$1,500',
    stands: [
      ['Days since active', '10', '3'],
      ['Billing tickets, 90 days', '1', '0'],
      ['Industry', 'Healthcare', 'Education'],
    ],
    note: 'Inactive for 10 days (typical 3) with a billing ticket open this quarter.',
    play: 'Failed payments',
  },
  {
    id: 'ACME-0440',
    name: 'Northwind Studio',
    rank: 3,
    risk: 0.5,
    level: 'call',
    plan: 'Starter · 8 seats',
    mrr: '$450',
    stands: [
      ['Logins, 30 days', '12', '124'],
      ['Monthly revenue', '45', '165'],
      ['Usage change', '-46.7%', '-1.3%'],
    ],
    note: 'Usage fell 46.7% month on month while logins dropped to 12.',
    play: 'Usage drop',
  },
  {
    id: 'ACME-0667',
    name: 'Halyard Freight',
    rank: 4,
    risk: 0.472,
    level: 'watch',
    plan: 'Growth · 18 seats',
    mrr: '$1,080',
    stands: [
      ['Days since active', '12', '3'],
      ['Cancellation tickets', '1', '0'],
      ['Logins, 30 days', '5', '124'],
    ],
    note: 'A cancellation-intent ticket and 12 quiet days stand out.',
    play: 'Cancellation intent',
  },
  {
    id: 'ACME-0011',
    name: 'Copperline Labs',
    rank: 6,
    risk: 0.468,
    level: 'watch',
    plan: 'Team · 12 seats',
    mrr: '$720',
    stands: [
      ['Active users', '0.38', '6.81'],
      ['Failed payments', '1', '0'],
      ['Logins, 30 days', '6', '124'],
    ],
    note: 'Fewer than one active user a day and a failed payment.',
    play: 'Failed payments',
  },
  {
    id: 'ACME-0204',
    name: 'Fernhill Schools',
    rank: 8,
    risk: 0.454,
    level: 'watch',
    plan: 'Starter · 6 seats',
    mrr: '$300',
    stands: [
      ['Logins, 30 days', '16', '124'],
      ['Support tickets', '3', '1'],
      ['Tenure, days', '389', '181'],
    ],
    note: 'Logins down to 16 with three support tickets open.',
    play: 'Adoption review',
  },
  {
    id: 'ACME-0502',
    name: 'Osprey Analytics',
    rank: 9,
    risk: 0.429,
    level: 'watch',
    plan: 'Growth · 30 seats',
    mrr: '$1,800',
    stands: [
      ['Cancellation tickets', '3', '0'],
      ['Active users', '0.5', '6.81'],
      ['Logins, 30 days', '8', '124'],
    ],
    note: 'Three cancellation-intent tickets in 90 days.',
    play: 'Cancellation intent',
  },
  {
    id: 'ACME-0185',
    name: 'Tidemark Retail',
    rank: 16,
    risk: 0.328,
    level: 'lower',
    plan: 'Team · 10 seats',
    mrr: '$600',
    stands: [
      ['Tenure, days', '654', '181'],
      ['Logins, 30 days', '13', '124'],
      ['Active users', '0.8', '6.81'],
    ],
    note: 'Long tenure; logins lighter than usual.',
    play: 'Check-in',
  },
];
