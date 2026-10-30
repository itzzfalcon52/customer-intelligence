import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  FlaskConical,
  Gauge,
  Layers,
  Scale,
  ShieldAlert,
  Wand2,
} from 'lucide-react';
import { metric } from '../format';
import { useCatalog, useResource } from '../queries';
import type { Analysis } from '../types';
import { Bars, Curve } from '../charts';
import {
  Alert,
  Badge,
  ButtonLink,
  Card,
  EmptyState,
  JsonDetails,
  Loading,
  Notice,
  PageHeader,
  Pagination,
  Table,
  Td,
  Th,
  Tr,
} from '../ui';

function describe(a: Analysis) {
  if (a.kind === 'investigation')
    return {
      title: 'Investigation',
      icon: FlaskConical,
      tone: 'bg-violet-50 text-violet-600',
    };
  if (a.kind === 'campaign')
    return {
      title: 'Outreach drafts',
      icon: Wand2,
      tone: 'bg-sky-50 text-sky-600',
    };
  if (a.kind === 'executive_briefing')
    return {
      title: 'Executive briefing',
      icon: BarChart3,
      tone: 'bg-sky-50 text-sky-600',
    };
  if (a.kind === 'rule_challenger')
    return {
      title: 'Rule check',
      icon: Scale,
      tone: 'bg-amber-50 text-amber-600',
    };
  if (a.effects)
    return {
      title: 'Customer explanation',
      icon: Wand2,
      tone: 'bg-brand-50 text-brand-600',
    };
  if (a.results)
    return {
      title: 'Leakage demonstration',
      icon: ShieldAlert,
      tone: 'bg-rose-50 text-rose-600',
    };
  return {
    title: 'Model diagnostics',
    icon: Gauge,
    tone: 'bg-emerald-50 text-emerald-600',
  };
}

export function Analyses() {
  const [page, setPage] = useState(0);
  const data = useCatalog<Analysis>('analyses', page);
  return (
    <>
      <PageHeader
        title="Analyses"
        description="Everything computed behind the scores: diagnostics, customer explanations, investigations and saved AI work."
        actions={
          <ButtonLink to="/app/models" icon={Gauge}>
            Create diagnostics from a model
          </ButtonLink>
        }
      />
      <Notice error={data.error} />
      {data.isPending ? (
        <div className="skeleton h-64 rounded-2xl" />
      ) : data.data?.length ? (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.data.map((a) => {
              const d = describe(a);
              const Icon = d.icon;
              const internal =
                a.kind === 'investigation'
                  ? '/app/investigate'
                  : `/app/analyses/${a.id}`;
              return (
                <Link
                  key={a.id}
                  to={internal}
                  className="group flex items-start gap-4 rounded-2xl bg-white p-5 shadow-card ring-1 ring-slate-200/80 transition hover:-translate-y-0.5 hover:shadow-lift"
                >
                  <span
                    className={`grid size-10 shrink-0 place-items-center rounded-xl ${d.tone}`}
                  >
                    <Icon className="size-5" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold text-slate-900">
                      {d.title}
                    </span>
                    <span className="mt-1 block text-[13px] text-slate-500">
                      {a.partition
                        ? `On ${a.partition} data`
                        : a.score_id
                          ? 'For a scored customer'
                          : 'Saved result'}
                    </span>
                  </span>
                  <ArrowUpRight className="size-4 text-slate-300 transition group-hover:text-slate-600" />
                </Link>
              );
            })}
          </div>
          <Pagination page={page} setPage={setPage} count={data.data.length} />
        </>
      ) : (
        <Card>
          <EmptyState
            icon={BarChart3}
            title="No analyses yet"
            description="Open a model and create diagnostics, or click Explain next to an account in a scoring batch."
            action={
              <ButtonLink variant="primary" to="/app/models">
                Go to models
              </ButtonLink>
            }
          />
        </Card>
      )}
    </>
  );
}

export function AnalysisDetail() {
  const { id } = useParams();
  const data = useResource<Analysis>(`/api/v1/analyses/${id}`, Boolean(id));
  if (data.isPending) return <Loading />;
  if (!data.data) return <Notice error={data.error} />;
  const a = data.data;
  const d = describe(a);
  return (
    <>
      <PageHeader
        back={{ to: '/app/analyses', label: 'All analyses' }}
        eyebrow={<Badge tone="brand">{d.title}</Badge>}
        title={d.title}
        description="Measured evidence, with its limits in view."
        actions={
          a.run_id && (
            <ButtonLink to={`/app/models/${a.run_id}`} trailing={ArrowRight}>
              Source model
            </ButtonLink>
          )
        }
      />
      <div className="space-y-6">
        {(a.warning || a.importance_warning) && (
          <Alert tone="warning">{a.warning || a.importance_warning}</Alert>
        )}
        {a.permutation_importance && (
          <Card
            title="Which inputs matter to this model?"
            icon={BarChart3}
            description="Drop in validation average precision when each input is shuffled. Association, not causation."
          >
            <Bars
              data={[...a.permutation_importance].sort(
                (x, y) => y.mean_ap_decrease - x.mean_ap_decrease,
              )}
              x="feature"
              y="mean_ap_decrease"
              horizontal
              height={Math.max(200, a.permutation_importance.length * 38)}
            />
          </Card>
        )}
        {a.contact_curve && (
          <Card
            title="What changes with contact capacity?"
            description="Validation precision, recall and lift at different contact counts."
          >
            <Curve
              data={a.contact_curve}
              x="k"
              lines={['precision', 'recall', 'lift']}
            />
          </Card>
        )}
        {a.calibration && (
          <Card
            title="Do scores match outcomes?"
            description={`Validation Brier score ${metric(a.calibration.brier_score)}. This alone doesn’t make scores calibrated probabilities.`}
          >
            <Curve
              data={a.calibration.bins}
              x="lower"
              lines={['mean_score', 'observed_positive_rate']}
            />
          </Card>
        )}
        {a.segments && a.segments.length > 0 && (
          <Card title="Performance across customer groups" icon={Layers}>
            <Table>
              <thead>
                <tr>
                  <Th>Segment</Th>
                  <Th align="right">Rows</Th>
                  <Th align="right">Avg. precision</Th>
                  <Th align="right">Recall</Th>
                  <Th>Note</Th>
                </tr>
              </thead>
              <tbody>
                {a.segments.map((s) => (
                  <Tr key={s.segment}>
                    <Td className="font-medium text-slate-900">{s.segment}</Td>
                    <Td align="right" mono>
                      {s.row_count}
                    </Td>
                    <Td align="right" mono>
                      {metric(s.metrics?.average_precision)}
                    </Td>
                    <Td align="right" mono>
                      {metric(s.metrics?.recall)}
                    </Td>
                    <Td className="text-slate-500">{s.warning || '—'}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          </Card>
        )}
        {a.heuristic != null && (
          <Card
            title="Simple rule benchmark"
            icon={Scale}
            description={a.heuristic.warning}
          >
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-semibold tabular">
                {metric(a.heuristic.average_precision)}
              </span>
              <span className="text-sm text-slate-500">
                validation avg. precision for “{a.heuristic.column}”,{' '}
                {a.heuristic.direction.replaceAll('_', ' ')}
              </span>
            </div>
          </Card>
        )}
        {a.effects && (
          <Card
            title="What moves this account’s score"
            icon={Wand2}
            description="Replacing one input with a typical value shows model sensitivity. Not a causal explanation."
          >
            <Bars
              data={a.effects}
              x="feature"
              y="risk_score_change_if_replaced"
              horizontal
              height={Math.max(200, a.effects.length * 38)}
            />
            <div className="mt-4">
              <Table>
                <thead>
                  <tr>
                    <Th>Input</Th>
                    <Th>Typical value</Th>
                    <Th align="right">Score change if replaced</Th>
                  </tr>
                </thead>
                <tbody>
                  {a.effects.map((f) => (
                    <Tr key={f.feature}>
                      <Td className="font-medium text-slate-900">
                        {f.feature}
                      </Td>
                      <Td>{f.reference_value}</Td>
                      <Td align="right" mono>
                        {metric(f.risk_score_change_if_replaced)}
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            </div>
          </Card>
        )}
        {a.results && (
          <Card
            title="Why future information fools a model"
            icon={ShieldAlert}
            description="The leaked input copies the outcome. That invalid model is never used for scoring."
          >
            <div className="grid gap-4 sm:grid-cols-2">
              {Object.entries(a.results).map(([name, m]) => (
                <div
                  key={name}
                  className={
                    name === 'with_leakage'
                      ? 'rounded-xl bg-rose-50 p-5 ring-1 ring-rose-200'
                      : 'rounded-xl bg-emerald-50 p-5 ring-1 ring-emerald-200'
                  }
                >
                  <p className="text-sm font-medium text-slate-700">
                    {name === 'with_leakage'
                      ? 'With invalid future input'
                      : 'Without leakage'}
                  </p>
                  <p className="mt-2 text-3xl font-semibold tabular">
                    {metric(m.average_precision)}
                  </p>
                  <p className="text-xs text-slate-500">
                    validation avg. precision
                  </p>
                </div>
              ))}
            </div>
          </Card>
        )}
        <JsonDetails data={a} label="Complete analysis and evidence" />
      </div>
    </>
  );
}
