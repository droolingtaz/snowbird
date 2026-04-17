import { useState } from "react";
import {
  usePortfolioSummary, usePortfolioHistory, usePortfolioAllocation,
  useHoldings, useDividendCalendar, useBenchmark,
} from "../api/hooks";
import { useAuthStore } from "../store/auth";
import StatTile from "../components/StatTile";
import Card from "../components/Card";
import PerformanceChart from "../components/PerformanceChart";
import AllocationDonut from "../components/AllocationDonut";
import UpcomingEventsCard from "../components/UpcomingEventsCard";
import IncomeGoalCard from "../components/IncomeGoalCard";
import { clsx } from "clsx";
import { format, addDays } from "date-fns";

function fmt(n?: number) {
  if (n == null) return "\u2014";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2 });
}

export default function Dashboard() {
  const accountId = useAuthStore((s) => s.accountId);
  const [period, setPeriod] = useState("1M");
  const [showBenchmark, setShowBenchmark] = useState(false);
  const [allocBy, setAllocBy] = useState("sector");

  const { data: summary, isLoading: sumLoading } = usePortfolioSummary();
  const { data: history, isLoading: histLoading } = usePortfolioHistory(period);
  const { data: allocation } = usePortfolioAllocation(allocBy);
  const { data: holdings = [] } = useHoldings();

  const { data: benchmarkRaw } = useBenchmark("SPY", period);

  const today = format(new Date(), "yyyy-MM-dd");
  const in90 = format(addDays(new Date(), 90), "yyyy-MM-dd");
  const { data: divCalendar = [] } = useDividendCalendar(today, in90);

  // Top movers
  const topMovers = [...holdings]
    .filter((h: any) => h.unrealized_plpc != null)
    .sort((a: any, b: any) => Math.abs(b.unrealized_plpc) - Math.abs(a.unrealized_plpc))
    .slice(0, 5);

  if (!accountId) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-24 gap-4">
        <p className="text-text-secondary text-lg">No account selected.</p>
        <a href="/settings" className="btn-primary">Add Alpaca Account</a>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dashboard</h1>
      </div>

      {/* Stat tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          label="Equity"
          value={summary?.equity ?? 0}
          loading={sumLoading}
        />
        <StatTile
          label="Today P/L"
          value={summary?.today_pl ?? 0}
          changePct={summary?.today_pl_pct}
          loading={sumLoading}
        />
        <StatTile
          label="Total P/L"
          value={summary?.total_pl ?? 0}
          loading={sumLoading}
        />
        <StatTile
          label="Buying Power"
          value={summary?.buying_power ?? 0}
          loading={sumLoading}
        />
      </div>

      {/* Performance chart */}
      <Card title="Portfolio Value">
        <PerformanceChart
          data={history?.points ?? []}
          loading={histLoading}
          period={period}
          onPeriodChange={setPeriod}
          showBenchmark={showBenchmark}
          benchmarkData={benchmarkRaw?.points}
          onBenchmarkToggle={() => setShowBenchmark(!showBenchmark)}
        />
      </Card>

      {/* Middle row: Allocation + Top Movers + Upcoming Events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Allocation */}
        <Card
          title="Allocation"
          className="lg:col-span-1"
          action={
            <select
              className="text-xs bg-transparent text-text-secondary border border-border rounded px-1 py-0.5"
              value={allocBy}
              onChange={(e) => setAllocBy(e.target.value)}
            >
              <option value="sector">Sector</option>
              <option value="asset_class">Asset Class</option>
              <option value="bucket">Bucket</option>
            </select>
          }
        >
          <AllocationDonut items={allocation?.items ?? []} />
        </Card>

        {/* Top movers */}
        <Card title="Top Movers" className="lg:col-span-1">
          {topMovers.length === 0 ? (
            <p className="text-text-tertiary text-sm py-4 text-center">No positions</p>
          ) : (
            <div className="space-y-2">
              {topMovers.map((h: any) => (
                <div key={h.symbol} className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-medium">{h.symbol}</span>
                    {h.name && <span className="ml-1.5 text-2xs text-text-tertiary">{h.name}</span>}
                  </div>
                  <div className={clsx(
                    "text-sm mono font-medium",
                    h.unrealized_plpc >= 0 ? "text-green-profit" : "text-red-loss"
                  )}>
                    {h.unrealized_plpc >= 0 ? "+" : ""}
                    {(h.unrealized_plpc * 100).toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Upcoming Events */}
        <UpcomingEventsCard />
      </div>

      {/* Bottom row: Upcoming Dividends + Income Goal */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Upcoming dividends */}
        <Card title="Upcoming Dividends">
          {divCalendar.length === 0 ? (
            <p className="text-text-tertiary text-sm py-4 text-center">No upcoming dividends</p>
          ) : (
            <div className="space-y-2">
              {divCalendar.slice(0, 5).map((d: any, i: number) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="font-medium">{d.symbol}</span>
                    <span className="ml-2 text-text-tertiary text-xs">{d.pay_date}</span>
                  </div>
                  <span className="mono text-green-profit">
                    {d.projected_income != null ? `$${d.projected_income.toFixed(2)}` : "\u2014"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Income Goal + ETA */}
        <IncomeGoalCard />
      </div>
    </div>
  );
}
