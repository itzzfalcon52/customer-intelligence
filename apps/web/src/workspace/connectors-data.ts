/** Connector providers: names, roles, guide anchors and the credential fields each needs. */
export type Provider =
  'stripe' | 'razorpay' | 'zoho_billing' | 'hubspot' | 'zoho_crm';

export interface Connection {
  id: string;
  provider: Provider;
  role: 'billing' | 'crm';
  label: string;
  last_synced_at: string | null;
  last_source_id: string | null;
  last_error: string | null;
  write_enabled: boolean;
  churn_property: string | null;
  enrich_connection_id: string | null;
  last_counts: {
    accounts?: number;
    invoices?: number;
    tickets?: number;
    cancelled?: number | null;
  } | null;
  last_match: {
    billing_accounts: number;
    matched: number;
    matched_by_crm_id?: number;
    rate: number;
  } | null;
  last_notes: string[];
}

export const ZOHO_REGIONS = [
  ['in', 'India (zoho.in)'],
  ['com', 'United States (zoho.com)'],
  ['eu', 'Europe (zoho.eu)'],
  ['au', 'Australia (zoho.com.au)'],
  ['jp', 'Japan (zoho.jp)'],
  ['ca', 'Canada (zohocloud.ca)'],
  ['sa', 'Saudi Arabia (zoho.sa)'],
] as const;

interface FieldSpec {
  key: string;
  label: string;
  secret?: boolean;
  placeholder?: string;
  optional?: boolean;
  region?: boolean;
}

const ZOHO_FIELDS: FieldSpec[] = [
  { key: 'region', label: 'Zoho region', region: true },
  { key: 'client_id', label: 'Client ID', placeholder: '1000.…' },
  { key: 'client_secret', label: 'Client secret', secret: true },
  {
    key: 'code',
    label: 'One-time code',
    secret: true,
    placeholder: '1000.… (works once, for a few minutes)',
  },
];

export const PROVIDERS: Record<
  Provider,
  {
    name: string;
    role: 'billing' | 'crm';
    anchor: string;
    label: string;
    about: string;
    note?: string;
    single?: { label: string; placeholder: string };
    fields?: FieldSpec[];
  }
> = {
  stripe: {
    name: 'Stripe',
    role: 'billing',
    anchor: 'stripe',
    label: 'Stripe billing',
    about:
      'Customers, subscriptions and invoices: plan, seats, revenue, failed payments and cancellations.',
    note: 'New Indian businesses can join Stripe by invitation only; use Razorpay or Zoho Billing instead.',
    single: { label: 'Restricted key', placeholder: 'rk_live_… or rk_test_…' },
  },
  razorpay: {
    name: 'Razorpay',
    role: 'billing',
    anchor: 'razorpay',
    label: 'Razorpay payments',
    about:
      'Customers, Razorpay Subscriptions, plans and invoices: plan, seats, revenue, failed payments and cancellations.',
    fields: [
      {
        key: 'key_id',
        label: 'Key ID',
        placeholder: 'rzp_live_… or rzp_test_…',
      },
      { key: 'key_secret', label: 'Key secret', secret: true },
    ],
  },
  zoho_billing: {
    name: 'Zoho Billing',
    role: 'billing',
    anchor: 'zoho-billing',
    label: 'Zoho Billing',
    about:
      'Customers, subscriptions and invoices from Zoho Billing (formerly Zoho Subscriptions). Customers Zoho already linked to Zoho CRM match exactly.',
    fields: [
      ...ZOHO_FIELDS,
      {
        key: 'organization_id',
        label: 'Organisation ID',
        optional: true,
        placeholder: 'Only if you have several',
      },
    ],
  },
  hubspot: {
    name: 'HubSpot',
    role: 'crm',
    anchor: 'hubspot',
    label: 'HubSpot CRM',
    about:
      'Companies and support tickets; optionally, approved plays become tasks for the account owner.',
    single: { label: 'Private app access token', placeholder: 'pat-…' },
  },
  zoho_crm: {
    name: 'Zoho CRM',
    role: 'crm',
    anchor: 'zoho-crm',
    label: 'Zoho CRM',
    about:
      'Accounts and Cases (support tickets); optionally, approved plays become Zoho CRM tasks.',
    fields: ZOHO_FIELDS,
  },
};

export const GUIDE = '/app/guides/connectors';
