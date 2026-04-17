import { useReceivedMonthly } from "../api/hooks";
import Card from "./Card";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell, LabelList,
} from "recharts";

interface RecvMonth {
  month: string;
  total: number;
}

function formatMonth(m: string) {
  const [y, mo] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[parseInt(mo, 10) - 1]} ${y.slice(2)}`;
}

export default function ReceivedMonthlyChart() {
  const { data, isLoading } = useReceivedMonthly(12);

  if (isLoading) {
    return (
      <Card title="Dividends Received (12M)">
        <div className="h-52 animate-pulse bg-surface-3 rounded" />
      </Card>
    );
  }

  const months: RecvMonth[] = data?.months ?? [];

  if (months.length === 0) {
    return (
      <Card title="Dividends Received (12M)">
        <p className="text-text-tertiary text-sm py-8 text-center">No dividend history</p>
      </Card>
    );
  }

  const chartData = months.map((m) => ({
    name: formatMonth(m.month),
    total: m.total,
  }));

  return (
    <Card title="Dividends Received (12M)">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 16, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fontSize: 10, fill: "#4a5568" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#4a5568" }}
            tickLine={false}
            axisLine={false}
            width={50}
            tickFormatter={(v) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              background: "#1a1e25",
              border: "1px solid #1e2433",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Received"]}
          />
          <Bar dataKey="total" radius={[3, 3, 0, 0]}>
            {chartData.map((_, idx) => (
              <Cell key={idx} fill="#8b5cf6" />
            ))}
            <LabelList
              dataKey="total"
              position="top"
              style={{ fontSize: 9, fill: "#8b5cf6" }}
              formatter={(v: number) => `$${Math.round(v)}`}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
