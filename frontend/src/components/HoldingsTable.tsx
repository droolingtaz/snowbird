import { clsx } from "clsx";

interface Holding {
  symbol: string;
  name?: string;
  qty: number;
  avg_entry_price?: number;
  current_price?: number;
  market_value?: number;
  unrealized_pl?: number;
  unrealized_plpc?: number;
  weight_pct: number;
  sector?: string;
  bucket_names: string[];
}

function fmt(n?: number, decimals = 2, prefix = "$") {
  if (n == null) return "—";
  return `${prefix}${n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

export default function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  if (!holdings?.length) {
    return (
      <div className="text-center py-12 text-text-tertiary text-sm">
        No positions yet. Sync your account or add Alpaca credentials.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="table-auto">
        <thead>
          <tr>
            <th>Symbol</th>
            <th className="text-right">Qty</th>
            <th className="text-right">Avg Cost</th>
            <th className="text-right">Price</th>
            <th className="text-right">Mkt Value</th>
            <th className="text-right">Unrealized P/L</th>
            <th className="text-right">Weight</th>
            <th>Sector</th>
            <th>Buckets</th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const isUp = (h.unrealized_pl ?? 0) >= 0;
            return (
              <tr key={h.symbol}>
                <td>
                  <div>
                    <span className="font-semibold text-text-primary">{h.symbol}</span>
                    {h.name && (
                      <span className="block text-2xs text-text-tertiary truncate max-w-[120px]">{h.name}</span>
                    )}
                  </div>
                </td>
                <td className="text-right mono">{h.qty.toLocaleString()}</td>
                <td className="text-right mono">{fmt(h.avg_entry_price)}</td>
                <td className="text-right mono">{fmt(h.current_price)}</td>
                <td className="text-right mono font-medium">{fmt(h.market_value)}</td>
                <td className={clsx("text-right mono", isUp ? "stat-up" : "stat-down")}>
                  {fmt(h.unrealized_pl)}
                  {h.unrealized_plpc != null && (
                    <span className="block text-2xs">
                      {isUp ? "+" : ""}{(h.unrealized_plpc * 100).toFixed(2)}%
                    </span>
                  )}
                </td>
                <td className="text-right mono">{h.weight_pct.toFixed(1)}%</td>
                <td className="text-text-secondary text-xs">{h.sector ?? "—"}</td>
                <td>
                  <div className="flex flex-wrap gap-1">
                    {h.bucket_names.map((b) => (
                      <span key={b} className="badge bg-accent/10 text-accent text-2xs">{b}</span>
                    ))}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
