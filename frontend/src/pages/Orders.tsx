import { useState } from "react";
import { useOrders, useCancelOrder, useCancelAllOrders } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "../components/Card";
import { clsx } from "clsx";
import { X, XCircle } from "lucide-react";

function StatusBadge({ status }: { status?: string }) {
  const color = {
    new: "bg-blue-500/20 text-blue-400",
    pending_new: "bg-blue-500/20 text-blue-400",
    accepted: "bg-blue-500/20 text-blue-400",
    held: "bg-yellow-500/20 text-yellow-400",
    partially_filled: "bg-orange-500/20 text-orange-400",
    filled: "bg-green-500/20 text-green-400",
    canceled: "bg-surface-3 text-text-tertiary",
    expired: "bg-surface-3 text-text-tertiary",
    replaced: "bg-surface-3 text-text-tertiary",
  }[status ?? ""] ?? "bg-surface-3 text-text-tertiary";

  return <span className={`badge ${color}`}>{status ?? "—"}</span>;
}

function fmt(n?: number | null) {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2 });
}

export default function Orders() {
  const accountId = useAuthStore((s) => s.accountId);
  const [tab, setTab] = useState<"open" | "closed">("open");
  const { data: orders = [], isLoading } = useOrders(tab);
  const cancelOrder = useCancelOrder();
  const cancelAll = useCancelAllOrders();

  const isOpenTab = tab === "open";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Orders</h1>
        {isOpenTab && (orders as any[]).length > 0 && (
          <button
            onClick={() => cancelAll.mutate()}
            className="btn-danger text-xs gap-1.5"
            disabled={cancelAll.isPending}
          >
            <XCircle className="w-3.5 h-3.5" />
            Cancel All
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-border">
        {(["open", "closed"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px",
              tab === t
                ? "border-accent text-accent"
                : "border-transparent text-text-secondary hover:text-text-primary"
            )}
          >
            {t}
          </button>
        ))}
      </div>

      <Card>
        {isLoading ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2, 3].map((i) => <div key={i} className="h-10 bg-surface-2 rounded" />)}
          </div>
        ) : (orders as any[]).length === 0 ? (
          <div className="text-center py-12 text-text-tertiary text-sm">
            No {tab} orders.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-auto">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Type</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Limit</th>
                  <th>TIF</th>
                  <th>Status</th>
                  <th className="text-right">Filled Avg</th>
                  <th>Submitted</th>
                  {isOpenTab && <th></th>}
                </tr>
              </thead>
              <tbody>
                {(orders as any[]).map((o) => (
                  <tr key={o.id}>
                    <td className="font-semibold">{o.symbol}</td>
                    <td>
                      <span className={clsx(
                        "badge",
                        o.side === "buy" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                      )}>
                        {o.side}
                      </span>
                    </td>
                    <td className="text-text-secondary capitalize">{o.type}</td>
                    <td className="text-right mono">{o.qty ?? (o.notional ? `$${fmt(o.notional)}` : "—")}</td>
                    <td className="text-right mono">{o.limit_price ? `$${fmt(o.limit_price)}` : "—"}</td>
                    <td className="text-text-secondary uppercase text-xs">{o.time_in_force ?? "—"}</td>
                    <td><StatusBadge status={o.status} /></td>
                    <td className="text-right mono">{o.filled_avg_price ? `$${fmt(o.filled_avg_price)}` : "—"}</td>
                    <td className="text-text-secondary text-xs">
                      {o.submitted_at ? new Date(o.submitted_at).toLocaleString() : "—"}
                    </td>
                    {isOpenTab && (
                      <td>
                        <button
                          onClick={() => cancelOrder.mutate({ orderId: o.id, accountId: accountId! })}
                          className="p-1 text-text-tertiary hover:text-red-loss transition-colors"
                          title="Cancel order"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
