import { useState } from "react";
import {
  useReinvestPreview,
  useReinvestSettings,
  useUpdateReinvestSettings,
  useExecuteReinvest,
} from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "./Card";

function fmt(n?: number) {
  if (n == null) return "\u2014";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface ReinvestOrder {
  symbol: string;
  side: string;
  notional: number;
  bucket_name?: string;
  purpose: string;
}

function OrderRow({ o }: { o: ReinvestOrder }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <div>
        <span className="font-medium">{o.symbol}</span>
        <span className="ml-2 text-2xs text-text-tertiary">
          {o.purpose === "tax_reserve" ? "Tax Reserve" : o.bucket_name ?? ""}
        </span>
      </div>
      <span className="mono text-green-profit">${fmt(o.notional)}</span>
    </div>
  );
}

function SettingsPanel({
  settings,
  onClose,
}: {
  settings: any;
  onClose: () => void;
}) {
  const accountId = useAuthStore((s) => s.accountId);
  const update = useUpdateReinvestSettings();
  const [taxRate, setTaxRate] = useState(String(settings?.tax_rate_pct ?? 24));
  const [symbol, setSymbol] = useState(settings?.tax_reserve_symbol ?? "CSHI");
  const [autoEnabled, setAutoEnabled] = useState(
    settings?.auto_reinvest_enabled ?? false,
  );

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    update.mutate(
      {
        account_id: accountId,
        tax_rate_pct: parseFloat(taxRate) || 24,
        tax_reserve_symbol: symbol || "CSHI",
        auto_reinvest_enabled: autoEnabled,
      },
      { onSuccess: onClose },
    );
  };

  return (
    <form onSubmit={handleSave} className="space-y-3">
      <div>
        <label className="text-xs text-text-secondary block mb-1">
          Tax rate (%)
        </label>
        <input
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={taxRate}
          onChange={(e) => setTaxRate(e.target.value)}
          className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label className="text-xs text-text-secondary block mb-1">
          Tax reserve symbol
        </label>
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm"
        />
      </div>
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="auto-reinvest"
          checked={autoEnabled}
          onChange={(e) => setAutoEnabled(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="auto-reinvest" className="text-xs text-text-secondary">
          Auto-reinvest (coming soon)
        </label>
      </div>
      <div className="flex gap-2">
        <button type="submit" className="btn-primary flex-1 text-sm py-1.5">
          Save
        </button>
        <button
          type="button"
          onClick={onClose}
          className="flex-1 text-sm py-1.5 border border-border rounded text-text-secondary hover:text-text-primary"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default function ReinvestCard() {
  const accountId = useAuthStore((s) => s.accountId);
  const { data: preview, isLoading } = useReinvestPreview();
  const { data: settings } = useReinvestSettings();
  const execute = useExecuteReinvest();
  const [showModal, setShowModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [result, setResult] = useState<any>(null);

  if (!accountId) return null;

  if (isLoading) {
    return (
      <Card title="Dividend Reinvestment">
        <div className="animate-pulse bg-surface-2 rounded h-24" />
      </Card>
    );
  }

  const taxRate = settings?.tax_rate_pct ?? 24;
  const taxSymbol = settings?.tax_reserve_symbol ?? "CSHI";
  const cash = preview?.unreinvested_cash ?? 0;

  const handleExecute = () => {
    if (!accountId) return;
    execute.mutate(
      { account_id: accountId, dry_run: false },
      {
        onSuccess: (data) => {
          setResult(data);
        },
      },
    );
  };

  return (
    <Card
      title="Dividend Reinvestment"
      action={
        <button
          onClick={() => setShowSettings(!showSettings)}
          className="text-xs text-text-secondary hover:text-text-primary"
          title="Settings"
        >
          {showSettings ? "Close" : "Settings"}
        </button>
      }
    >
      {showSettings ? (
        <SettingsPanel
          settings={settings}
          onClose={() => setShowSettings(false)}
        />
      ) : (
        <div className="space-y-3">
          {/* Summary stats */}
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between" title="Accumulated dividends since last reinvestment">
              <span className="text-text-secondary">Unreinvested dividends</span>
              <span className="mono font-medium">${fmt(cash)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">
                Tax reserve ({taxRate}%)
              </span>
              <span className="mono font-medium">
                ${fmt(preview?.tax_reserved ?? 0)} &rarr; {taxSymbol}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-secondary">Investable</span>
              <span className="mono font-medium text-green-profit">
                ${fmt(preview?.investable ?? 0)}
              </span>
            </div>
          </div>

          {/* Preview button */}
          {cash > 0 && (
            <button
              onClick={() => {
                setResult(null);
                setShowModal(true);
              }}
              className="btn-primary w-full text-sm py-1.5"
            >
              Preview
            </button>
          )}

          {cash <= 0 && (
            <p className="text-text-tertiary text-xs text-center py-1">
              No dividends to reinvest
            </p>
          )}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-surface border border-border rounded-xl shadow-card-lg w-full max-w-md mx-4 p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold">Reinvestment Plan</h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-text-tertiary hover:text-text-primary text-lg leading-none"
              >
                &times;
              </button>
            </div>

            {result ? (
              <div className="space-y-3">
                <div className="text-sm">
                  <span
                    className={
                      result.status === "executed"
                        ? "text-green-profit font-medium"
                        : "text-red-loss font-medium"
                    }
                  >
                    {result.status === "executed"
                      ? "Orders placed successfully"
                      : `Execution ${result.status}`}
                  </span>
                </div>
                {result.orders_json?.placed?.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs text-text-secondary font-medium">
                      Placed orders
                    </p>
                    {result.orders_json.placed.map((o: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="font-medium">{o.symbol}</span>
                        <span className="mono text-green-profit">
                          ${fmt(o.notional)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {result.error && (
                  <p className="text-xs text-red-loss">{result.error}</p>
                )}
                <button
                  onClick={() => setShowModal(false)}
                  className="btn-primary w-full text-sm py-1.5 mt-2"
                >
                  Close
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Summary */}
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Dividend cash</span>
                    <span className="mono">${fmt(preview?.unreinvested_cash)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">
                      Tax reserve ({taxRate}%)
                    </span>
                    <span className="mono">${fmt(preview?.tax_reserved)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-secondary">Investable</span>
                    <span className="mono text-green-profit">
                      ${fmt(preview?.investable)}
                    </span>
                  </div>
                </div>

                {/* Order list */}
                {preview?.total_orders?.length > 0 && (
                  <div className="space-y-1.5 border-t border-border pt-3">
                    <p className="text-xs text-text-secondary font-medium mb-1">
                      Orders ({preview.total_orders.length})
                    </p>
                    {preview.total_orders.map((o: ReinvestOrder, i: number) => (
                      <OrderRow key={i} o={o} />
                    ))}
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex gap-2 pt-1">
                  <button
                    onClick={handleExecute}
                    disabled={execute.isPending}
                    className="btn-primary flex-1 text-sm py-1.5"
                  >
                    {execute.isPending ? "Placing orders..." : "Reinvest now"}
                  </button>
                  <button
                    onClick={() => setShowModal(false)}
                    className="flex-1 text-sm py-1.5 border border-border rounded text-text-secondary hover:text-text-primary"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
