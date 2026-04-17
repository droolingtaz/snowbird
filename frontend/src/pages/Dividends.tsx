import { useState } from "react";
import {
  useDividendForecast, useDividendCalendar, useDividendsBySymbol, useDividendHistory
} from "../api/hooks";
import Card from "../components/Card";
import DividendCalendar from "../components/DividendCalendar";
import FuturePaymentsChart from "../components/FuturePaymentsChart";
import ReceivedMonthlyChart from "../components/ReceivedMonthlyChart";
import GrowthYoYChart from "../components/GrowthYoYChart";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format, addDays } from "date-fns";

const today = format(new Date(), "yyyy-MM-dd");
const in12m = format(addDays(new Date(), 365), "yyyy-MM-dd");

function fmt(n?: number | null) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2 });
}

export default function Dividends() {
  const [year, setYear] = useState(new Date().getFullYear());
  const { data: forecast } = useDividendForecast();
  const { data: calendar = [] } = useDividendCalendar(today, in12m);
  const { data: bySymbol = [] } = useDividendsBySymbol();
  const { data: history = [] } = useDividendHistory(year);

  const ytdTotal = (history as any[]).reduce((s: number, d: any) => s + (d.net_amount || 0), 0);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Dividends</h1>
        <div className="flex items-center gap-2">
          <label className="text-xs text-text-secondary">Year:</label>
          <select
            className="input py-1 w-24"
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
          >
            {[0, 1, 2, 3].map((i) => {
              const y = new Date().getFullYear() - i;
              return <option key={y} value={y}>{y}</option>;
            })}
          </select>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="card">
          <p className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">YTD Received</p>
          <p className="text-xl font-semibold mono text-green-profit">${fmt(ytdTotal)}</p>
        </div>
        <div className="card">
          <p className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Forward 12M</p>
          <p className="text-xl font-semibold mono">${fmt(forecast?.annual_total)}</p>
        </div>
        <div className="card">
          <p className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Yield on Cost</p>
          <p className="text-xl font-semibold mono">
            {forecast?.yield_on_cost != null ? `${(forecast.yield_on_cost * 100).toFixed(2)}%` : "—"}
          </p>
        </div>
        <div className="card">
          <p className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Forward Yield</p>
          <p className="text-xl font-semibold mono">
            {forecast?.forward_yield != null ? `${(forecast.forward_yield * 100).toFixed(2)}%` : "—"}
          </p>
        </div>
      </div>

      {/* 12M forecast bar chart */}
      {forecast?.monthly?.length > 0 && (
        <Card title="12-Month Income Forecast">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={forecast.monthly} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false} width={50} tickFormatter={(v) => `$${v.toFixed(0)}`} />
              <Tooltip
                contentStyle={{ background: "#1a1e25", border: "1px solid #1e2433", borderRadius: 8, fontSize: 12 }}
                formatter={(v: any) => [`$${Number(v).toFixed(2)}`, "Projected Income"]}
              />
              <Bar dataKey="projected_income" fill="#22c55e" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Dividend charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <FuturePaymentsChart />
        <ReceivedMonthlyChart />
      </div>

      <GrowthYoYChart />

      {/* Calendar */}
      <Card title="Dividend Calendar (next 12 months)">
        <DividendCalendar items={calendar} />
      </Card>

      {/* By symbol */}
      {bySymbol.length > 0 && (
        <Card title="By Symbol">
          <div className="overflow-x-auto">
            <table className="table-auto">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th className="text-right">Total Received</th>
                  <th className="text-right">YTD</th>
                  <th className="text-right">Ann. DPS</th>
                  <th>Frequency</th>
                  <th className="text-right">Projected Annual</th>
                </tr>
              </thead>
              <tbody>
                {(bySymbol as any[]).map((s) => (
                  <tr key={s.symbol}>
                    <td className="font-semibold">{s.symbol}</td>
                    <td className="text-right mono">${fmt(s.total_received)}</td>
                    <td className="text-right mono text-green-profit">${fmt(s.ytd_received)}</td>
                    <td className="text-right mono">{s.annual_dps != null ? `$${fmt(s.annual_dps)}` : "—"}</td>
                    <td className="text-text-secondary capitalize">{s.frequency ?? "—"}</td>
                    <td className="text-right mono">{s.projected_annual != null ? `$${fmt(s.projected_annual)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
