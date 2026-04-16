import { useAccounts, useMarketClock, useSyncAccount } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import { clsx } from "clsx";
import { RefreshCw, LogOut, Circle } from "lucide-react";

export default function Topbar() {
  const { data: accounts = [] } = useAccounts();
  const { data: clock } = useMarketClock();
  const { accountId, setAccountId, logout } = useAuthStore();
  const sync = useSyncAccount();

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border bg-surface-1 flex-shrink-0">
      {/* Account switcher */}
      <div className="flex items-center gap-2">
        {accounts.length === 0 && (
          <span className="text-xs text-text-tertiary">No accounts — add one in Settings</span>
        )}
        {accounts.map((acct: { id: number; label: string; mode: string }) => (
          <button
            key={acct.id}
            onClick={() => setAccountId(acct.id)}
            className={clsx(
              "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors",
              acct.id === accountId
                ? acct.mode === "paper"
                  ? "bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/40"
                  : "bg-green-500/20 text-green-400 ring-1 ring-green-500/40"
                : "text-text-secondary hover:bg-surface-2"
            )}
          >
            <Circle
              className={clsx(
                "w-2 h-2 fill-current",
                acct.mode === "paper" ? "text-blue-400" : "text-green-400"
              )}
            />
            {acct.label}
            <span className={clsx(
              "text-2xs uppercase",
              acct.mode === "paper" ? "text-blue-400/70" : "text-green-400/70"
            )}>
              {acct.mode}
            </span>
          </button>
        ))}
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {/* Market status */}
        {clock && (
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <div className={clsx(
              "w-1.5 h-1.5 rounded-full",
              clock.is_open ? "bg-green-profit animate-pulse" : "bg-text-tertiary"
            )} />
            {clock.is_open ? "Market Open" : "Market Closed"}
          </div>
        )}

        {/* Sync button */}
        {accountId && (
          <button
            onClick={() => sync.mutate(accountId)}
            disabled={sync.isPending}
            className="btn-ghost p-1.5 rounded-lg"
            title="Sync now"
          >
            <RefreshCw className={clsx("w-3.5 h-3.5", sync.isPending && "animate-spin")} />
          </button>
        )}

        {/* Logout */}
        <button
          onClick={logout}
          className="btn-ghost p-1.5 rounded-lg"
          title="Logout"
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    </header>
  );
}
