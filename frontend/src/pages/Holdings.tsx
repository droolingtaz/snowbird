import { useHoldings, useSyncAccount } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "../components/Card";
import HoldingsTable from "../components/HoldingsTable";
import { RefreshCw } from "lucide-react";

export default function Holdings() {
  const accountId = useAuthStore((s) => s.accountId);
  const { data: holdings = [], isLoading } = useHoldings();
  const sync = useSyncAccount();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Holdings</h1>
        <div className="flex items-center gap-2 text-sm text-text-secondary">
          <span>{holdings.length} positions</span>
          {accountId && (
            <button
              onClick={() => sync.mutate(accountId)}
              disabled={sync.isPending}
              className="btn-ghost gap-1 py-1 px-2 text-xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${sync.isPending ? "animate-spin" : ""}`} />
              Sync
            </button>
          )}
        </div>
      </div>

      <Card>
        {isLoading ? (
          <div className="space-y-3 animate-pulse">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 bg-surface-2 rounded" />
            ))}
          </div>
        ) : (
          <HoldingsTable holdings={holdings} />
        )}
      </Card>
    </div>
  );
}
