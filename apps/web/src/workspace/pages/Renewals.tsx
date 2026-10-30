import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlarmClockOff,
  ArrowRight,
  CalendarClock,
  Download,
  Flame,
  Wallet,
} from 'lucide-react';
import { download } from '../api';
import { calendarDay, number } from '../format';
import { useMemory, useReasons, useResource } from '../queries';
import { ReasonLine } from '../brief-ui';
import { cn } from '../style';
import { TAG_SHAPE } from '../../components/site/Tag';
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Loading,
  Notice,
  PageHeader,
  RiskBadge,
  ScoreBar,
  Select,
  Stat,
  Table,
  Tabs,
  Td,
  Th,
  Tr,
} from '../ui';

type Window = '30' | '60' | '90';
type Sort = 'risk' | 'date' | 'value';

interface Item {
  account_id: string;
  customer_id: string;
  rank: number;
  risk_score: number;
  level: 'high' | 'elevated' | 'low';
  renews_at: string;
  days_left: number;
  overdue: boolean;
  cancel_scheduled: boolean;
  amount: number | null;
  billing_cycle: string | null;
  holdout: boolean;
}

interface Radar {
  available: boolean;
  message?: string;
  score_id?: string;
  source_name?: string;
  as_of?: string;
  window_days: number;
  totals?: {
    renewing: number;
    value_renewing: number;
    high_risk: number;
    value_high_risk: number;
    cancel_scheduled: number;
    overdue: number;
  };
  items: Item[];
}

/** Who renews soon and might not: billing renewal dates joined to the latest risk ranks. */
export function Renewals() {
  const [window, setWindow] = useState<Window>('30');
  const [sort, setSort] = useState<Sort>('risk');
  const radar = useResource<Radar>(
    `/api/v1/renewals?days=${window}&sort=${sort}`,
  );
  const currency = useMemory().data?.assumptions?.currency ?? null;
  const money = (value: number | null | undefined) =>
    value == null
      ? '—'
      : currency
        ? Intl.NumberFormat(undefined, {
            style: 'currency',
            currency,
            maximumFractionDigits: 0,
          }).format(value)
        : number(Math.round(value));
  const data = radar.data;
  return (
    <>
      <PageHeader
        title="Renewal radar"
        description="Accounts renewing soon, ranked by churn risk, with the value that renews. Talk to the risky ones before the date, not after."
        actions={
          data?.available && (
            <Button
              icon={Download}
              onClick={() =>
                void download(
                  `/api/v1/renewals/export.csv?days=${window}&sort=${sort}`,
                  `renewals-${window}d.csv`,
                )
              }
            >
              Export CSV
            </Button>
          )
        }
      />
      {radar.isLoading ? (
        <Loading label="Loading renewals" />
      ) : !data?.available ? (
        <Card>
          <EmptyState
            icon={CalendarClock}
            title="No renewal dates yet"
            description={
              data?.message ??
              'Connect a billing system to see who renews soon.'
            }
            action={
              <div className="flex flex-wrap justify-center gap-2">
                <ButtonLink to="/app/sources#connectors" variant="primary">
                  Connect billing
                </ButtonLink>
                <ButtonLink to="/app/guides/connectors">
                  Connector guide
                </ButtonLink>
              </div>
            }
          />
          <Notice error={radar.error} />
        </Card>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <Tabs
              value={window}
              onChange={setWindow}
              tabs={[
                { value: '30', label: 'Next 30 days' },
                { value: '60', label: '60 days' },
                { value: '90', label: '90 days' },
              ]}
            />
            <p className="text-[13px] text-slate-500">
              {data.source_name} · as of {calendarDay(data.as_of!)}
            </p>
          </div>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Renewing"
              icon={CalendarClock}
              value={number(data.totals!.renewing)}
              hint={`In the next ${data.window_days} days`}
            />
            <Stat
              label="Value renewing"
              icon={Wallet}
              tone="brand"
              value={money(data.totals!.value_renewing)}
              hint={
                currency
                  ? 'Last payment of each account'
                  : 'Last payments · set a currency in Settings'
              }
            />
            <Stat
              label="On high-risk accounts"
              icon={Flame}
              tone="danger"
              value={money(data.totals!.value_high_risk)}
              hint={`${number(data.totals!.high_risk)} accounts in the top 10% of risk`}
            />
            <Stat
              label="Set to cancel"
              icon={AlarmClockOff}
              tone="warning"
              value={number(data.totals!.cancel_scheduled)}
              hint={
                data.totals!.overdue
                  ? `${number(data.totals!.overdue)} renewal dates already passed`
                  : 'Already scheduled in billing'
              }
            />
          </div>
          <Card
            bodyClassName="p-0"
            footer={
              <p className="text-xs text-slate-500">
                Renewal dates and “set to cancel” come straight from your
                billing system.{' '}
                <Link
                  to={`/app/scores/${data.score_id}`}
                  className="inline-flex items-center gap-1 font-medium text-brand-700"
                >
                  Full risk list <ArrowRight className="size-3" />
                </Link>
              </p>
            }
            title="Accounts renewing"
            description="Set-to-cancel accounts first, then by risk. Risk scores rank accounts; they are not probabilities, and the value is each account’s last payment."
            action={
              <Select
                aria-label="Sort renewals"
                value={sort}
                onChange={(e) => setSort(e.target.value as Sort)}
                className="w-40"
              >
                <option value="risk">Sort by risk</option>
                <option value="date">Sort by date</option>
                <option value="value">Sort by value</option>
              </Select>
            }
          >
            {data.items.length ? (
              <RenewalTable
                items={data.items}
                scoreId={data.score_id!}
                money={money}
              />
            ) : (
              <EmptyState
                compact
                icon={CalendarClock}
                title={`No renewals in the next ${data.window_days} days`}
                description="Try a longer window."
              />
            )}
          </Card>
        </>
      )}
    </>
  );
}

function RenewalTable({
  items,
  scoreId,
  money,
}: {
  items: Item[];
  scoreId: string;
  money: (value: number | null) => string;
}) {
  const reasons = useReasons(scoreId);
  // A month of monthly renewals can be hundreds of rows; the riskiest come first.
  const [shown, setShown] = useState(50);
  return (
    <>
      <Table>
        <thead>
          <tr>
            <Th>Rank</Th>
            <Th>Account</Th>
            <Th>Renews</Th>
            <Th align="right">Value</Th>
            <Th>Risk</Th>
            <Th align="right">Risk score</Th>
          </tr>
        </thead>
        <tbody>
          {items.slice(0, shown).map((item) => (
            <Tr key={item.customer_id}>
              <Td mono className="font-semibold text-tag-ink">
                <span className="flex items-center gap-2.5">
                  <span
                    aria-hidden="true"
                    className={cn(
                      'h-4 w-2.5 shrink-0',
                      item.level === 'high' && 'bg-tag-red',
                      item.level === 'elevated' && 'bg-tag-amber',
                      item.level === 'low' && 'bg-stock-300',
                    )}
                    style={{ clipPath: TAG_SHAPE }}
                  />
                  #{item.rank}
                </span>
              </Td>
              <Td className="font-medium text-slate-900">
                <span className="flex flex-wrap items-center gap-2">
                  {item.account_id}
                  {item.cancel_scheduled && (
                    <Badge tone="danger">Set to cancel</Badge>
                  )}
                  {item.holdout && <Badge>Holdout · don’t contact</Badge>}
                </span>
                <ReasonLine
                  reasons={reasons.data}
                  customerId={item.customer_id}
                />
              </Td>
              <Td className="whitespace-nowrap">
                <span
                  className={cn(
                    'font-mono text-[13px] font-semibold',
                    item.overdue
                      ? 'text-rose-700'
                      : item.days_left <= 14
                        ? 'text-tag-ink'
                        : 'text-slate-600',
                  )}
                >
                  {item.overdue
                    ? `${Math.abs(item.days_left)}d overdue`
                    : item.days_left === 0
                      ? 'today'
                      : `in ${item.days_left}d`}
                </span>
                <span className="block text-xs text-slate-500">
                  {calendarDay(item.renews_at)}
                </span>
              </Td>
              <Td align="right" mono>
                {money(item.amount)}
                {item.billing_cycle && (
                  <span className="block font-sans text-xs text-slate-500">
                    {item.billing_cycle}
                  </span>
                )}
              </Td>
              <Td>
                <RiskBadge level={item.level} />
              </Td>
              <Td align="right">
                <ScoreBar value={item.risk_score} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
      {items.length > shown && (
        <div className="border-t border-slate-100 px-5 py-3 text-center">
          <Button size="sm" onClick={() => setShown((n) => n + 100)}>
            Show {number(Math.min(100, items.length - shown))} more of{' '}
            {number(items.length - shown)}
          </Button>
        </div>
      )}
    </>
  );
}
