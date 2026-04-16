import { useState } from "react";
import { usePerformance, useBenchmark, useMonthlyReturns } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "../components/Card";
import { clsx } from "clsx";

const periods = ["1M", "3M", "YTD", "1Y", "ALL"];

function pct(n?: number | null) {
  if (n == null) return "—";
  const v = n * 100;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function MonthlyHeatmap({ data }: { data: Array<{ year: number; month: number; return_pct?: number | null }> }) {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const years = [...new Set(data.map((d) => d.year))].sort();

  if (!data.length) return <p className="text-text-tertiary text-sm">No data available yet.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="text-xs w-full">
        <thead>
          <tr>
            <th className="text-left px-2 py-1 text-text-tertiary font-normal w-12">Year</th>
            {months.map((m) => (
              <th key={m} className="px-1 py-1 text-center text-text-tertiary font-normal">{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((year) => (
            <tr key={year}>
              <td className="px-2 py-1 text-text-secondary">{year}</td>
              {months.map((_, mi) => {
                const cell = data.find((d) => d.year === year && d.month === mi + 1);
                const val = cell?.return_pct;
                const intensity = val != null ? Math.min(Math.abs(val) * 400, 0.8) : 0;
                return (
                  <td
                    key={mi}
                    className="px-1 py-1 text-center rounded"
                    style={{
                      background: val == null
                        ? "transparent"
                        : val >= 0
                          ? `rgba(34,197,94,${intensity})`
                          : `rgba(239,68,68,${intensity})`,
                    }}
                    title={val != null ? `${pct(val)}` : "No data"}
                  >
                    {val != null ? (
                      <span className={clsx("mono text-2xs", val >= 0 ? "text-green-profit" : "text-red-loss")}>
                        {(val * 100).toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-text-tertiary">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Performance() {
  const accountId = useAuthStore((s) => s.accountId);
  const [period, setPeriod] = useState("1Y");
  const { data: metrics } = usePerformance(period);
  const { data: benchmark } = useBenchmark("SPY", period);
  const { data: monthly = [] } = useMonthlyReturns();

  const stats = [
    { label: "TWR", value: pct(metrics?.twr) },
    { label: "CAGR", value: pct(metrics?.cagr) },
    { label: "Total Return", value: pct(metrics?.total_return_pct) },
    { label: "Volatility (ann.)", value: pct(metrics?.volatility) },
    { label: "Sharpe Ratio", value: metrics?.sharpe != null ? metrics.sharpe.toFixed(2) : "—" },
    { label: "Max Drawdown", value: pct(metrics?.max_drawdown) },
    { label: "Best Day", value: pct(metrics?.best_day) },
    { label: "Worst Day", value: pct(metrics?.worst_day) },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Performance</h1>
        <div className="flex gap-1">
          {periods.map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={clsx(
                "px-2.5 py-1 rounded text-xs font-medium transition-colors",
                p === period ? "bg-accent/20 text-accent" : "text-text-secondary hover:bg-surface-2"
              )}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {stats.map((s) => (
          <div key={s.label} className="card">
            <p className="text-2xs uppercase tracking-wider text-text-tertiary mb-1">{s.label}</p>
            <p className={clsx(
              "text-xl font-semibold mono",
              s.value.startsWith("+") ? "text-green-profit" :
              s.value.startsWith("-") ? "text-red-loss" : "text-text-primary"
            )}>
              {s.value}
            </p>
          </div>
        ))}
      </div>

      {/* Benchmark comparison */}
      {benchmark?.points?.length > 0 && (
        <Card title="Portfolio vs SPY (normalized to 100)">
          <div className="overflow-x-auto">
            <div className="text-xs text-text-secondary flex gap-6 mb-3">
              <span>Portfolio: <strong className={clsx(
                (benchmark.portfolio_return ?? 0) >= 0 ? "text-green-profit" : "text-red-loss"
              )}>{pct(benchmark.portfolio_return)}</strong></span>
              <span>SPY: <strong className={clsx(
                (benchmark.benchmark_return ?? 0) >= 0 ? "text-green-profit" : "text-red-loss"
              )}>{pct(benchmark.benchmark_return)}</strong></span>
            </div>
          </div>
        </Card>
      )}

      {/* Monthly heatmap */}
      <Card title="Monthly Returns">
        <MonthlyHeatmap data={monthly} />
      </Card>
    </div>
  );
}
