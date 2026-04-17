import { useGrowthYoY } from "../api/hooks";
import Card from "./Card";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Legend,
} from "recharts";

interface YearData {
  year: number;
  months: { month: number; total: number }[];
}

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const YEAR_COLORS = ["#6366f1", "#22c55e", "#f59e0b"];

export default function GrowthYoYChart() {
  const { data, isLoading } = useGrowthYoY(3);

  if (isLoading) {
    return (
      <Card title="Dividend Growth YoY">
        <div className="h-52 animate-pulse bg-surface-3 rounded" />
      </Card>
    );
  }

  const years: YearData[] = data?.years ?? [];

  if (years.length === 0) {
    return (
      <Card title="Dividend Growth YoY">
        <p className="text-text-tertiary text-sm py-8 text-center">No data available</p>
      </Card>
    );
  }

  // Build chart data: one row per month (1-12), columns for each year
  const chartData = MONTH_LABELS.map((label, idx) => {
    const row: Record<string, string | number> = { name: label };
    for (const yr of years) {
      const monthData = yr.months.find((m) => m.month === idx + 1);
      row[String(yr.year)] = monthData?.total ?? 0;
    }
    return row;
  });

  return (
    <Card title="Dividend Growth YoY">
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
            formatter={(v: number, name: string) => [`$${v.toFixed(2)}`, name]}
          />
          <Legend
            verticalAlign="bottom"
            iconType="square"
            wrapperStyle={{ fontSize: 11 }}
          />
          {years.map((yr, i) => (
            <Bar
              key={yr.year}
              dataKey={String(yr.year)}
              fill={YEAR_COLORS[i % YEAR_COLORS.length]}
              radius={[3, 3, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
