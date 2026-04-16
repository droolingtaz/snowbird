import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

interface Item {
  label: string;
  value: number;
  pct: number;
}

const COLORS = [
  "#4f7cff", "#22c55e", "#f97316", "#a855f7", "#14b8a6",
  "#eab308", "#ec4899", "#06b6d4", "#8b5cf6", "#84cc16",
];

function CustomTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const { name, value, payload: p } = payload[0];
  return (
    <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-xs shadow-card-lg">
      <p className="font-medium text-text-primary">{name}</p>
      <p className="text-text-secondary">${value.toLocaleString("en-US", { minimumFractionDigits: 0 })}</p>
      <p className="text-accent">{p.pct.toFixed(1)}%</p>
    </div>
  );
}

export default function AllocationDonut({ items }: { items: Item[] }) {
  if (!items?.length) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-text-tertiary">
        No holdings to display
      </div>
    );
  }

  const top8 = items.slice(0, 8);
  const other = items.slice(8);
  const otherValue = other.reduce((s, i) => s + i.value, 0);
  const otherPct = other.reduce((s, i) => s + i.pct, 0);
  const displayItems = otherValue > 0
    ? [...top8, { label: "Other", value: otherValue, pct: otherPct }]
    : top8;

  return (
    <div className="flex items-center gap-4">
      <ResponsiveContainer width={160} height={160}>
        <PieChart>
          <Pie
            data={displayItems}
            cx="50%"
            cy="50%"
            innerRadius={45}
            outerRadius={70}
            dataKey="value"
            nameKey="label"
            strokeWidth={2}
            stroke="#0d0f12"
          >
            {displayItems.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip content={<CustomTooltip />} />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex-1 space-y-1.5 min-w-0">
        {displayItems.slice(0, 6).map((item, i) => (
          <div key={item.label} className="flex items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-1.5 min-w-0">
              <div
                className="w-2 h-2 rounded-sm flex-shrink-0"
                style={{ background: COLORS[i % COLORS.length] }}
              />
              <span className="text-text-secondary truncate">{item.label}</span>
            </div>
            <span className="text-text-primary mono flex-shrink-0">{item.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
