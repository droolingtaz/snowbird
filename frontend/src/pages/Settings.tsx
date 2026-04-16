import { useState } from "react";
import { useAccounts, useCreateAccount, useDeleteAccount, useTestAccount } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "../components/Card";
import { Plus, Trash2, CheckCircle2, XCircle, RefreshCw } from "lucide-react";
import { clsx } from "clsx";

function AddAccountForm({ onDone }: { onDone: () => void }) {
  const [label, setLabel] = useState("");
  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [error, setError] = useState("");
  const createAccount = useCreateAccount();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await createAccount.mutateAsync({ label, mode, api_key: apiKey, api_secret: apiSecret });
      onDone();
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Failed to add account");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label">Label</label>
          <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="My Paper Account" required />
        </div>
        <div>
          <label className="label">Mode</label>
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value as any)}>
            <option value="paper">Paper</option>
            <option value="live">Live</option>
          </select>
        </div>
      </div>
      <div>
        <label className="label">API Key ID</label>
        <input className="input font-mono text-xs" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="PKXXXXXXXXXXXXXXXX" required />
      </div>
      <div>
        <label className="label">Secret Key</label>
        <input className="input font-mono text-xs" type="password" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} placeholder="••••••••••••••••••••" required />
      </div>
      {error && <p className="text-xs text-red-loss">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" className="btn-primary flex-1" disabled={createAccount.isPending}>
          {createAccount.isPending ? "Adding…" : "Add Account"}
        </button>
        <button type="button" onClick={onDone} className="btn-ghost flex-1">Cancel</button>
      </div>
    </form>
  );
}

export default function Settings() {
  const { data: accounts = [], isLoading } = useAccounts();
  const deleteAccount = useDeleteAccount();
  const testAccount = useTestAccount();
  const { accountId, setAccountId } = useAuthStore();
  const [showAdd, setShowAdd] = useState(false);
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; message: string }>>({});

  async function handleTest(id: number) {
    const result = await testAccount.mutateAsync(id);
    setTestResults((r) => ({ ...r, [id]: result }));
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-lg font-semibold">Settings</h1>

      {/* Alpaca Accounts */}
      <Card title="Alpaca Accounts">
        {isLoading ? (
          <div className="animate-pulse space-y-3">
            {[1, 2].map((i) => <div key={i} className="h-14 bg-surface-2 rounded" />)}
          </div>
        ) : (
          <div className="space-y-3">
            {(accounts as any[]).length === 0 && !showAdd && (
              <p className="text-text-tertiary text-sm">No accounts yet. Add your Alpaca API keys below.</p>
            )}

            {(accounts as any[]).map((acct) => (
              <div key={acct.id} className="flex items-start justify-between bg-surface-2 rounded-lg p-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{acct.label}</span>
                    <span className={clsx(
                      "badge",
                      acct.mode === "paper" ? "badge-paper" : "badge-live"
                    )}>
                      {acct.mode}
                    </span>
                    {acct.id === accountId && (
                      <span className="badge bg-accent/10 text-accent">active</span>
                    )}
                  </div>
                  <p className="text-xs text-text-tertiary font-mono mt-0.5">{acct.api_key}</p>
                  {acct.last_sync_at && (
                    <p className="text-2xs text-text-tertiary mt-0.5">
                      Last sync: {new Date(acct.last_sync_at).toLocaleString()}
                    </p>
                  )}
                  {testResults[acct.id] && (
                    <div className={clsx(
                      "flex items-center gap-1 text-xs mt-1",
                      testResults[acct.id].ok ? "text-green-profit" : "text-red-loss"
                    )}>
                      {testResults[acct.id].ok
                        ? <CheckCircle2 className="w-3.5 h-3.5" />
                        : <XCircle className="w-3.5 h-3.5" />}
                      {testResults[acct.id].message}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-1 ml-3">
                  <button
                    onClick={() => setAccountId(acct.id)}
                    className={clsx("btn-ghost text-xs py-1 px-2", acct.id === accountId && "text-accent")}
                  >
                    {acct.id === accountId ? "Active" : "Select"}
                  </button>
                  <button
                    onClick={() => handleTest(acct.id)}
                    className="btn-ghost text-xs py-1 px-2"
                    disabled={testAccount.isPending}
                  >
                    <RefreshCw className={clsx("w-3 h-3", testAccount.isPending && "animate-spin")} />
                  </button>
                  <button
                    onClick={() => {
                      if (confirm("Delete this account? All synced data will be removed.")) {
                        deleteAccount.mutate(acct.id);
                      }
                    }}
                    className="btn-ghost text-xs py-1 px-2 text-red-loss hover:text-red-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}

            {showAdd ? (
              <div className="mt-3 pt-3 border-t border-border">
                <AddAccountForm onDone={() => setShowAdd(false)} />
              </div>
            ) : (
              <button
                onClick={() => setShowAdd(true)}
                className="btn-ghost gap-1.5 text-sm mt-2"
              >
                <Plus className="w-4 h-4" /> Add Account
              </button>
            )}
          </div>
        )}
      </Card>

      {/* Info card */}
      <Card title="Security">
        <div className="text-sm text-text-secondary space-y-2">
          <p>Your Alpaca API secrets are encrypted at rest using Fernet symmetric encryption. Secrets are never stored in plaintext.</p>
          <p>This application is intended for self-hosted, local network use. Do not expose it to the internet without a reverse proxy and TLS.</p>
        </div>
      </Card>

      <Card title="Disclaimer">
        <p className="text-sm text-text-secondary">
          Snowbird is educational software. Live trading involves real financial risk.
          The authors are not responsible for any financial losses.
          Always paper-trade first and understand your risk before trading live.
        </p>
      </Card>
    </div>
  );
}
