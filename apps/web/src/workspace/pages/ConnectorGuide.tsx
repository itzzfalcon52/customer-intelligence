import type { ReactNode } from 'react';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { ButtonLink, Card, PageHeader } from '../ui';

/** Step-by-step instructions for connecting each provider, for admins and their clients. */
export function ConnectorGuide() {
  return (
    <>
      <PageHeader
        back={{ to: '/app/sources#connectors', label: 'Connectors' }}
        title="Connector guide"
        description="How to connect a client’s billing system and CRM to Holdfast, step by step. Share this page with whoever holds the client’s admin login."
        actions={
          <ButtonLink to="/app/sources#connectors" variant="primary">
            Go to connectors <ArrowRight className="size-4" />
          </ButtonLink>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav
          aria-label="On this page"
          className="h-fit space-y-1 text-sm lg:sticky lg:top-24"
        >
          {CONTENTS.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="block px-2 py-1 text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            >
              {label}
            </a>
          ))}
        </nav>
        <div className="min-w-0 space-y-6">
          <Section id="before" title="Before you start">
            <List
              items={[
                'Connecting is done by an owner or admin of the Holdfast workspace. Members can see a connection’s status; viewers can only read.',
                'The client creates the key in their own billing system or CRM and either pastes it in themselves or sends it to you through a secure channel. Never send keys by email or chat.',
                'Holdfast checks a key with one read, then stores it encrypted. It is never shown again, never logged and never sent to the AI.',
                'Holdfast only reads. The one exception is creating CRM tasks for approved plays, which stays off until an admin turns it on.',
                'Email addresses are used only to match billing customers to CRM accounts by company domain; they are not saved with the synced data.',
                'If a connector says “Needs setup”, the person running the Holdfast server runs pnpm setup:connectors once and restarts the API.',
                'Billing connectors also read each subscription’s next renewal date (and, for Stripe and Zoho Billing, whether a cancellation is already scheduled) for the Renewal radar. CSV bundles can add a renews_at column to accounts.csv.',
              ]}
            />
          </Section>

          <Section id="choose" title="Which sources to connect">
            <p>
              Connect <strong>one billing source</strong>: it is the record of
              who paid, failed payments and who cancelled, which is what the
              model learns from. A <strong>CRM</strong> is optional and adds
              company details and support tickets.
            </p>
            <List
              items={[
                'Businesses in India: Razorpay or Zoho Billing for billing, and Zoho CRM as the CRM. Stripe only accepts new Indian businesses by invitation.',
                'Businesses elsewhere: Stripe for billing, and HubSpot or Zoho CRM as the CRM.',
                'Try test or sandbox accounts first. Test data proves the connection works, but it is too small to judge a model.',
              ]}
            />
          </Section>

          <Section id="razorpay" title="Razorpay">
            <Steps
              items={[
                'Sign in to the Razorpay Dashboard as an owner or admin.',
                'To try it first, switch the mode toggle to Test mode. Test keys start with rzp_test_; live keys start with rzp_live_.',
                'Open Account & Settings → API Keys (it may appear under Website and app settings) and click Generate Key, or Regenerate if one exists.',
                'Copy the Key ID and the Key Secret. Razorpay shows the secret only once; download it if offered.',
                'In Holdfast, open Connectors → Razorpay → Connect Razorpay, paste both and click Connect.',
                'Click Sync now. The card shows how many customers, invoices and cancellations were read.',
              ]}
            />
            <Reads>
              Customers, Subscriptions, Plans and Invoices. A customer counts as
              cancelled when all their subscriptions have ended; expired or
              overdue invoices and halted subscriptions count as failed
              payments.
            </Reads>
            <Note>
              Razorpay keys can’t be limited to read-only, so treat this key
              like a password. Holdfast only ever reads with it. To revoke
              access, regenerate the key in Razorpay; the old one stops working.
            </Note>
          </Section>

          <Section
            id="zoho"
            title="Zoho: create a Self Client (Billing and CRM)"
          >
            <p>
              Zoho Billing and Zoho CRM both connect through a Zoho “Self
              Client”. One Self Client can serve both; you generate a separate
              one-time code for each.
            </p>
            <Steps
              items={[
                'Open the Zoho API Console for your data centre: api-console.zoho.in for India (api-console.zoho.com in the US, .eu in Europe, and so on). Sign in as a Zoho admin.',
                'Click Get Started or Add Client, choose Self Client, then Create and confirm.',
                'Open the Client Secret tab and copy the Client ID and Client Secret.',
                'Open the Generate Code tab. Paste the scopes listed below for the product you are connecting, set the time duration to 10 minutes, add a description such as “Holdfast”, and click Create.',
                'Choose the Zoho organisation or portal when asked, then copy the code. It works once and only for those minutes, so connect straight away.',
              ]}
            />
          </Section>

          <Section id="zoho-billing" title="Zoho Billing">
            <Steps
              items={[
                'Create a Self Client and generate a code (above) with these scopes:',
              ]}
            />
            <Code>
              ZohoSubscriptions.customers.READ,ZohoSubscriptions.subscriptions.READ,ZohoSubscriptions.invoices.READ,ZohoSubscriptions.settings.READ
            </Code>
            <Steps
              start={2}
              items={[
                'In Holdfast, open Connectors → Zoho Billing → Connect Zoho Billing.',
                'Choose the region (India is zoho.in), then paste the Client ID, Client Secret and the one-time code.',
                'If the client has more than one Zoho Billing organisation, also enter the Organisation ID. Holdfast lists the IDs if one is needed; it is also shown in Zoho Billing under Settings → Organization Profile.',
                'Click Connect, then Sync now.',
              ]}
            />
            <Reads>
              Customers, Subscriptions and Invoices. Cancelled or expired
              subscriptions mark a customer as cancelled; overdue or unpaid
              invoices count as failed payments. Customers Zoho has already
              linked to Zoho CRM are matched to their CRM account exactly.
            </Reads>
          </Section>

          <Section id="zoho-crm" title="Zoho CRM">
            <Steps
              items={[
                'Create a Self Client and generate a code (above) with these scopes:',
              ]}
            />
            <Code>
              ZohoCRM.modules.accounts.READ,ZohoCRM.modules.cases.READ,ZohoCRM.settings.fields.READ
            </Code>
            <p className="text-[13px] text-slate-600">
              To let approved plays create Zoho CRM tasks, add{' '}
              <code className="font-mono">ZohoCRM.modules.tasks.CREATE</code> to
              the same list.
            </p>
            <Steps
              start={2}
              items={[
                'In Holdfast, open Connectors → Zoho CRM → Connect Zoho CRM, choose the region and paste the Client ID, Client Secret and code.',
                'Choose which Accounts date field records churn. Holdfast never guesses it.',
                'If the client has no such field: in Zoho CRM go to Setup → Customization → Modules and Fields → Accounts, add a Date field such as “Churned On”, and fill it in for accounts that left.',
                'Optional: tick “Create tasks for approved plays”.',
                'Click Sync now.',
              ]}
            />
            <Reads>
              Accounts (name, website, industry, created date and your churn
              field) and Cases as support tickets. If Cases aren’t available,
              the sync still works without tickets and says so on the card.
            </Reads>
          </Section>

          <Section id="stripe" title="Stripe">
            <Steps
              items={[
                'Sign in to the Stripe Dashboard as an administrator or developer. Switch on Test mode to try it first.',
                'Go to Developers → API keys → Create restricted key and name it “Holdfast”.',
                'Set Read on Customers, Subscriptions and Invoices. Leave everything else at None.',
                'Create the key and copy it. It starts with rk_live_ or rk_test_.',
                'In Holdfast, open Connectors → Stripe → Connect Stripe, paste the key and click Connect, then Sync now.',
              ]}
            />
            <Note>
              To revoke access, delete or roll the restricted key in Stripe
              under Developers → API keys.
            </Note>
          </Section>

          <Section id="hubspot" title="HubSpot">
            <Steps
              items={[
                'Sign in as a HubSpot super admin.',
                'Go to Development → Legacy apps → Create legacy app → Private. In older accounts it may appear as Settings → Integrations → Private apps.',
                'Name it “Holdfast”. On the Scopes tab tick crm.objects.companies.read, crm.schemas.companies.read and tickets. Add a task write scope only if plays should create tasks.',
                'Create the app, open the Auth tab, click Show token and copy it. It starts with pat-.',
                'In Holdfast, open Connectors → HubSpot → Connect HubSpot and paste the token.',
                'Choose which company date property records churn. If there is none, create a Date property such as “Churned on” for companies, under Settings → Properties.',
                'Click Sync now.',
              ]}
            />
            <Note>
              To revoke access, rotate the token on the app’s Auth tab or delete
              the app. HubSpot recommends rotating about every six months.
            </Note>
          </Section>

          <Section id="match" title="Match billing with a CRM">
            <Steps
              items={[
                'Connect one billing source and one CRM.',
                'On the billing card, choose “Match with …” under “Add CRM accounts and support tickets”.',
                'Click Sync now on the billing card. It reads both systems and shows how many customers were matched.',
              ]}
            />
            <p>
              Billing stays the record of who cancelled. Customers are matched
              to CRM accounts by Zoho’s own link when there is one, otherwise by
              company email domain. Personal mailboxes such as gmail.com never
              match, and unmatched customers keep billing data only.
            </p>
          </Section>

          <Section id="daily" title="Turn on daily checks">
            <Steps
              items={[
                'On the connection card, click Sync now, then Train from this data.',
                'Confirm what churn means (for example, cancelled within 90 days) and start training. It takes a few minutes.',
                'Make the trained model active from Results or Models.',
                'Open Results → Automatic check, choose this connection under “Live connections”, set it to Daily, tick “Run on a schedule” and save.',
              ]}
            />
            <p>
              Each day Holdfast pulls fresh data, re-scores every account,
              writes the brief and posts a summary to the Inbox, plus an email
              for anyone who turned the digest on in Settings. Retraining always
              waits for an admin’s approval.
            </p>
          </Section>

          <Section id="troubleshooting" title="Troubleshooting">
            <dl className="divide-y divide-slate-100 text-sm">
              {TROUBLE.map(([message, fix]) => (
                <div
                  key={message}
                  className="grid gap-1 py-3 sm:grid-cols-[1fr_1.3fr] sm:gap-6"
                >
                  <dt className="font-medium text-slate-900">“{message}”</dt>
                  <dd className="text-slate-600">{fix}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section id="revoke" title="Removing access">
            <Steps
              items={[
                'In Holdfast, click Disconnect on the connection card. Data already synced stays; daily checks on it pause.',
                'In the provider, revoke the key too: regenerate it in Razorpay, delete the Self Client in the Zoho API Console, delete or roll the Stripe key, or rotate or delete the HubSpot app.',
              ]}
            />
          </Section>
        </div>
      </div>
    </>
  );
}

const CONTENTS = [
  ['before', 'Before you start'],
  ['choose', 'Which sources to connect'],
  ['razorpay', 'Razorpay'],
  ['zoho', 'Zoho Self Client'],
  ['zoho-billing', 'Zoho Billing'],
  ['zoho-crm', 'Zoho CRM'],
  ['stripe', 'Stripe'],
  ['hubspot', 'HubSpot'],
  ['match', 'Match billing with a CRM'],
  ['daily', 'Daily checks'],
  ['troubleshooting', 'Troubleshooting'],
  ['revoke', 'Removing access'],
] as const;

const TROUBLE: [string, string][] = [
  [
    'The provider rejected the key. Check that it was copied whole.',
    'Copy the key again without spaces. Test and live keys are different; use the one that matches the account’s mode.',
  ],
  [
    'This key can’t read subscriptions (or customers, invoices, accounts, cases…)',
    'The key or Self Client is missing that permission. Add it and reconnect (for Zoho, generate a new code with the full scope list).',
  ],
  [
    'The one-time code is invalid or expired',
    'Zoho codes work once and only for a few minutes. Generate a new code and connect straight away.',
  ],
  [
    'Zoho didn’t recognise the client ID or secret, or the region is wrong',
    'Check the region matches where the Zoho account lives (India is zoho.in) and copy the ID and secret again from the Self Client.',
  ],
  [
    'This Zoho account has several Billing organisations',
    'Enter one of the listed organisation IDs in the optional field and connect again.',
  ],
  [
    'The provider returned no accounts.',
    'The account has no customers yet; a new test account is empty. Add a few test customers and subscriptions first.',
  ],
  [
    'The active model was trained on different data',
    'Train a model from this connection (Train from this data), make it active, then turn on the daily check.',
  ],
  [
    'Needs setup',
    'The server administrator runs pnpm setup:connectors once and restarts the API.',
  ],
];

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <Card title={title}>
        <div className="space-y-3 text-sm leading-relaxed text-slate-700">
          {children}
        </div>
      </Card>
    </section>
  );
}

function Steps({ items, start = 1 }: { items: string[]; start?: number }) {
  return (
    <ol className="space-y-2" start={start}>
      {items.map((text, i) => (
        <li key={text} className="flex gap-3">
          <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-field-700 font-mono text-[10px] font-bold text-stock">
            {start + i}
          </span>
          <span>{text}</span>
        </li>
      ))}
    </ol>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1.5 pl-5">
      {items.map((text) => (
        <li key={text}>{text}</li>
      ))}
    </ul>
  );
}

function Code({ children }: { children: ReactNode }) {
  return (
    <pre className="overflow-x-auto bg-tag-ink px-3 py-2.5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-all text-stock">
      {children}
    </pre>
  );
}

function Reads({ children }: { children: ReactNode }) {
  return (
    <p className="text-[13px] text-slate-600">
      <span className="font-semibold text-slate-800">
        What Holdfast reads:{' '}
      </span>
      {children}
    </p>
  );
}

function Note({ children }: { children: ReactNode }) {
  return (
    <p className="flex gap-2 bg-field-50 px-3 py-2 text-[13px] text-slate-700">
      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-field-700" />
      <span>{children}</span>
    </p>
  );
}
