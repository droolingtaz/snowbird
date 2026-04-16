import { clsx } from "clsx";

interface StatTileProps {
  label: string;
  value: string | number;
  change?: number;
  changePct?: number;
  prefix?: string;
  suffix?: string;
  loading?: boolean;
}

function fmt(n: number, decimals = 2) {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export default function StatTile({
  label, value, change, changePct, prefix = "$", loading = false
}: StatTileProps) {
  const isPositive = (change ?? 0) >= 0;
  const isNegative = (change ?? 0) < 0;

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-3 w-20 bg-surface-3 rounded mb-3" />
        <div className="h-7 w-32 bg-surface-3 rounded" />
      </div>
    );
  }

  return (
    <div className="card">
      <p className="text-xs font-medium text-text-secondary uppercase tracking-wider mb-1.5">
        {label}
      </p>
      <p className="text-2xl font-semibold mono text-text-primary">
        {typeof value === "number" ? `${prefix}${fmt(value)}` : value}
      </p>
      {change !== undefined && (
        <p className={clsx("text-xs mono mt-1", isPositive && "stat-up", isNegative && "stat-down")}>
          {isPositive ? "+" : ""}
          {prefix}{fmt(change)} {changePct !== undefined ? `(${isPositive ? "+" : ""}${fmt(changePct, 2)}%)` : ""}
        </p>
      )}
    </div>
  );
}
