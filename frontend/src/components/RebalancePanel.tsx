import { useState } from "react";
import { useRebalancePreview, useExecuteRebalance } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import { clsx } from "clsx";
import { TrendingUp, TrendingDown } from "lucide-react";

export default function RebalancePanel({ onClose }: { onClose: () => void }) {
  const accountId = useAuthStore((s) => s.accountId);
  const [cashToDeploy, setCashToDeploy] = useState(0);
  const [dryRun, setDryRun] = useState(true);
  const [executed, setExecuted] = useState(false);

  const { data: preview, isLoading } = useRebalancePreview(cashToDeploy);
  const execute = useExecuteRebalance();

  async function handleExecute() {
    if (!accountId || !preview?.orders?.length) return;
    const result = await execute.mutateAsync({
      account_id: accountId,
      orders: preview.orders,
      dry_run: dryRun,
    });
    if (!dryRun) setExecuted(true);
  }

  if (executed) {
    return (
      <div className="text-center py-8">
        <p className="text-green-profit font-medium">Rebalance orders placed!</p>
        <button onClick={onClose} className="btn-ghost mt-4">Close</button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <label className="label">Cash to Deploy ($)</label>
          <input
            className="input"
            type="number"
            min="0"
            step="100"
            value={cashToDeploy || ""}
            onChange={(e) => setCashToDeploy(parseFloat(e.target.value) || 0)}
            placeholder="0"
          />
        </div>
        <div className="text-right text-xs text-text-secondary pt-5">
          Available: ${preview?.cash_available?.toFixed(2) ?? "—"}
        </div>
      </div>

      {isLoading && (
        <div className="animate-pulse space-y-2">
          {[1, 2, 3].map((i) => <div key={i} className="h-10 bg-surface-2 rounded" />)}
        </div>
      )}

      {preview && !isLoading && (
        <>
          {preview.orders.length === 0 ? (
            <p className="text-center text-text-tertiary text-sm py-6">Portfolio is already balanced ✓</p>
          ) : (
            <>
              <div className="flex gap-4 text-xs text-text-secondary bg-surface-2 rounded-lg px-3 py-2">
                <span>Buys: <strong className="text-green-profit">${preview.total_buys.toFixed(2)}</strong></span>
                <span>Sells: <strong className="text-red-loss">${preview.total_sells.toFixed(2)}</strong></span>
                <span>{preview.orders.length} orders</span>
              </div>

              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {preview.orders.map((o: any, i: number) => (
                  <div key={i} className="flex items-center justify-between bg-surface-2 rounded-lg px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      {o.side === "buy"
                        ? <TrendingUp className="w-4 h-4 text-green-profit" />
                        : <TrendingDown className="w-4 h-4 text-red-loss" />}
                      <span className="font-medium">{o.symbol}</span>
                      {o.bucket_name && <span className="text-2xs text-text-tertiary">{o.bucket_name}</span>}
                    </div>
                    <div className="text-right">
                      <span className={clsx("font-medium mono", o.side === "buy" ? "text-green-profit" : "text-red-loss")}>
                        {o.side.toUpperCase()}
                      </span>
                      <span className="ml-2 text-text-secondary mono">
                        {o.qty ? `${o.qty} shares` : ""} ${o.notional.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {preview.orders.length > 0 && (
            <>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={!dryRun}
                  onChange={(e) => setDryRun(!e.target.checked)}
                  className="accent-accent"
                />
                <span className="text-sm text-text-secondary">Execute live (uncheck = dry run only)</span>
              </label>

              <div className="flex gap-2">
                <button
                  onClick={handleExecute}
                  disabled={execute.isPending}
                  className={clsx("btn flex-1", dryRun ? "btn-ghost border border-border" : "btn-primary")}
                >
                  {execute.isPending ? "Executing…" : dryRun ? "Simulate" : "Execute Rebalance"}
                </button>
                <button onClick={onClose} className="btn-ghost flex-1">Cancel</button>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
