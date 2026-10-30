import { useState } from 'react';
import { FileClock, Gauge, Mail, ShieldCheck } from 'lucide-react';
import { post, request } from './api';
import { date, number } from './format';
import { useAction, useResource } from './queries';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Field,
  Input,
  Notice,
  Table,
  Td,
  Th,
  Tr,
} from './ui';

const json = (method: string, body: unknown) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

interface EmailState {
  configured: boolean;
  enabled: boolean;
  address: string | null;
  needs_address: boolean;
  recipients: number;
}

/** Each person turns the daily email on for themselves; it goes to their own account address. */
export function EmailDigestCard() {
  const state = useResource<EmailState>('/api/v1/email/subscription');
  const [address, setAddress] = useState('');
  const save = useAction<EmailState, boolean>((enabled) =>
    request(
      '/api/v1/email/subscription',
      json('PUT', { enabled, address: address.trim() || null }),
    ),
  );
  const test = useAction<{ sent_to: string }, undefined>(() =>
    post('/api/v1/email/test', {}),
  );
  const data = state.data;
  return (
    <Card
      title="Email digest"
      icon={Mail}
      description="After each automatic check, get the brief headline, the accounts to call first and the recommended play. Customer names and IDs stay in the app."
      action={
        data?.enabled ? (
          <Badge tone="success" dot>
            On
          </Badge>
        ) : (
          <Badge>Off</Badge>
        )
      }
    >
      {!data ? (
        <Notice error={state.error} />
      ) : !data.configured ? (
        <p className="text-sm text-slate-600">
          Email isn’t set up on this server yet. An admin adds a Resend API key
          and a sender address to the API environment.
        </p>
      ) : (
        <div className="space-y-3">
          {data.needs_address && !data.enabled && (
            <Field label="Send to">
              <Input
                type="email"
                autoComplete="email"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="you@company.com"
              />
            </Field>
          )}
          <Checkbox
            checked={data.enabled}
            disabled={save.isPending}
            onChange={(on) => save.mutate(on)}
            description={
              data.enabled
                ? `Going to ${data.address}. Turn it off here at any time; every email links back to this setting.`
                : 'Goes to your own account address, one email per check.'
            }
          >
            Email me after each check
          </Checkbox>
          {data.enabled && (
            <Button
              size="sm"
              loading={test.isPending}
              onClick={() => test.mutate(undefined)}
            >
              Send me a test email
            </Button>
          )}
          {test.data && (
            <p className="text-xs text-slate-600">
              Test sent to {test.data.sent_to}.
            </p>
          )}
          <Notice error={save.error || test.error} />
        </div>
      )}
    </Card>
  );
}

export function PrivacyCard({ canManage }: { canManage: boolean }) {
  const policy = useResource<{
    blocked_columns: string[];
    default_patterns: boolean;
  }>('/api/v1/privacy');
  const [draft, setDraft] = useState<string | null>(null);
  const [patterns, setPatterns] = useState<boolean | null>(null);
  const save = useAction<unknown, undefined>(() =>
    request(
      '/api/v1/privacy',
      json('PUT', {
        blocked_columns: (
          draft ??
          policy.data?.blocked_columns.join(', ') ??
          ''
        )
          .split(',')
          .map((c) => c.trim())
          .filter(Boolean),
        default_patterns: patterns ?? policy.data?.default_patterns ?? true,
      }),
    ),
  );
  if (!policy.data) return <Notice error={policy.error} />;
  return (
    <Card
      title="Privacy: never send to AI"
      icon={ShieldCheck}
      description="Columns listed here still train models on this server, but their values never reach the AI provider, investigations or outreach drafts."
    >
      <Field
        label="Column names"
        hint="Comma-separated, exactly as in your files."
      >
        <Input
          value={draft ?? policy.data.blocked_columns.join(', ')}
          disabled={!canManage}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="e.g. contact_email, account_owner"
        />
      </Field>
      <div className="mt-3">
        <Checkbox
          checked={patterns ?? policy.data.default_patterns}
          disabled={!canManage}
          onChange={setPatterns}
          description="Names that look like emails, phone numbers, addresses, people’s names, age, gender, health and similar."
        >
          Also withhold likely personal or sensitive columns
        </Checkbox>
      </div>
      <Notice error={save.error} />
      {canManage && (
        <Button
          className="mt-4"
          loading={save.isPending}
          onClick={() => save.mutate(undefined)}
        >
          Save policy
        </Button>
      )}
    </Card>
  );
}

export function RetentionCard({ canManage }: { canManage: boolean }) {
  const policy = useResource<{
    days: number | null;
    last_applied_at: string | null;
  }>('/api/v1/retention-policy');
  const [days, setDays] = useState<string | null>(null);
  const save = useAction<unknown, undefined>(() =>
    request(
      '/api/v1/retention-policy',
      json('PUT', { days: Number(days) || null }),
    ),
  );
  const apply = useAction<{ removed: Record<string, number> }, undefined>(() =>
    post('/api/v1/retention-policy/apply', {}),
  );
  if (!policy.data) return <Notice error={policy.error} />;
  const value = days ?? String(policy.data.days ?? '');
  return (
    <Card
      title="Data retention"
      icon={FileClock}
      description="Delete old scores, analyses, AI conversations, traces and unused uploads automatically once a day. Models, the datasets they need and the audit log are kept."
    >
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Keep for (days)" className="w-40">
          <Input
            type="number"
            min={7}
            max={3650}
            value={value}
            disabled={!canManage}
            placeholder="Forever"
            onChange={(e) => setDays(e.target.value)}
          />
        </Field>
        {canManage && (
          <>
            <Button
              loading={save.isPending}
              onClick={() => save.mutate(undefined)}
            >
              Save
            </Button>
            <Button
              variant="ghost"
              disabled={!policy.data.days}
              loading={apply.isPending}
              onClick={() => apply.mutate(undefined)}
            >
              Clean up now
            </Button>
          </>
        )}
      </div>
      <Notice error={save.error || apply.error} />
      <p className="mt-3 text-xs text-slate-500">
        {apply.data
          ? `Removed ${Object.entries(apply.data.removed)
              .map(([k, v]) => `${v} ${k}`)
              .join(', ')}.`
          : policy.data.last_applied_at
            ? `Last cleaned ${date(policy.data.last_applied_at)}.`
            : 'Nothing is deleted until you set a period.'}
      </p>
    </Card>
  );
}

export function UsageCard() {
  const usage = useResource<{
    month: string;
    ai_operations: number;
    ai_tokens: { input: number; output: number };
    ai_cost_usd: number | null;
    jobs: Record<string, number>;
    accounts_scored: number;
  }>('/api/v1/usage');
  if (!usage.data) return <Notice error={usage.error} />;
  const u = usage.data;
  const jobs = Object.values(u.jobs).reduce((a, b) => a + b, 0);
  return (
    <Card title={`Usage · ${u.month}`} icon={Gauge}>
      <div className="grid grid-cols-2 gap-3">
        {[
          ['AI requests', number(u.ai_operations)],
          ['AI tokens', number(u.ai_tokens.input + u.ai_tokens.output)],
          ['Background jobs', number(jobs)],
          ['Accounts scored', number(u.accounts_scored)],
        ].map(([label, value]) => (
          <div
            key={label}
            className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70"
          >
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-lg font-semibold tabular">{value}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        {u.ai_cost_usd != null
          ? `AI cost $${u.ai_cost_usd.toFixed(2)} at your configured prices.`
          : 'AI cost appears once model prices are configured (CI_MODEL_PRICES).'}
      </p>
    </Card>
  );
}

export function AuditCard() {
  const events = useResource<
    {
      id: string;
      at: string;
      actor: string;
      role: string;
      action: string;
      target: string | null;
    }[]
  >('/api/v1/audit');
  return (
    <Card
      className="mt-6"
      title="Audit log"
      description="Every change in this workspace and every automated action. Request contents are never stored."
    >
      <Notice error={events.error} />
      {events.data?.length === 0 && (
        <p className="text-sm text-slate-500">No changes recorded yet.</p>
      )}
      {events.data && events.data.length > 0 && (
        <Table>
          <thead>
            <tr>
              <Th>When</Th>
              <Th>Who</Th>
              <Th>What</Th>
            </tr>
          </thead>
          <tbody>
            {events.data.slice(0, 50).map((e) => (
              <Tr key={e.id}>
                <Td className="whitespace-nowrap text-slate-500">
                  {date(e.at)}
                </Td>
                <Td className="whitespace-nowrap">
                  {e.actor.startsWith('system:')
                    ? e.actor.replace('system:', 'Automatic · ')
                    : e.actor === 'local'
                      ? 'You'
                      : e.actor.slice(0, 10)}
                  {e.role !== 'system' && e.role !== 'owner' && (
                    <Badge className="ml-2">{e.role}</Badge>
                  )}
                </Td>
                <Td mono className="text-xs">
                  {e.action}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
