import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BookOpen } from 'lucide-react';
import { post, request } from './api';
import { date, number, percent } from './format';
import { useAction, useIdentity, useResource } from './queries';
import {
  Alert,
  Badge,
  Button,
  ButtonLink,
  Checkbox,
  Field,
  Input,
  Loading,
  Notice,
  Select,
} from './ui';
import {
  GUIDE,
  PROVIDERS,
  ZOHO_REGIONS,
  type Connection,
  type Provider,
} from './connectors-data';

const COMING = [
  ['Salesforce', 'Accounts, opportunities and cases.'],
  ['Freshdesk and Freshsales', 'Support tickets and CRM accounts.'],
  ['Chargebee', 'Subscriptions and invoices.'],
  ['Intercom and Zendesk', 'Support conversations and their topics.'],
] as const;

/** Billing and CRM connectors, grouped by what they contribute. */
export function Connectors() {
  const list = useResource<{ enabled: boolean; connections: Connection[] }>(
    '/api/v1/connections',
  );
  const canManage = useIdentity().data?.can_manage ?? false;
  const all = list.data?.connections ?? [];
  if (list.isLoading) return <Loading label="Loading connections" />;
  const group = (title: string, hint: string, providers: Provider[]) => (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <p className="text-xs text-slate-500">{hint}</p>
      </div>
      {providers.map((provider) => {
        const mine = all.filter((c) => c.provider === provider);
        if (!list.data?.enabled)
          return (
            <ConnectorShell
              key={provider}
              name={PROVIDERS[provider].name}
              badge={<Badge>Needs setup</Badge>}
            >
              {canManage
                ? 'Connectors are switched off on this server. Run pnpm setup:connectors, then restart the API.'
                : 'Ask a workspace admin to finish connector setup.'}
            </ConnectorShell>
          );
        return mine.length ? (
          mine.map((c) => (
            <ConnectionCard key={c.id} c={c} all={all} canManage={canManage} />
          ))
        ) : (
          <ConnectForm
            key={provider}
            provider={provider}
            canManage={canManage}
          />
        );
      })}
    </div>
  );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-field-50 px-4 py-3 ring-1 ring-field-100">
        <p className="text-[13px] text-slate-700">
          Connecting a client’s account for the first time? The setup guide
          walks through each provider step by step.
        </p>
        <ButtonLink size="sm" icon={BookOpen} to={GUIDE}>
          Setup guide
        </ButtonLink>
      </div>
      {group(
        'Billing',
        'Who pays, how much, failed payments and who cancelled. Connect one.',
        ['razorpay', 'zoho_billing', 'stripe'],
      )}
      {group(
        'CRM and support',
        'Company details and support tickets. Optional; match it with billing for richer signals.',
        ['zoho_crm', 'hubspot'],
      )}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-900">Coming soon</h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {COMING.map(([name, description]) => (
            <ConnectorShell
              key={name}
              name={name}
              badge={<Badge tone="info">Coming soon</Badge>}
            >
              {description}
            </ConnectorShell>
          ))}
        </div>
        <p className="text-xs text-slate-500">
          For anything not connected yet, export the tables as CSV and upload
          them as a bundle above.
        </p>
      </div>
    </div>
  );
}

function ConnectorShell({
  name,
  badge,
  children,
}: {
  name: string;
  badge: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start gap-3 rounded-2xl bg-white p-4 shadow-card ring-1 ring-slate-200/80">
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-sm font-semibold text-slate-500">
        {name[0]}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-900">
          {name}
          {badge}
        </p>
        <div className="mt-0.5 text-xs text-slate-500">{children}</div>
      </div>
    </div>
  );
}

function GuideLink({ provider }: { provider: Provider }) {
  return (
    <Link
      to={`${GUIDE}#${PROVIDERS[provider].anchor}`}
      className="inline-flex items-center gap-1 font-medium text-brand-700 hover:text-brand-800"
    >
      Step-by-step guide <ArrowRight className="size-3" />
    </Link>
  );
}

function ConnectForm({
  provider,
  canManage,
}: {
  provider: Provider;
  canManage: boolean;
}) {
  const info = PROVIDERS[provider];
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState(info.label);
  const [values, setValues] = useState<Record<string, string>>({
    region: 'in',
  });
  const set = (key: string, value: string) =>
    setValues((v) => ({ ...v, [key]: value }));
  const connect = useAction<Connection, undefined>(() =>
    post(
      '/api/v1/connections',
      info.single
        ? { provider, label, secret: values.secret?.trim() }
        : {
            provider,
            label,
            fields: Object.fromEntries(
              Object.entries(values)
                .map(([k, v]) => [k, v.trim()])
                .filter(([, v]) => v),
            ),
          },
    ),
  );
  const needed = info.single
    ? ['secret']
    : (info.fields ?? []).filter((f) => !f.optional).map((f) => f.key);
  const ready = label.trim() && needed.every((k) => values[k]?.trim());
  return (
    <ConnectorShell
      name={info.name}
      badge={<Badge tone="success">Available</Badge>}
    >
      <p>{info.about}</p>
      {info.note && <p className="mt-1 text-slate-600">{info.note}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-3">
        {canManage && !open && (
          <Button size="sm" variant="primary" onClick={() => setOpen(true)}>
            Connect {info.name}
          </Button>
        )}
        {!canManage && <span>A workspace admin can connect {info.name}.</span>}
        <GuideLink provider={provider} />
      </div>
      {canManage && open && (
        <form
          className="mt-3 grid gap-3 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            connect.mutate(undefined, {
              // Codes and secrets never stay in the page after use.
              onSuccess: () => setValues({ region: 'in' }),
            });
          }}
        >
          <Field label="Name">
            <Input
              value={label}
              maxLength={80}
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
          {info.single ? (
            <Field label={info.single.label}>
              <Input
                type="password"
                autoComplete="off"
                spellCheck={false}
                placeholder={info.single.placeholder}
                value={values.secret ?? ''}
                onChange={(e) => set('secret', e.target.value)}
              />
            </Field>
          ) : (
            info.fields?.map((f) => (
              <Field
                key={f.key}
                label={f.optional ? `${f.label} (optional)` : f.label}
              >
                {f.region ? (
                  <Select
                    value={values.region ?? 'in'}
                    onChange={(e) => set('region', e.target.value)}
                  >
                    {ZOHO_REGIONS.map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </Select>
                ) : (
                  <Input
                    type={f.secret ? 'password' : 'text'}
                    autoComplete="off"
                    spellCheck={false}
                    placeholder={f.placeholder}
                    value={values[f.key] ?? ''}
                    onChange={(e) => set(f.key, e.target.value)}
                  />
                )}
              </Field>
            ))
          )}
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <Button
              type="submit"
              variant="primary"
              disabled={!ready}
              loading={connect.isPending}
            >
              Connect
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
          </div>
          <div className="sm:col-span-2">
            <Notice error={connect.error} />
            <p className="mt-1">
              Holdfast checks the credentials with one read, then stores them
              encrypted. They are never shown again.
            </p>
          </div>
        </form>
      )}
    </ConnectorShell>
  );
}

function ConnectionCard({
  c,
  all,
  canManage,
}: {
  c: Connection;
  all: Connection[];
  canManage: boolean;
}) {
  const info = PROVIDERS[c.provider];
  const sync = useAction<unknown, undefined>(() =>
    post(`/api/v1/connections/${c.id}/sync`, {}),
  );
  const remove = useAction<unknown, undefined>(() =>
    request(`/api/v1/connections/${c.id}`, { method: 'DELETE' }),
  );
  const counts = c.last_counts;
  const summary =
    counts?.accounts == null
      ? null
      : info.role === 'billing'
        ? `${number(counts.accounts)} customers, ${number(counts.invoices ?? 0)} invoices, ${number(counts.cancelled ?? 0)} cancelled`
        : `${number(counts.accounts)} accounts, ${number(counts.tickets ?? 0)} tickets, ${number(counts.cancelled ?? 0)} churned`;
  const partner = all.find((x) => x.id === c.enrich_connection_id);
  return (
    <ConnectorShell
      name={info.name}
      badge={
        c.last_error ? (
          <Badge tone="danger">Sync failed</Badge>
        ) : (
          <Badge tone="success" dot>
            Connected
          </Badge>
        )
      }
    >
      <p className="text-slate-700">
        {c.label}
        {' · '}
        {c.last_synced_at
          ? `Last synced ${date(c.last_synced_at)}`
          : 'Not synced yet'}
        {summary && ` · ${summary}`}
      </p>
      {c.last_match && partner && (
        <p className="mt-1">
          Matched {number(c.last_match.matched)} of{' '}
          {number(c.last_match.billing_accounts)} customers (
          {percent(c.last_match.rate)}) to {PROVIDERS[partner.provider].name}{' '}
          accounts
          {c.last_match.matched_by_crm_id
            ? `, ${number(c.last_match.matched_by_crm_id)} through Zoho’s own CRM link and the rest by email domain`
            : ' by email domain'}
          . Unmatched customers keep billing data only.
        </p>
      )}
      {c.last_notes.map((note) => (
        <Alert key={note} tone="info" className="mt-2">
          {note}
        </Alert>
      ))}
      {c.last_error && (
        <Alert tone="danger" className="mt-2">
          {c.last_error}
        </Alert>
      )}
      {canManage && info.role === 'crm' && <CrmSettings c={c} />}
      {canManage && info.role === 'billing' && (
        <MatchWithCrm c={c} crms={all.filter((x) => x.role === 'crm')} />
      )}
      <Notice error={sync.error || remove.error} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {canManage && (
          <Button
            size="sm"
            loading={sync.isPending}
            onClick={() => sync.mutate(undefined)}
          >
            Sync now
          </Button>
        )}
        {c.last_source_id && (
          <ButtonLink
            size="sm"
            variant="primary"
            to={`/app/sources/${c.last_source_id}`}
          >
            Train from this data <ArrowRight className="size-3.5" />
          </ButtonLink>
        )}
        {canManage && (
          <Button
            size="sm"
            variant="ghost"
            loading={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `Disconnect ${c.label}? Synced data stays; daily checks on it pause. Also revoke the key in ${info.name}.`,
                )
              )
                remove.mutate(undefined);
            }}
          >
            Disconnect
          </Button>
        )}
        <GuideLink provider={c.provider} />
      </div>
    </ConnectorShell>
  );
}

const settingsOf = (id: string) => (body: Record<string, unknown>) =>
  request<Connection>(`/api/v1/connections/${id}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

/** A CRM has no standard churn field, so an admin picks the date that records it. */
function CrmSettings({ c }: { c: Connection }) {
  const name = PROVIDERS[c.provider].name;
  const properties = useResource<{ name: string; label: string }[]>(
    `/api/v1/connections/${c.id}/properties`,
  );
  const save = useAction(settingsOf(c.id));
  const write = useAction<Connection, boolean>((enabled) =>
    request(`/api/v1/connections/${c.id}/write`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, confirm: enabled }),
    }),
  );
  return (
    <div className="mt-3 space-y-3">
      <Field
        label={
          c.provider === 'zoho_crm'
            ? 'Which Accounts date field records churn?'
            : 'Which company date records churn?'
        }
        hint={`Holdfast never guesses churn. Without this, ${name} data can be scored but not trained on.`}
      >
        <Select
          value={c.churn_property ?? ''}
          disabled={properties.isLoading || save.isPending}
          onChange={(e) =>
            save.mutate({ churn_property: e.target.value || null })
          }
        >
          <option value="">Not set</option>
          {properties.data?.map((p) => (
            <option key={p.name} value={p.name}>
              {p.label}
            </option>
          ))}
        </Select>
      </Field>
      <Checkbox
        checked={c.write_enabled}
        disabled={write.isPending}
        onChange={(on) => {
          if (
            !on ||
            window.confirm(
              `Allow approved plays to create tasks in ${name}? Nothing is written until a play is approved.`,
            )
          )
            write.mutate(on);
        }}
        description={`Approved plays become ${name} tasks on the matching accounts. The credential needs task-create permission.`}
      >
        Create tasks for approved plays
      </Checkbox>
      <Notice error={properties.error || save.error || write.error} />
    </div>
  );
}

function MatchWithCrm({ c, crms }: { c: Connection; crms: Connection[] }) {
  const save = useAction(settingsOf(c.id));
  if (!crms.length) return null;
  return (
    <div className="mt-3">
      <Field
        label="Add CRM accounts and support tickets"
        hint="Matched on each sync by Zoho’s own CRM link when there is one, otherwise by email domain; personal mailboxes never match."
      >
        <Select
          value={c.enrich_connection_id ?? ''}
          disabled={save.isPending}
          onChange={(e) =>
            save.mutate({ enrich_connection_id: e.target.value || null })
          }
        >
          <option value="">Billing only</option>
          {crms.map((h) => (
            <option key={h.id} value={h.id}>
              Match with {h.label} ({PROVIDERS[h.provider].name})
            </option>
          ))}
        </Select>
      </Field>
      <Notice error={save.error} />
    </div>
  );
}
