import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRightLeft,
  Check,
  Crown,
  LogOut,
  Pencil,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import { authClient } from '../../lib/auth';
import { request } from '../api';
import { useAction, useIdentity, useResource } from '../queries';
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Select,
} from '../ui';
import { cn } from '../style';

interface Team {
  role: string;
  organization: { id: string; name: string; slug: string };
}
interface Member {
  id: string;
  role: string;
  user: { name: string; email: string };
}
interface Permissions {
  role: string;
  capabilities: { label: string; allowed: boolean }[];
  roles: Record<
    'admin' | 'member' | 'viewer',
    { label: string; allowed: boolean }[]
  >;
}

const ROLE_COPY: Record<string, string> = {
  owner: 'Created the team. Full control; can’t be removed.',
  admin: 'Full control, including members, approvals and guardrails.',
  member: 'Does the day-to-day work: data, models, scores and plays.',
  viewer: 'Reads everything and asks AI questions; changes nothing.',
};
const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

async function switchTo(organizationId: string | null) {
  await authClient.organization.setActive({ organizationId });
  window.location.assign('/app');
}

export function TeamPage() {
  const identity = useIdentity();
  const teams = useResource<{ organizations: Team[] }>(
    '/api/backend/organizations',
  );
  const permissions = useResource<Permissions>('/api/v1/workspace/permissions');
  if (identity.isPending) return <Loading label="Loading team" />;
  if (!identity.data) return <Notice error={identity.error} />;
  const me = identity.data;
  const active = teams.data?.organizations.find(
    (t) => t.organization.id === me.organization_id,
  );
  return (
    <div className="space-y-6">
      <PageHeader
        title={active ? active.organization.name : 'Bring your team'}
        description={
          active
            ? `A shared workspace. You’re ${me.role === 'admin' || me.role === 'owner' ? 'an' : 'a'} ${me.role}: ${ROLE_COPY[me.role].toLowerCase()}`
            : 'Work on retention together: one shared set of data, models, scores, plays and Nemotron briefs, with roles that decide who can change what.'
        }
      />
      <Notice error={teams.error || permissions.error} />
      {active ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-6">
            <Members
              organizationId={active.organization.id}
              canManage={me.can_manage}
            />
            {me.can_manage && <Rename team={active} />}
          </div>
          <div className="h-fit space-y-6">
            {permissions.data && <Access permissions={permissions.data} />}
            <Workspaces
              teams={teams.data?.organizations ?? []}
              activeId={me.organization_id}
            />
            {me.role !== 'owner' && <Leave team={active} />}
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-6">
            <CreateTeam />
            {permissions.data && <RoleTable permissions={permissions.data} />}
          </div>
          <div className="h-fit">
            <Workspaces
              teams={teams.data?.organizations ?? []}
              activeId={null}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function CreateTeam() {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function create() {
    setBusy(true);
    setError('');
    const slug =
      name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '')
        .slice(0, 40) || 'team';
    const created = await authClient.organization.create({
      name: name.trim(),
      slug: `${slug}-${Math.random().toString(36).slice(2, 6)}`,
    });
    if (created.error || !created.data) {
      setError(created.error?.message ?? 'Could not create the team.');
      setBusy(false);
      return;
    }
    await switchTo(created.data.id);
  }
  return (
    <Card title="Create a team workspace" icon={Users}>
      <ol className="mb-5 grid gap-3 sm:grid-cols-3">
        {[
          ['1', 'Create the team', 'You become its owner.'],
          ['2', 'Add your colleagues', 'By the email they signed up with.'],
          [
            '3',
            'Work from one place',
            'Shared scores, plays, results and briefs.',
          ],
        ].map(([n, title, body]) => (
          <li
            key={n}
            className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200/70"
          >
            <span className="grid size-6 place-items-center rounded-full bg-brand-600 text-xs font-bold text-white">
              {n}
            </span>
            <p className="mt-2 text-sm font-semibold text-slate-900">{title}</p>
            <p className="text-xs text-slate-500">{body}</p>
          </li>
        ))}
      </ol>
      <form
        className="flex flex-col gap-2 sm:flex-row"
        onSubmit={(e) => {
          e.preventDefault();
          void create();
        }}
      >
        <Input
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          placeholder="Acme Customer Success"
          aria-label="Team name"
        />
        <Button
          type="submit"
          variant="primary"
          disabled={name.trim().length < 2}
          loading={busy}
        >
          Create team
        </Button>
      </form>
      <Notice error={error} />
      <p className="mt-3 text-xs text-slate-500">
        Your personal workspace stays exactly as it is. Nothing is copied into
        the team.
      </p>
    </Card>
  );
}

function Members({
  organizationId,
  canManage,
}: {
  organizationId: string;
  canManage: boolean;
}) {
  const base = `/api/backend/organizations/${organizationId}/members`;
  const members = useResource<{ members: Member[] }>(base);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('member');
  const add = useAction<unknown, undefined>(() =>
    request(base, json('POST', { email: email.trim(), role })),
  );
  const change = useAction<unknown, { id: string; role: string }>((v) =>
    request(`${base}/${v.id}`, json('PATCH', { role: v.role })),
  );
  const remove = useAction<unknown, string>((id) =>
    request(`${base}/${id}`, { method: 'DELETE' }),
  );
  const list = members.data?.members ?? [];
  return (
    <Card
      title="Members"
      icon={Users}
      description={`${list.length} ${list.length === 1 ? 'person' : 'people'} in this workspace.`}
    >
      <Notice
        error={members.error || add.error || change.error || remove.error}
      />
      <ul className="-my-2 divide-y divide-slate-100">
        {list.map((m) => (
          <li key={m.id} className="flex flex-wrap items-center gap-3 py-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand-400 to-brand-700 text-xs font-semibold text-white">
              {m.user.name.slice(0, 1).toUpperCase()}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5 truncate text-sm font-medium text-slate-900">
                {m.user.name}
                {m.role === 'owner' && (
                  <Crown className="size-3.5 text-amber-500" />
                )}
              </span>
              <span className="block truncate text-xs text-slate-500">
                {m.user.email}
              </span>
            </span>
            {canManage && m.role !== 'owner' ? (
              <div className="w-32">
                <Select
                  value={m.role}
                  aria-label={`Role for ${m.user.email}`}
                  disabled={change.isPending}
                  onChange={(e) =>
                    change.mutate({ id: m.id, role: e.target.value })
                  }
                >
                  <option value="admin">Admin</option>
                  <option value="member">Member</option>
                  <option value="viewer">Viewer</option>
                </Select>
              </div>
            ) : (
              <Badge tone={m.role === 'viewer' ? 'neutral' : 'brand'}>
                {m.role}
              </Badge>
            )}
            {canManage && m.role !== 'owner' && (
              <Button
                size="sm"
                variant="ghost"
                icon={Trash2}
                aria-label={`Remove ${m.user.email}`}
                title="Remove from team"
                onClick={() => remove.mutate(m.id)}
              />
            )}
          </li>
        ))}
      </ul>
      {canManage ? (
        <form
          className="mt-5 rounded-xl bg-slate-50 p-4 ring-1 ring-slate-200/70"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined, { onSuccess: () => setEmail('') });
          }}
        >
          <p className="mb-3 text-sm font-semibold text-slate-900">
            Add a colleague
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              className="min-w-48 flex-1"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
              aria-label="Colleague email"
            />
            <div className="w-32">
              <Select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                aria-label="Role"
              >
                <option value="member">Member</option>
                <option value="viewer">Viewer</option>
                <option value="admin">Admin</option>
              </Select>
            </div>
            <Button
              type="submit"
              icon={UserPlus}
              disabled={!email.includes('@')}
              loading={add.isPending}
            >
              Add
            </Button>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {ROLE_COPY[role]} They need an account first; no email is sent.
          </p>
        </form>
      ) : (
        <p className="mt-4 text-xs text-slate-500">
          Ask an owner or admin to add colleagues or change roles.
        </p>
      )}
    </Card>
  );
}

function Access({ permissions }: { permissions: Permissions }) {
  return (
    <Card
      title="Your access"
      icon={ShieldCheck}
      description={`As ${permissions.role} in this workspace.`}
    >
      <ul className="space-y-2">
        {permissions.capabilities.map((c) => (
          <li key={c.label} className="flex items-start gap-2 text-sm">
            {c.allowed ? (
              <Check className="mt-0.5 size-4 shrink-0 text-brand-600" />
            ) : (
              <X className="mt-0.5 size-4 shrink-0 text-slate-300" />
            )}
            <span
              className={cn(c.allowed ? 'text-slate-700' : 'text-slate-400')}
            >
              {c.label}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function RoleTable({ permissions }: { permissions: Permissions }) {
  const roles = ['admin', 'member', 'viewer'] as const;
  return (
    <Card
      title="What each role can do"
      icon={ShieldCheck}
      description="Enforced by the server on every request, not just hidden in the interface."
    >
      <div className="-mx-5 -mb-5 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-y border-slate-100 bg-slate-50/60 text-left text-xs text-slate-500">
              <th className="px-5 py-2.5 font-medium">Can…</th>
              {roles.map((r) => (
                <th
                  key={r}
                  className="px-3 py-2.5 text-center font-medium capitalize"
                >
                  {r}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {permissions.roles.admin.map((row, i) => (
              <tr
                key={row.label}
                className="border-b border-slate-100 last:border-0"
              >
                <td className="px-5 py-2.5 text-slate-700">{row.label}</td>
                {roles.map((r) => (
                  <td key={r} className="px-3 py-2.5 text-center">
                    {permissions.roles[r][i].allowed ? (
                      <Check
                        className="mx-auto size-4 text-brand-600"
                        aria-label="Yes"
                      />
                    ) : (
                      <X
                        className="mx-auto size-4 text-slate-300"
                        aria-label="No"
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Workspaces({
  teams,
  activeId,
}: {
  teams: Team[];
  activeId: string | null;
}) {
  const [busy, setBusy] = useState('');
  const options = [
    { id: null, name: 'Personal workspace', role: 'owner' },
    ...teams.map((t) => ({
      id: t.organization.id,
      name: t.organization.name,
      role: t.role,
    })),
  ];
  return (
    <Card title="Your workspaces" icon={ArrowRightLeft}>
      <ul className="space-y-2">
        {options.map((o) => {
          const current = o.id === activeId;
          return (
            <li
              key={o.id ?? 'personal'}
              className={cn(
                'flex items-center gap-3 rounded-xl p-3 ring-1',
                current ? 'bg-brand-50/70 ring-brand-200' : 'ring-slate-200',
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-slate-900">
                  {o.name}
                </span>
                <span className="text-xs text-slate-500 capitalize">
                  {o.id ? o.role : 'Only you'}
                </span>
              </span>
              {current ? (
                <Badge tone="brand" dot>
                  Current
                </Badge>
              ) : (
                <Button
                  size="sm"
                  loading={busy === (o.id ?? 'personal')}
                  onClick={() => {
                    setBusy(o.id ?? 'personal');
                    void switchTo(o.id);
                  }}
                >
                  Switch
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Rename({ team }: { team: Team }) {
  const [name, setName] = useState(team.organization.name);
  const [state, setState] = useState<'' | 'saving' | 'saved'>('');
  const [error, setError] = useState('');
  async function save() {
    setState('saving');
    const result = await authClient.organization.update({
      organizationId: team.organization.id,
      data: { name: name.trim() },
    });
    if (result.error) {
      setError(result.error.message ?? 'Could not rename the team.');
      setState('');
      return;
    }
    setState('saved');
  }
  return (
    <Card title="Team settings" icon={Pencil}>
      <div className="flex flex-wrap items-end gap-2">
        <Field label="Team name" className="min-w-56 flex-1">
          <Input
            value={name}
            maxLength={80}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Button
          loading={state === 'saving'}
          disabled={
            name.trim().length < 2 || name.trim() === team.organization.name
          }
          onClick={() => void save()}
        >
          {state === 'saved' ? 'Saved' : 'Rename'}
        </Button>
      </div>
      <Notice error={error} />
      <p className="mt-3 text-xs text-slate-500">
        Privacy, data retention, usage and the audit log for this workspace are
        in{' '}
        <Link className="font-medium text-brand-700" to="/app/settings">
          Settings
        </Link>
        .
      </p>
    </Card>
  );
}

function Leave({ team }: { team: Team }) {
  const [confirm, setConfirm] = useState(false);
  const leave = useAction<unknown, undefined>(() =>
    request(`/api/backend/organizations/${team.organization.id}/members/me`, {
      method: 'DELETE',
    }),
  );
  return (
    <Card title="Leave this team">
      <p className="text-sm text-slate-600">
        You’ll lose access to its data and briefs. An admin can add you back.
      </p>
      <Notice error={leave.error} />
      <div className="mt-3 flex gap-2">
        {confirm ? (
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Stay
            </Button>
            <Button
              variant="danger"
              icon={LogOut}
              loading={leave.isPending}
              onClick={() =>
                leave.mutate(undefined, {
                  onSuccess: () => void switchTo(null),
                })
              }
            >
              Leave {team.organization.name}
            </Button>
          </>
        ) : (
          <Button
            variant="ghost"
            icon={LogOut}
            onClick={() => setConfirm(true)}
          >
            Leave team
          </Button>
        )}
      </div>
    </Card>
  );
}
