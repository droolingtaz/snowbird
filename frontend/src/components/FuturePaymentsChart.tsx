import { useFuturePayments } from "../api/hooks";
import Card from "./Card";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";

interface FutureMonth {
  month: string;
  confirmed: number;
  estimated: number;
  total: number;
}

function formatMonth(m: string) {
  const [y, mo] = m.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[parseInt(mo, 10) - 1]} ${y.slice(2)}`;
}

export default function FuturePaymentsChart() {
  const { data, isLoading } = useFuturePayments(12);

  if (isLoading) {
    return (
      <Card title="Future Payments (12M)">
        <div className="h-52 animate-pulse bg-surface-3 rounded" />
      </Card>
    );
  }

  const months: FutureMonth[] = data?.months ?? [];

  if (months.length === 0) {
    return (
      <Card title="Future Payments (12M)">
        <p className="text-text-tertiary text-sm py-8 text-center">No forecast data available</p>
      </Card>
    );
  }

  const chartData = months.map((m) => ({
    name: formatMonth(m.month),
    confirmed: m.confirmed,
    estimated: m.estimated,
  }));

  return (
    <Card title="Future Payments (12M)">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
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
            formatter={(v: number, name: string) => [
              `$${v.toFixed(2)}`,
              name === "confirmed" ? "Confirmed" : "Estimated",
            ]}
          />
          <Legend
            verticalAlign="bottom"
            iconType="square"
            wrapperStyle={{ fontSize: 11 }}
          />
          <Bar dataKey="confirmed" stackId="a" fill="#3b82f6" radius={[0, 0, 0, 0]} name="Confirmed" />
          <Bar dataKey="estimated" stackId="a" fill="#14b8a6" radius={[3, 3, 0, 0]} name="Estimated" />
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
