import { useState } from "react";
import {
  usePortfolioSummary, usePortfolioHistory, usePortfolioAllocation,
  useHoldings, useDividendCalendar,
  useIrr, usePassiveIncome, useMovers,
} from "../api/hooks";
import { useAuthStore } from "../store/auth";
import StatTile from "../components/StatTile";
import Card from "../components/Card";
import PerformanceChart from "../components/PerformanceChart";
import AllocationDonut from "../components/AllocationDonut";
import { clsx } from "clsx";
import { format, addDays } from "date-fns";
import {
  TrendingUp, TrendingDown, DollarSign, ArrowUpRight, ArrowDownRight, HelpCircle,
} from "lucide-react";

function fmt(n?: number) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2 });
}

function fmtPct(n?: number | null) {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
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

  const today = format(new Date(), "yyyy-MM-dd");
  const in90 = format(addDays(new Date(), 90), "yyyy-MM-dd");
  const { data: divCalendar = [] } = useDividendCalendar(today, in90);

  // New KPI data
  const { data: irr1Y, isLoading: irrLoading } = useIrr("1Y");
  const { data: irrAll } = useIrr("ALL");
  const { data: income, isLoading: incomeLoading } = usePassiveIncome();
  const { data: moversData, isLoading: moversLoading } = useMovers(5);

  // Top movers (legacy — from holdings)
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

      {/* KPI tiles: IRR + Passive Income */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* IRR Tile */}
        {irrLoading ? (
          <div className="card animate-pulse">
            <div className="h-3 w-20 bg-surface-3 rounded mb-3" />
            <div className="h-7 w-32 bg-surface-3 rounded" />
          </div>
        ) : (
          <div className="card">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Internal Rate of Return
              </p>
              <HelpCircle className="w-3.5 h-3.5 text-text-tertiary" />
            </div>
            <p className={clsx(
              "text-2xl font-semibold mono",
              irr1Y?.irr != null && irr1Y.irr >= 0 ? "text-green-profit" : "text-red-loss",
              irr1Y?.irr == null && "text-text-primary",
            )}>
              {irr1Y?.irr != null ? fmtPct(irr1Y.irr * 100) : "—"}
            </p>
            <p className="text-xs text-text-tertiary mt-1 mono">
              1Y{irrAll?.irr != null ? ` · lifetime ${fmtPct(irrAll.irr * 100)}` : ""}
            </p>
          </div>
        )}

        {/* Passive Income Tile */}
        {incomeLoading ? (
          <div className="card animate-pulse">
            <div className="h-3 w-20 bg-surface-3 rounded mb-3" />
            <div className="h-7 w-32 bg-surface-3 rounded" />
          </div>
        ) : (
          <div className="card">
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">
                Passive Income
              </p>
              <DollarSign className="w-3.5 h-3.5 text-text-tertiary" />
            </div>
            <p className="text-2xl font-semibold mono text-green-profit">
              {income?.current_yield_pct != null ? `${income.current_yield_pct.toFixed(2)}%` : "—"}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-text-tertiary mono">
                ${fmt(income?.annual_income)} annually
              </span>
              {income?.yoy_growth_pct != null && (
                <span className={clsx(
                  "inline-flex items-center text-2xs mono font-medium",
                  income.yoy_growth_pct >= 0 ? "text-green-profit" : "text-red-loss",
                )}>
                  {income.yoy_growth_pct >= 0 ? (
                    <ArrowUpRight className="w-3 h-3 mr-0.5" />
                  ) : (
                    <ArrowDownRight className="w-3 h-3 mr-0.5" />
                  )}
                  {Math.abs(income.yoy_growth_pct).toFixed(1)}% YoY
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Performance chart */}
      <Card title="Portfolio Value">
        <PerformanceChart
          data={history?.points ?? []}
          loading={histLoading}
          period={period}
          onPeriodChange={setPeriod}
          showBenchmark={showBenchmark}
          onBenchmarkToggle={() => setShowBenchmark(!showBenchmark)}
        />
      </Card>

      {/* Gainers / Losers row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Top Day Gainers */}
        <Card
          title="Top Day Gainers"
          action={<TrendingUp className="w-4 h-4 text-green-profit" />}
        >
          {moversLoading ? (
            <div className="space-y-3 animate-pulse">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="flex justify-between">
                  <div className="h-4 w-16 bg-surface-3 rounded" />
                  <div className="h-4 w-20 bg-surface-3 rounded" />
                </div>
              ))}
            </div>
          ) : (moversData?.gainers ?? []).length === 0 ? (
            <p className="text-text-tertiary text-sm py-4 text-center">No gainers today</p>
          ) : (
            <div className="space-y-2">
              {(moversData?.gainers ?? []).map((m: any) => (
                <div key={m.symbol} className="flex items-center justify-between">
                  <div className="min-w-0">
                    <span className="text-sm font-medium">{m.symbol}</span>
                    {m.name && (
                      <span className="ml-1.5 text-2xs text-text-tertiary truncate">{m.name}</span>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0 ml-2">
                    <span className="text-sm mono font-medium text-green-profit">
                      {m.change_pct != null ? fmtPct(m.change_pct) : "—"}
                    </span>
                    {m.change_usd != null && (
                      <span className="ml-1.5 text-2xs mono text-text-tertiary">
                        +${Math.abs(m.change_usd).toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Top Day Losers */}
        <Card
          title="Top Day Losers"
          action={<TrendingDown className="w-4 h-4 text-red-loss" />}
        >
          {moversLoading ? (
            <div className="space-y-3 animate-pulse">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="flex justify-between">
                  <div className="h-4 w-16 bg-surface-3 rounded" />
                  <div className="h-4 w-20 bg-surface-3 rounded" />
                </div>
              ))}
            </div>
          ) : (moversData?.losers ?? []).length === 0 ? (
            <p className="text-text-tertiary text-sm py-4 text-center">No losers today</p>
          ) : (
            <div className="space-y-2">
              {(moversData?.losers ?? []).map((m: any) => (
                <div key={m.symbol} className="flex items-center justify-between">
                  <div className="min-w-0">
                    <span className="text-sm font-medium">{m.symbol}</span>
                    {m.name && (
                      <span className="ml-1.5 text-2xs text-text-tertiary truncate">{m.name}</span>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0 ml-2">
                    <span className="text-sm mono font-medium text-red-loss">
                      {m.change_pct != null ? fmtPct(m.change_pct) : "—"}
                    </span>
                    {m.change_usd != null && (
                      <span className="ml-1.5 text-2xs mono text-text-tertiary">
                        -${Math.abs(m.change_usd).toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Bottom row */}
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

        {/* Top movers (all-time unrealized) */}
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

        {/* Upcoming dividends */}
        <Card title="Upcoming Dividends" className="lg:col-span-1">
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
                    {d.projected_income != null ? `$${d.projected_income.toFixed(2)}` : "—"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
