import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const SERIES = ['#0f5a54', '#f2b91f', '#d7262e', '#636f6b', '#4fa598'];
const axis = { fontSize: 11, fill: '#929e99' };
const tooltip = {
  contentStyle: {
    background: '#052523',
    border: 'none',
    borderRadius: 10,
    color: '#f5f7f4',
    fontSize: 12,
    boxShadow: '0 10px 30px -10px rgb(15 23 42 / 0.5)',
  },
  itemStyle: { color: '#dce1dc' },
  labelStyle: { color: '#929e99', marginBottom: 4 },
  cursor: { fill: 'rgb(148 163 184 / 0.12)' },
};
const nice = (key: string) =>
  key.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
const fmt = (v: unknown) =>
  typeof v === 'number'
    ? Math.abs(v) >= 100
      ? v.toLocaleString()
      : v.toFixed(3)
    : String(v);

export function Bars({
  data,
  x,
  y,
  height = 260,
  horizontal = false,
  highlight,
}: {
  data: object[];
  x: string;
  y: string;
  height?: number;
  horizontal?: boolean;
  highlight?: string;
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout={horizontal ? 'vertical' : 'horizontal'}
          margin={{ top: 8, right: 16, left: horizontal ? 8 : -8, bottom: 0 }}
        >
          <CartesianGrid
            stroke="#e6eae5"
            horizontal={!horizontal}
            vertical={horizontal}
          />
          {horizontal ? (
            <>
              <XAxis
                type="number"
                tick={axis}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey={x}
                tick={{ ...axis, fill: '#4a5552' }}
                width={150}
                axisLine={false}
                tickLine={false}
              />
            </>
          ) : (
            <>
              <XAxis
                dataKey={x}
                tick={axis}
                axisLine={false}
                tickLine={false}
              />
              <YAxis tick={axis} axisLine={false} tickLine={false} />
            </>
          )}
          <Tooltip {...tooltip} formatter={(v) => [fmt(v), nice(y)]} />
          <Bar
            dataKey={y}
            radius={horizontal ? [0, 2, 2, 0] : [2, 2, 0, 0]}
            maxBarSize={44}
            animationDuration={700}
          >
            {data.map((d, i) => (
              <Cell
                key={i}
                fill={
                  highlight && (d as Record<string, unknown>)[x] === highlight
                    ? '#0f5a54'
                    : highlight
                      ? '#c3cbc5'
                      : '#2b877b'
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Curve({
  data,
  x,
  lines,
  height = 280,
}: {
  data: object[];
  x: string;
  lines: string[];
  height?: number;
}) {
  if (lines.length === 1)
    return (
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 8, right: 16, left: -4, bottom: 0 }}
          >
            <defs>
              <linearGradient
                id={`fill-${lines[0]}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor="#2b877b" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#2b877b" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#e6eae5" vertical={false} />
            <XAxis dataKey={x} tick={axis} axisLine={false} tickLine={false} />
            <YAxis tick={axis} axisLine={false} tickLine={false} />
            <Tooltip {...tooltip} formatter={(v) => [fmt(v), nice(lines[0])]} />
            <Area
              type="monotone"
              dataKey={lines[0]}
              stroke="#0f5a54"
              strokeWidth={2}
              fill={`url(#fill-${lines[0]})`}
              animationDuration={800}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    );
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 8, right: 16, left: -4, bottom: 0 }}
        >
          <CartesianGrid stroke="#e6eae5" vertical={false} />
          <XAxis dataKey={x} tick={axis} axisLine={false} tickLine={false} />
          <YAxis tick={axis} axisLine={false} tickLine={false} />
          <Tooltip
            {...tooltip}
            formatter={(v, name) => [fmt(v), nice(String(name))]}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(v) => (
              <span className="text-xs text-slate-600">{nice(String(v))}</span>
            )}
          />
          {lines.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={SERIES[i % SERIES.length]}
              strokeWidth={2.25}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
              connectNulls={false}
              animationDuration={800}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Histogram of risk scores in ten buckets. */
export function Histogram({
  scores,
  height = 220,
}: {
  scores: number[];
  height?: number;
}) {
  const buckets = Array.from({ length: 10 }, (_, i) => ({
    range: `${(i / 10).toFixed(1)}`,
    accounts: 0,
    i,
  }));
  for (const s of scores) buckets[Math.min(9, Math.floor(s * 10))].accounts++;
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={buckets}
          margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
        >
          <CartesianGrid stroke="#e6eae5" vertical={false} />
          <XAxis
            dataKey="range"
            tick={axis}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={axis}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            {...tooltip}
            labelFormatter={(l) => `Score ${l}–${(Number(l) + 0.1).toFixed(1)}`}
            formatter={(v) => [String(v), 'Accounts']}
          />
          <Bar dataKey="accounts" radius={[5, 5, 0, 0]} animationDuration={700}>
            {buckets.map((b) => (
              <Cell
                key={b.i}
                fill={b.i >= 7 ? '#d7262e' : b.i >= 4 ? '#f2b91f' : '#929e99'}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Donut({
  data,
  height = 180,
  center,
}: {
  data: { name: string; value: number; color: string }[];
  height?: number;
  center?: { value: string; label: string };
}) {
  return (
    <div className="relative" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="68%"
            outerRadius="100%"
            paddingAngle={2}
            stroke="none"
            animationDuration={800}
          >
            {data.map((d) => (
              <Cell key={d.name} fill={d.color} />
            ))}
          </Pie>
          <Tooltip {...tooltip} />
        </PieChart>
      </ResponsiveContainer>
      {center && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="font-mono text-2xl font-bold text-tag-ink tabular">
              {center.value}
            </p>
            <p className="text-xs text-slate-500">{center.label}</p>
          </div>
        </div>
      )}
    </div>
  );
}
