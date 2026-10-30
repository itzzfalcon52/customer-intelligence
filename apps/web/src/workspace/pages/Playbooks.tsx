import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { BookOpen, FileText, Search, Trash2, Upload } from 'lucide-react';
import { request } from '../api';
import { number } from '../format';
import { useAction, useResource } from '../queries';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Loading,
  Notice,
  PageHeader,
  Reveal,
} from '../ui';

interface Playbook {
  id: string;
  title: string;
  filename: string;
  created_at: string;
  characters: number;
  passages: number;
}
interface Passage {
  heading: string;
  text: string;
}
interface Hit {
  citation: string;
  playbook_id: string;
  playbook: string;
  passage: number;
  heading: string;
  text: string;
}

export function Playbooks() {
  const list = useResource<Playbook[]>('/api/v1/playbooks');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [query, setQuery] = useState('');
  const [asked, setAsked] = useState('');
  const upload = useAction<Playbook, undefined>(() => {
    const body = new FormData();
    body.append('file', file!);
    if (title.trim()) body.append('title', title.trim());
    return request('/api/v1/playbooks', { method: 'POST', body });
  });
  const hits = useResource<{ results: Hit[] }>(
    `/api/v1/playbooks/search?q=${encodeURIComponent(asked)}`,
    asked.length >= 2,
  );
  async function submit() {
    try {
      await upload.mutateAsync(undefined);
      setFile(null);
      setTitle('');
    } catch {
      /* rendered */
    }
  }
  const items = list.data ?? [];
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Workspace"
        title="Playbooks"
        description="Upload your own customer-success playbooks. When Ask AI recommends a play, it searches these and cites the passage it used, such as [P1], so you can check it."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-6">
          <Card
            title="Your playbooks"
            icon={BookOpen}
            description="Text and Markdown only. Headings are kept so each passage knows its section."
          >
            {list.isPending ? (
              <Loading label="Loading playbooks" />
            ) : items.length === 0 ? (
              <EmptyState
                compact
                icon={FileText}
                title="No playbooks yet"
                description="Add your renewal, onboarding or escalation playbook. Ask AI only cites what is written in them."
              />
            ) : (
              <ul className="-my-2 divide-y divide-slate-100">
                {items.map((p) => (
                  <li key={p.id}>
                    <Link
                      to={`/app/playbooks/${p.id}`}
                      className="flex items-center gap-3 rounded-lg py-3 transition-colors hover:bg-slate-50"
                    >
                      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-200">
                        <FileText className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold text-slate-900">
                          {p.title}
                        </span>
                        <span className="block truncate text-xs text-slate-500">
                          {p.filename} · added {p.created_at.slice(0, 10)}
                        </span>
                      </span>
                      <Badge>{number(p.passages)} passages</Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card
            title="Try a search"
            icon={Search}
            description="The same keyword search Ask AI uses. Results are ranked by relevance, best first."
          >
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setAsked(query.trim());
              }}
            >
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. failed payments, usage drop, renewal call"
                aria-label="Search playbooks"
                maxLength={300}
              />
              <Button type="submit" disabled={query.trim().length < 2}>
                Search
              </Button>
            </form>
            <Notice error={hits.error} />
            {asked && hits.data && (
              <div className="mt-4 space-y-3">
                {hits.data.results.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    No passage mentions those words. Ask AI will say the
                    playbooks don’t cover it rather than invent a play.
                  </p>
                ) : (
                  hits.data.results.map((h) => (
                    <Link
                      key={h.citation}
                      to={`/app/playbooks/${h.playbook_id}#passage-${h.passage}`}
                      className="block rounded-xl p-3 ring-1 ring-slate-200 transition hover:ring-brand-300"
                    >
                      <p className="flex items-center gap-2 text-xs text-slate-500">
                        <Badge tone="brand">{h.citation}</Badge>
                        <span className="truncate">
                          {h.playbook}
                          {h.heading && ` › ${h.heading}`}
                        </span>
                      </p>
                      <p className="mt-2 line-clamp-3 text-sm text-slate-700">
                        {h.text}
                      </p>
                    </Link>
                  ))
                )}
              </div>
            )}
          </Card>
        </div>
        <Reveal className="h-fit">
          <Card title="Add a playbook" icon={Upload}>
            <div className="space-y-4">
              <Field label="File" hint="Markdown or plain text, up to 1 MB.">
                <Input
                  type="file"
                  accept=".md,.markdown,.txt,text/plain,text/markdown"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </Field>
              <Field label="Title" hint="Optional. Defaults to the file name.">
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={120}
                  placeholder="Renewal playbook"
                />
              </Field>
              <Notice error={upload.error} />
              <Button
                variant="primary"
                className="w-full"
                disabled={!file}
                loading={upload.isPending}
                onClick={() => void submit()}
              >
                Upload playbook
              </Button>
              <p className="text-xs leading-relaxed text-slate-500">
                Playbooks describe what your team intends to do. Citing one
                doesn’t show that a play works; measured results come from
                holdout groups.
              </p>
            </div>
          </Card>
        </Reveal>
      </div>
    </div>
  );
}

export function PlaybookDetail() {
  const { id = '' } = useParams();
  const { hash } = useLocation();
  const navigate = useNavigate();
  const playbook = useResource<Playbook & { content: Passage[] }>(
    `/api/v1/playbooks/${id}`,
  );
  const [confirm, setConfirm] = useState(false);
  const remove = useAction<void, undefined>(() =>
    request(`/api/v1/playbooks/${id}`, { method: 'DELETE' }),
  );
  useEffect(() => {
    if (!playbook.data || !hash) return;
    document
      .getElementById(hash.slice(1))
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [playbook.data, hash]);
  async function destroy() {
    try {
      await remove.mutateAsync(undefined);
      navigate('/app/playbooks');
    } catch {
      setConfirm(false);
    }
  }
  if (playbook.isPending) return <Loading label="Loading playbook" />;
  if (!playbook.data) return <Notice error={playbook.error} />;
  const p = playbook.data;
  return (
    <div className="space-y-6">
      <PageHeader
        back={{ to: '/app/playbooks', label: 'Playbooks' }}
        title={p.title}
        description={`${p.filename} · ${number(p.passages)} passages · added ${p.created_at.slice(0, 10)}`}
        actions={
          confirm ? (
            <>
              <Button variant="ghost" onClick={() => setConfirm(false)}>
                Keep it
              </Button>
              <Button
                variant="danger"
                icon={Trash2}
                loading={remove.isPending}
                onClick={() => void destroy()}
              >
                Delete playbook
              </Button>
            </>
          ) : (
            <Button
              variant="ghost"
              icon={Trash2}
              onClick={() => setConfirm(true)}
            >
              Delete
            </Button>
          )
        }
      />
      <Notice error={remove.error} />
      <div className="space-y-3">
        {p.content.map((passage, i) => {
          const target = hash === `#passage-${i}`;
          return (
            <section
              key={i}
              id={`passage-${i}`}
              className={
                'scroll-mt-24 rounded-2xl bg-white p-5 shadow-card ring-1 transition ' +
                (target ? 'ring-2 ring-brand-400' : 'ring-slate-200/80')
              }
            >
              <p className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <span className="font-mono">#{i}</span>
                {passage.heading && (
                  <span className="font-medium text-slate-700">
                    {passage.heading}
                  </span>
                )}
                {target && <Badge tone="brand">Cited</Badge>}
              </p>
              <p className="text-sm leading-relaxed whitespace-pre-line text-slate-700">
                {passage.text}
              </p>
            </section>
          );
        })}
      </div>
    </div>
  );
}
