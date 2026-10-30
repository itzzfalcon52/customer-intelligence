import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
} from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { Command } from 'cmdk';
import {
  Activity,
  Inbox as InboxIcon,
  Users,
  BrainCircuit,
  Crosshair,
  HeartHandshake,
  Target,
  BookOpen,
  LifeBuoy,
  Radar,
  BarChart3,
  Check,
  ChevronRight,
  Database,
  FlaskConical,
  LayoutDashboard,
  Loader2,
  LogOut,
  Menu,
  MessagesSquare,
  Plug,
  Search,
  Settings2,
  Sparkles,
  X,
  type LucideIcon,
} from 'lucide-react';
import { authClient } from '../lib/auth';
import { Logo } from '../components/Logo';
import {
  WorkspaceContext,
  useJobs,
  useIdentity,
  usePendingActions,
  useResource,
} from './queries';
import { useWorkspaceStore } from './store';
import { Kbd, Loading, Notice } from './ui';
import { cn } from './style';
import {
  JOB_LABEL,
  jobResultLink,
  useDemoPipeline,
  useWorkflow,
} from './workflow';

const Copilot = lazy(() =>
  import('./pages/Copilot').then((m) => ({ default: m.Copilot })),
);

export function WorkspaceRoot() {
  const session = authClient.useSession();
  const client = useQueryClient();
  const priorUser = useRef<string | undefined>(undefined);
  const activeOrg = (
    session.data?.session as
      { activeOrganizationId?: string | null } | undefined
  )?.activeOrganizationId;
  // Query caches are keyed by user and workspace, so switching never shows stale data.
  const userId = session.data
    ? `${session.data.user.id}:${activeOrg ?? 'personal'}`
    : undefined;
  useEffect(() => {
    if (priorUser.current && priorUser.current !== userId) {
      void client.cancelQueries();
      client.clear();
    }
    if (priorUser.current !== userId) useWorkspaceStore.getState().reset();
    priorUser.current = userId;
  }, [client, userId]);
  if (session.isPending)
    return (
      <div className="grid min-h-screen place-items-center bg-stock">
        <Loader2 className="size-6 animate-spin text-brand-600" />
      </div>
    );
  if (session.error)
    return (
      <div className="grid min-h-screen place-items-center bg-stock p-6">
        <div className="max-w-sm space-y-4 text-center">
          <Notice error="The account service is unavailable. Check that pnpm dev is running." />
          <button
            className="text-sm font-medium text-brand-700"
            onClick={() => void session.refetch()}
          >
            Try again
          </button>
        </div>
      </div>
    );
  if (!session.data) return <Navigate to="/login" replace />;
  return (
    <WorkspaceContext.Provider value={userId!}>
      <Shell
        key={userId}
        name={session.data.user.name}
        email={session.data.user.email}
      />
    </WorkspaceContext.Provider>
  );
}

// The everyday path for a customer-success team; the last entry lists extra active prefixes.
const MAIN: [string, string, LucideIcon, string[]][] = [
  ['/app/scores', 'At-risk accounts', Target, []],
  ['/app/plays', 'Retention plays', HeartHandshake, []],
  ['/app/monitoring', 'Results', Radar, []],
  ['/app/ask', 'Ask AI', MessagesSquare, []],
  ['/app/inbox', 'Inbox', InboxIcon, []],
  ['/app/data', 'Data', Database, ['/app/sources']],
  ['/app/team', 'Team', Users, []],
];
const ADVANCED: [string, string, LucideIcon][] = [
  ['/app/churn', 'Churn definition', Crosshair],
  ['/app/models', 'Models', BrainCircuit],
  ['/app/investigate', 'Investigations', FlaskConical],
  ['/app/analyses', 'Analyses', BarChart3],
  ['/app/playbooks', 'Playbooks', BookOpen],
  ['/app/sources', 'Connectors & sources', Plug],
  ['/app/guides/connectors', 'Connector guide', LifeBuoy],
  ['/app/jobs', 'Jobs', Activity],
  ['/app/settings', 'Settings', Settings2],
];
const TITLES: [RegExp, string][] = [
  [/^\/app\/?$/, 'Home'],
  [/^\/app\/data/, 'Customer data'],
  [/^\/app\/churn/, 'Churn definition'],
  [/^\/app\/models/, 'Models'],
  [/^\/app\/scores/, 'At-risk accounts'],
  [/^\/app\/plays/, 'Retention plays'],
  [/^\/app\/investigate/, 'Investigations'],
  [/^\/app\/analyses/, 'Analyses'],
  [/^\/app\/ask/, 'Ask AI'],
  [/^\/app\/inbox/, 'Inbox'],
  [/^\/app\/monitoring/, 'Results'],
  [/^\/app\/jobs/, 'Jobs'],
  [/^\/app\/sources/, 'Data sources'],
  [/^\/app\/guides\/connectors/, 'Connector guide'],
  [/^\/app\/playbooks/, 'Playbooks'],
  [/^\/app\/settings/, 'Settings'],
  [/^\/app\/team/, 'Team'],
];

function navClass(active: boolean) {
  return cn(
    'group relative flex h-9 items-center gap-3 px-2.5 text-[14px] font-[580] transition-colors',
    active
      ? 'bg-field-800 text-stock before:absolute before:inset-y-1.5 before:-left-3 before:w-1.5 before:bg-tag-red'
      : 'text-field-200 hover:bg-field-800/60 hover:text-stock',
  );
}

function Sidebar({
  onNavigate,
  name,
  email,
}: {
  onNavigate: () => void;
  name: string;
  email: string;
}) {
  const { stages, completed, ready } = useWorkflow();
  const { pathname } = useLocation();
  const advancedOpen = useWorkspaceStore((s) => s.advancedOpen);
  const setAdvanced = useWorkspaceStore((s) => s.setAdvanced);
  const navigate = useNavigate();
  const client = useQueryClient();
  const jobs = useJobs();
  const busy =
    jobs.data?.filter((j) => ['queued', 'running'].includes(j.state)).length ??
    0;
  const approvals = usePendingActions().data?.length ?? 0;
  async function logout() {
    const result = await authClient.signOut();
    if (result.error) return;
    await client.cancelQueries();
    client.clear();
    useWorkspaceStore.getState().reset();
    navigate('/login', { replace: true });
  }
  return (
    <div className="flex h-full flex-col bg-field-900 text-field-100 [&_:focus-visible]:outline-tag-amber">
      <div className="flex h-16 items-center px-5">
        <Link to="/app" onClick={onNavigate}>
          <Logo dark />
        </Link>
      </div>
      <nav
        className="flex-1 space-y-6 overflow-y-auto px-3 pb-4"
        aria-label="Workspace"
      >
        <NavLink
          to="/app"
          end
          onClick={onNavigate}
          className={({ isActive }) => navClass(isActive)}
        >
          <LayoutDashboard className="size-4" />
          Home
        </NavLink>
        {!ready && (
          <div>
            <div className="mb-2 flex items-center justify-between px-2.5">
              <span className="text-[11px] font-[720] tracking-[0.08em] text-field-300 uppercase">
                Get set up
              </span>
              <span className="font-mono text-[11px] text-field-300">
                {Math.min(completed, 4)}/4
              </span>
            </div>
            <div className="mb-3 px-2.5">
              <div className="h-1 overflow-hidden bg-white/10">
                <motion.div
                  className="h-full bg-tag-amber"
                  initial={{ width: 0 }}
                  animate={{ width: `${(Math.min(completed, 4) / 4) * 100}%` }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                />
              </div>
            </div>
            <ol className="relative space-y-0.5">
              {stages
                .filter((s) => s.key !== 'act')
                .map((s) => (
                  <li key={s.key}>
                    <NavLink
                      to={s.status === 'todo' ? s.home : s.to}
                      onClick={onNavigate}
                      className={navClass(pathname.startsWith(s.home))}
                    >
                      <span
                        className={cn(
                          'grid size-5 shrink-0 place-items-center rounded-full font-mono text-[10px] font-bold',
                          s.status === 'done' && 'bg-field-300 text-field-950',
                          s.status === 'running' && 'bg-tag-amber text-tag-ink',
                          s.status === 'active' &&
                            'bg-stock text-field-950 ring-2 ring-tag-amber',
                          s.status === 'todo' &&
                            'text-field-300 ring-1 ring-field-600',
                        )}
                      >
                        {s.status === 'done' ? (
                          <Check className="size-3" strokeWidth={3.5} />
                        ) : s.status === 'running' ? (
                          <Loader2 className="size-3 animate-spin" />
                        ) : (
                          s.step
                        )}
                      </span>
                      <span className="flex-1 truncate">{s.title}</span>
                      {s.status === 'active' && (
                        <span className="bg-tag-amber px-1.5 py-0.5 text-[10px] font-[720] text-tag-ink">
                          Next
                        </span>
                      )}
                    </NavLink>
                  </li>
                ))}
            </ol>
          </div>
        )}
        <div className="space-y-0.5">
          {MAIN.map(([to, label, Icon, also]) => (
            <NavLink
              key={to}
              to={to}
              onClick={onNavigate}
              className={({ isActive }) =>
                navClass(
                  isActive ||
                    also.some((prefix) => pathname.startsWith(prefix)),
                )
              }
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              {to === '/app/inbox' && approvals > 0 && (
                <span className="bg-tag-amber px-1.5 font-mono text-[11px] font-bold text-tag-ink">
                  {approvals}
                </span>
              )}
            </NavLink>
          ))}
        </div>
        <div>
          <button
            onClick={() => setAdvanced(!advancedOpen)}
            aria-expanded={advancedOpen}
            className="flex w-full cursor-pointer items-center justify-between px-2.5 py-1 text-[11px] font-[720] tracking-[0.08em] text-field-300 uppercase transition hover:text-stock"
          >
            Advanced
            <span className="flex items-center gap-1.5 normal-case">
              {busy > 0 && !advancedOpen && (
                <Loader2 className="size-3 animate-spin text-tag-amber" />
              )}
              <ChevronRight
                className={cn(
                  'size-3.5 transition-transform',
                  advancedOpen && 'rotate-90',
                )}
              />
            </span>
          </button>
          <AnimatePresence initial={false}>
            {advancedOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2 }}
                className="mt-1 space-y-0.5 overflow-hidden"
              >
                {ADVANCED.map(([to, label, Icon]) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={onNavigate}
                    className={({ isActive }) => navClass(isActive)}
                  >
                    <Icon className="size-4" />
                    <span className="flex-1">{label}</span>
                    {to === '/app/jobs' && busy > 0 && (
                      <span className="flex items-center gap-1 bg-tag-amber/20 px-1.5 text-[11px] font-semibold text-tag-amber">
                        <Loader2 className="size-3 animate-spin" />
                        {busy}
                      </span>
                    )}
                  </NavLink>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </nav>
      <div className="border-t border-white/10 p-3">
        <div className="flex items-center gap-3 rounded-lg px-2 py-2">
          <span className="grid size-8 shrink-0 place-items-center bg-stock font-mono text-xs font-bold text-field-900 [clip-path:polygon(18%_0,82%_0,100%_14%,100%_100%,0_100%,0_14%)]">
            {name.slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium text-white">
              {name}
            </p>
            <p className="truncate text-[11px] text-field-300">{email}</p>
          </div>
          <button
            onClick={() => void logout()}
            className="cursor-pointer p-1.5 text-field-300 transition hover:bg-white/10 hover:text-stock"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Watches jobs and raises a toast when background work finishes. */
function useJobToasts() {
  const jobs = useJobs();
  const toast = useWorkspaceStore((s) => s.toast);
  const seen = useRef<Map<string, string>>(new Map());
  useEffect(() => {
    for (const job of jobs.data ?? []) {
      const before = seen.current.get(job.id);
      if (
        before &&
        ['queued', 'running'].includes(before) &&
        ['succeeded', 'failed'].includes(job.state)
      )
        toast({
          tone: job.state === 'succeeded' ? 'success' : 'danger',
          title: `${JOB_LABEL[job.kind] ?? job.kind} ${job.state === 'succeeded' ? 'finished' : 'failed'}`,
          body:
            job.state === 'succeeded'
              ? 'Open the result to continue.'
              : (job.error ?? undefined),
          to: job.state === 'succeeded' ? jobResultLink(job) : '/app/jobs',
        });
      seen.current.set(job.id, job.state);
    }
  }, [jobs.data, toast]);
}

function Toasts() {
  const toasts = useWorkspaceStore((s) => s.toasts);
  const dismiss = useWorkspaceStore((s) => s.dismiss);
  useEffect(() => {
    if (!toasts.length) return;
    const timer = setTimeout(() => dismiss(toasts[0].id), 7000);
    return () => clearTimeout(timer);
  }, [toasts, dismiss]);
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-80 flex-col gap-2">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            layout
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40 }}
            className="pointer-events-auto flex gap-3 rounded-xl bg-white p-4 shadow-pop ring-1 ring-slate-200"
            role="status"
          >
            <span
              className={cn(
                'mt-0.5 size-2 shrink-0 rounded-full',
                t.tone === 'success'
                  ? 'bg-emerald-500'
                  : t.tone === 'danger'
                    ? 'bg-rose-500'
                    : 'bg-field-500',
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-slate-900">{t.title}</p>
              {t.body && (
                <p className="mt-0.5 line-clamp-2 text-[13px] text-slate-500">
                  {t.body}
                </p>
              )}
              {t.to && (
                <Link
                  to={t.to}
                  onClick={() => dismiss(t.id)}
                  className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-brand-700 hover:text-brand-800"
                >
                  View <ChevronRight className="size-3.5" />
                </Link>
              )}
            </div>
            <button
              onClick={() => dismiss(t.id)}
              className="h-fit cursor-pointer text-slate-400 hover:text-slate-700"
              aria-label="Dismiss"
            >
              <X className="size-4" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function CommandPalette() {
  const open = useWorkspaceStore((s) => s.paletteOpen);
  const setOpen = useWorkspaceStore((s) => s.setPalette);
  const setAsk = useWorkspaceStore((s) => s.setAsk);
  const navigate = useNavigate();
  const { stages } = useWorkflow();
  const demo = useDemoPipeline();
  const go = (to: string) => {
    setOpen(false);
    navigate(to);
  };
  const item =
    'flex h-10 cursor-pointer items-center gap-3 rounded-lg px-3 text-sm text-slate-700 data-[selected=true]:bg-slate-100 data-[selected=true]:text-slate-900';
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[70] flex items-start justify-center p-4 pt-[12vh]">
          <motion.button
            aria-label="Close command menu"
            className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.15 }}
            className="relative w-full max-w-xl overflow-hidden rounded-2xl bg-white shadow-pop ring-1 ring-slate-200"
          >
            <Command label="Command menu" loop>
              <div className="flex items-center gap-3 border-b border-slate-100 px-4">
                <Search className="size-4 text-slate-400" />
                <Command.Input
                  autoFocus
                  placeholder="Jump to a step, page or action…"
                  className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-slate-400"
                />
                <Kbd>Esc</Kbd>
              </div>
              <Command.List className="max-h-[360px] overflow-y-auto p-2">
                <Command.Empty className="py-8 text-center text-sm text-slate-500">
                  No matches.
                </Command.Empty>
                <Command.Group
                  heading="Workflow"
                  className="px-1 py-1 text-xs font-medium text-slate-400 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5"
                >
                  {stages.map((s) => (
                    <Command.Item
                      key={s.key}
                      className={item}
                      onSelect={() => go(s.status === 'todo' ? s.home : s.to)}
                    >
                      <s.icon className="size-4 text-slate-400" />
                      <span className="flex-1">
                        {s.step}. {s.verb}
                      </span>
                      {s.status === 'done' && (
                        <Check className="size-4 text-brand-600" />
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group
                  heading="Actions"
                  className="px-1 py-1 text-xs font-medium text-slate-400 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5"
                >
                  <Command.Item
                    className={item}
                    onSelect={() => {
                      setOpen(false);
                      setAsk(true);
                    }}
                  >
                    <Sparkles className="size-4 text-slate-400" /> Ask AI about
                    your data
                  </Command.Item>
                  <Command.Item
                    className={item}
                    onSelect={() => go('/app/investigate')}
                  >
                    <FlaskConical className="size-4 text-slate-400" /> Start an
                    investigation
                  </Command.Item>
                  <Command.Item
                    className={item}
                    onSelect={() => {
                      setOpen(false);
                      void demo.start();
                    }}
                  >
                    <Database className="size-4 text-slate-400" /> Run the demo
                    pipeline (synthetic data)
                  </Command.Item>
                </Command.Group>
                <Command.Group
                  heading="Pages"
                  className="px-1 py-1 text-xs font-medium text-slate-400 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5"
                >
                  {[
                    ['/app', 'Home', LayoutDashboard] as const,
                    ...MAIN.map(
                      ([to, label, Icon]) => [to, label, Icon] as const,
                    ),
                    ...ADVANCED,
                  ].map(([to, label, Icon]) => (
                    <Command.Item
                      key={to}
                      className={item}
                      onSelect={() => go(to)}
                    >
                      <Icon className="size-4 text-slate-400" /> {label}
                    </Command.Item>
                  ))}
                </Command.Group>
              </Command.List>
            </Command>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

/** Ask context comes from where the user is: /app/models/:run, /app/scores/:score, ?run=. */
function askContext(pathname: string, search: string) {
  const params = new URLSearchParams(search);
  const run = pathname.match(/^\/app\/models\/([0-9a-f-]{36})/)?.[1];
  const score = pathname.match(/^\/app\/scores\/([0-9a-f-]{36})/)?.[1];
  return {
    run: run ?? params.get('run') ?? undefined,
    score: score ?? undefined,
    dataset: params.get('dataset') ?? undefined,
  };
}

function Shell({ name, email }: { name: string; email: string }) {
  const menu = useWorkspaceStore((s) => s.menuOpen);
  const setMenu = useWorkspaceStore((s) => s.setMenu);
  const ask = useWorkspaceStore((s) => s.askOpen);
  const setAsk = useWorkspaceStore((s) => s.setAsk);
  const setPalette = useWorkspaceStore((s) => s.setPalette);
  const location = useLocation();
  const worker = useResource<{ running: boolean }>(
    '/api/v1/worker',
    true,
    10000,
  );
  const [scrolled, setScrolled] = useState(false);
  const identity = useIdentity();
  useJobToasts();
  const title =
    TITLES.find(([re]) => re.test(location.pathname))?.[1] ?? 'Workspace';
  useEffect(() => {
    document.title = `${title} · Holdfast`;
    const id = decodeURIComponent(location.hash.slice(1));
    if (!id) {
      window.scrollTo({ top: 0 });
      return;
    }
    // Pages load lazily and render after their data arrives, so wait briefly for the anchor.
    let tries = 0;
    const timer = window.setInterval(() => {
      const target = document.getElementById(id);
      if (target || ++tries > 40) {
        window.clearInterval(timer);
        target?.scrollIntoView({ block: 'start' });
      }
    }, 75);
    return () => window.clearInterval(timer);
  }, [title, location.pathname, location.hash]);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPalette(!useWorkspaceStore.getState().paletteOpen);
      } else if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLowerCase() === 'j'
      ) {
        event.preventDefault();
        setAsk(!useWorkspaceStore.getState().askOpen);
      } else if (event.key === 'Escape') {
        setPalette(false);
        setAsk(false);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setAsk, setPalette]);
  const close = () => setMenu(false);
  return (
    <div className="min-h-screen bg-stock">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 lg:block">
        <Sidebar onNavigate={close} name={name} email={email} />
      </aside>
      <AnimatePresence>
        {menu && (
          <div className="fixed inset-0 z-50 lg:hidden">
            <motion.button
              aria-label="Close navigation"
              className="absolute inset-0 bg-slate-900/50"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={close}
            />
            <motion.aside
              className="absolute inset-y-0 left-0 w-72"
              initial={{ x: -288 }}
              animate={{ x: 0 }}
              exit={{ x: -288 }}
              transition={{ type: 'spring', bounce: 0, duration: 0.3 }}
            >
              <Sidebar onNavigate={close} name={name} email={email} />
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
      <div className="lg:pl-64">
        <header
          className={cn(
            'sticky top-0 z-30 flex h-16 items-center gap-3 border-b px-4 transition-colors sm:px-8',
            scrolled ? 'border-wire/60 bg-stock' : 'border-stock-300 bg-stock',
          )}
        >
          <button
            className="cursor-pointer rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
            aria-label="Open navigation"
            onClick={() => setMenu(true)}
          >
            <Menu className="size-5" />
          </button>
          <div className="flex min-w-0 items-center gap-2 text-sm">
            <Link
              to="/app"
              className="hidden text-slate-400 hover:text-slate-700 sm:block"
            >
              Workspace
            </Link>
            <ChevronRight className="hidden size-4 text-slate-300 sm:block" />
            <span className="truncate font-medium text-slate-900">{title}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setPalette(true)}
              className="hidden h-9 w-64 cursor-pointer items-center gap-2 bg-white px-3 text-sm text-slate-500 ring-1 ring-tag-ink/15 transition hover:ring-tag-ink/35 md:flex"
            >
              <Search className="size-4" />
              <span className="flex-1 text-left">Search or jump to…</span>
              <Kbd>⌘K</Kbd>
            </button>
            <WorkspacePill />
            <Link
              to="/app/jobs"
              title={
                worker.data?.running
                  ? 'Worker online'
                  : 'Worker offline: run pnpm worker:api'
              }
              className="hidden h-9 items-center gap-2 px-3 text-[13px] font-[600] text-slate-600 ring-1 ring-tag-ink/15 transition hover:bg-white sm:flex"
            >
              <span className="relative flex size-2">
                {worker.data?.running && (
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
                )}
                <span
                  className={cn(
                    'relative inline-flex size-2 rounded-full',
                    worker.data?.running ? 'bg-emerald-500' : 'bg-slate-300',
                  )}
                />
              </span>
              {worker.data?.running ? 'Worker online' : 'Worker offline'}
            </Link>
            <button
              onClick={() => setAsk(true)}
              className="flex h-9 cursor-pointer items-center gap-2 bg-tag-ink pr-3 pl-4 text-[13px] font-[640] text-stock transition [clip-path:polygon(7px_0,100%_0,100%_100%,7px_100%,0_50%)] hover:bg-field-900"
            >
              <Sparkles className="size-4 text-tag-amber" />
              Ask AI
            </button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1320px] px-4 py-8 sm:px-8">
          {/* Enter-only transition: an exit animation would render the next route's
              Outlet inside the outgoing container. */}
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {identity.data?.role === 'viewer' && (
              <div className="mb-6 rounded-xl bg-slate-100 px-4 py-2.5 text-sm text-slate-600 ring-1 ring-slate-200">
                You have view-only access to this team workspace. You can look
                around and ask AI questions; changes are made by members.
              </div>
            )}
            <Suspense fallback={<Loading />}>
              <Outlet />
            </Suspense>
          </motion.div>
        </main>
      </div>
      <AnimatePresence>
        {ask && (
          <div className="fixed inset-0 z-50">
            <motion.button
              aria-label="Close Ask AI"
              className="absolute inset-0 cursor-default bg-slate-900/30"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setAsk(false)}
            />
            <motion.aside
              aria-label="Ask AI"
              className="absolute inset-y-0 right-0 flex w-full max-w-[480px] flex-col bg-white shadow-pop"
              initial={{ x: 480 }}
              animate={{ x: 0 }}
              exit={{ x: 480 }}
              transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
            >
              <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-100 px-5">
                <div className="flex items-center gap-2.5">
                  <span className="grid size-8 place-items-center rounded-lg bg-slate-900">
                    <Sparkles className="size-4 text-brand-300" />
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      Ask AI
                    </p>
                    <p className="text-xs text-slate-500">
                      Answers checked against your results
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setAsk(false)}
                  className="cursor-pointer rounded-md p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  aria-label="Close Ask AI"
                >
                  <X className="size-4" />
                </button>
              </div>
              <div className="min-h-0 flex-1">
                <Suspense fallback={<Loading />}>
                  <Copilot
                    compact
                    initial={askContext(location.pathname, location.search)}
                  />
                </Suspense>
              </div>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
      <CommandPalette />
      <Toasts />
    </div>
  );
}

/** Which workspace you're in and your role; personal admins are invited to bring a team. */
function WorkspacePill() {
  const identity = useIdentity();
  const teams = useResource<{
    organizations: {
      role: string;
      organization: { id: string; name: string };
    }[];
  }>('/api/backend/organizations');
  if (!identity.data || identity.data.user_id === 'local') return null;
  const team = teams.data?.organizations.find(
    (t) => t.organization.id === identity.data!.organization_id,
  );
  return (
    <Link
      to="/app/team"
      className="hidden h-9 items-center gap-2 bg-white px-3 text-[13px] font-[600] text-tag-ink ring-1 ring-tag-ink/15 transition hover:ring-tag-ink/35 md:flex"
    >
      <Users className="size-4 text-brand-600" />
      {team ? (
        <>
          <span className="max-w-32 truncate">{team.organization.name}</span>
          <span className="bg-tag-slate px-1.5 py-0.5 text-[11px] font-[620] text-stock capitalize">
            {identity.data.role}
          </span>
        </>
      ) : (
        'Bring your team'
      )}
    </Link>
  );
}
