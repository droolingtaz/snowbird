import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine
} from "recharts";
import { clsx } from "clsx";

interface Point {
  date: string;
  equity: number;
  pnl?: number;
}

interface PerformanceChartProps {
  data: Point[];
  loading?: boolean;
  height?: number;
}

const periods = ["1D", "1W", "1M", "3M", "YTD", "1Y", "ALL"];

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const val: number = payload[0].value;
  return (
    <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-xs shadow-card-lg">
      <p className="text-text-secondary mb-0.5">{label}</p>
      <p className="font-semibold mono text-text-primary">${val.toLocaleString("en-US", { minimumFractionDigits: 2 })}</p>
    </div>
  );
}

interface PerformanceChartWithPeriodProps extends PerformanceChartProps {
  period: string;
  onPeriodChange: (p: string) => void;
  showBenchmark?: boolean;
  benchmarkData?: Array<{ date: string; portfolio: number; benchmark: number }>;
  onBenchmarkToggle?: () => void;
}

export default function PerformanceChart({
  data, loading, height = 240, period, onPeriodChange, showBenchmark, benchmarkData, onBenchmarkToggle
}: PerformanceChartWithPeriodProps) {
  const chartData = showBenchmark && benchmarkData?.length ? benchmarkData : data;

  return (
    <div>
      {/* Period selector */}
      <div className="flex items-center gap-1 mb-3 flex-wrap">
        {periods.map((p) => (
          <button
            key={p}
            onClick={() => onPeriodChange(p)}
            className={clsx(
              "px-2.5 py-1 rounded text-xs font-medium transition-colors",
              p === period
                ? "bg-accent/20 text-accent"
                : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
            )}
          >
            {p}
          </button>
        ))}
        {onBenchmarkToggle && (
          <button
            onClick={onBenchmarkToggle}
            className={clsx(
              "ml-2 px-2.5 py-1 rounded text-xs font-medium transition-colors border",
              showBenchmark
                ? "border-orange-500/50 bg-orange-500/10 text-orange-400"
                : "border-border text-text-secondary hover:bg-surface-2"
            )}
          >
            vs SPY
          </button>
        )}
      </div>

      {loading ? (
        <div className="animate-pulse bg-surface-2 rounded-lg" style={{ height }} />
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          {showBenchmark && benchmarkData?.length ? (
            <AreaChart data={benchmarkData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="portfolioGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4f7cff" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#4f7cff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="benchmarkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f97316" stopOpacity={0.1} />
                  <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} width={45} domain={["auto", "auto"]} />
              <Tooltip contentStyle={{ background: "#1a1e25", border: "1px solid #1e2433", borderRadius: 8 }} />
              <Area type="monotone" dataKey="portfolio" stroke="#4f7cff" fill="url(#portfolioGrad)" strokeWidth={2} dot={false} name="Portfolio" />
              <Area type="monotone" dataKey="benchmark" stroke="#f97316" fill="url(#benchmarkGrad)" strokeWidth={1.5} dot={false} name="SPY" strokeDasharray="4 2" />
            </AreaChart>
          ) : (
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4f7cff" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#4f7cff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} width={60} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} domain={["auto", "auto"]} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="equity" stroke="#4f7cff" fill="url(#equityGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          )}
        </ResponsiveContainer>
      )}
    </div>
  );
}
