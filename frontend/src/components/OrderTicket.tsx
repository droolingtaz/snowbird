import { useState, useEffect } from "react";
import { usePlaceOrder, useMarketSearch, useMarketQuote } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import { clsx } from "clsx";

interface OrderTicketProps {
  defaultSymbol?: string;
}

export default function OrderTicket({ defaultSymbol = "" }: OrderTicketProps) {
  const accountId = useAuthStore((s) => s.accountId);
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [searchQ, setSearchQ] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [orderType, setOrderType] = useState("market");
  const [useNotional, setUseNotional] = useState(false);
  const [qty, setQty] = useState("");
  const [notional, setNotional] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [tif, setTif] = useState("day");
  const [useBracket, setUseBracket] = useState(false);
  const [takeProfit, setTakeProfit] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");

  const { data: searchResults = [] } = useMarketSearch(searchQ);
  const { data: quote } = useMarketQuote(symbol);
  const placeOrder = usePlaceOrder();

  const price = quote?.last_price ?? quote?.ask_price;
  const estimatedCost = price
    ? useNotional
      ? parseFloat(notional) || 0
      : (parseFloat(qty) || 0) * price
    : null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!confirmed) { setConfirmed(true); return; }
    if (!accountId) return;
    setError("");
    try {
      await placeOrder.mutateAsync({
        account_id: accountId,
        symbol: symbol.toUpperCase(),
        side,
        type: orderType,
        qty: !useNotional && qty ? parseFloat(qty) : undefined,
        notional: useNotional && notional ? parseFloat(notional) : undefined,
        time_in_force: tif,
        limit_price: limitPrice ? parseFloat(limitPrice) : undefined,
        stop_price: stopPrice ? parseFloat(stopPrice) : undefined,
        bracket: useBracket ? {
          take_profit: takeProfit ? parseFloat(takeProfit) : undefined,
          stop_loss: stopLoss ? parseFloat(stopLoss) : undefined,
        } : undefined,
      });
      // Reset
      setQty(""); setNotional(""); setLimitPrice(""); setStopPrice("");
      setTakeProfit(""); setStopLoss(""); setConfirmed(false);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Order failed");
      setConfirmed(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* Symbol */}
      <div>
        <label className="label">Symbol</label>
        <div className="relative">
          <input
            className="input"
            placeholder="AAPL, TSLA…"
            value={symbol || searchQ}
            onChange={(e) => {
              setSearchQ(e.target.value);
              setSymbol("");
            }}
          />
          {searchResults.length > 0 && !symbol && searchQ && (
            <div className="absolute z-20 top-full left-0 right-0 mt-1 bg-surface-2 border border-border rounded-lg overflow-hidden shadow-card-lg max-h-48 overflow-y-auto">
              {searchResults.slice(0, 8).map((r: any) => (
                <button
                  key={r.symbol}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-surface-3 transition-colors"
                  onClick={() => { setSymbol(r.symbol); setSearchQ(r.symbol); }}
                >
                  <span className="font-medium">{r.symbol}</span>
                  {r.name && <span className="ml-2 text-text-secondary text-xs">{r.name}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
        {price && (
          <p className="text-xs text-text-secondary mt-1 mono">
            Last: ${price.toFixed(2)}
          </p>
        )}
      </div>

      {/* Side */}
      <div>
        <label className="label">Side</label>
        <div className="flex gap-2">
          {(["buy", "sell"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setSide(s)}
              className={clsx(
                "flex-1 py-2 rounded-lg text-sm font-medium capitalize transition-colors",
                side === s
                  ? s === "buy" ? "bg-green-profit text-white" : "bg-red-loss text-white"
                  : "bg-surface-2 text-text-secondary hover:bg-surface-3"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Order type */}
      <div>
        <label className="label">Order Type</label>
        <select
          className="input"
          value={orderType}
          onChange={(e) => setOrderType(e.target.value)}
        >
          <option value="market">Market</option>
          <option value="limit">Limit</option>
          <option value="stop">Stop</option>
          <option value="stop_limit">Stop Limit</option>
        </select>
      </div>

      {/* Qty / Notional toggle */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <label className="label mb-0">
            {useNotional ? "Dollar Amount" : "Quantity"}
          </label>
          <button
            type="button"
            onClick={() => setUseNotional(!useNotional)}
            className="text-2xs text-accent hover:text-accent-hover"
          >
            Switch to {useNotional ? "shares" : "dollars"}
          </button>
        </div>
        <input
          className="input"
          type="number"
          step="any"
          min="0"
          placeholder={useNotional ? "100.00" : "10"}
          value={useNotional ? notional : qty}
          onChange={(e) => useNotional ? setNotional(e.target.value) : setQty(e.target.value)}
          required
        />
      </div>

      {/* Limit/Stop prices */}
      {(orderType === "limit" || orderType === "stop_limit") && (
        <div>
          <label className="label">Limit Price</label>
          <input className="input" type="number" step="any" value={limitPrice} onChange={(e) => setLimitPrice(e.target.value)} required />
        </div>
      )}
      {(orderType === "stop" || orderType === "stop_limit") && (
        <div>
          <label className="label">Stop Price</label>
          <input className="input" type="number" step="any" value={stopPrice} onChange={(e) => setStopPrice(e.target.value)} required />
        </div>
      )}

      {/* TIF */}
      <div>
        <label className="label">Time in Force</label>
        <select className="input" value={tif} onChange={(e) => setTif(e.target.value)}>
          <option value="day">Day</option>
          <option value="gtc">GTC</option>
          <option value="ioc">IOC</option>
          <option value="fok">FOK</option>
        </select>
      </div>

      {/* Bracket */}
      <div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={useBracket}
            onChange={(e) => setUseBracket(e.target.checked)}
            className="accent-accent"
          />
          <span className="text-sm text-text-secondary">Bracket order (take profit + stop loss)</span>
        </label>
        {useBracket && (
          <div className="mt-3 space-y-3 pl-4 border-l-2 border-accent/20">
            <div>
              <label className="label">Take Profit Price</label>
              <input className="input" type="number" step="any" value={takeProfit} onChange={(e) => setTakeProfit(e.target.value)} />
            </div>
            <div>
              <label className="label">Stop Loss Price</label>
              <input className="input" type="number" step="any" value={stopLoss} onChange={(e) => setStopLoss(e.target.value)} />
            </div>
          </div>
        )}
      </div>

      {/* Estimated cost */}
      {estimatedCost !== null && estimatedCost > 0 && (
        <div className="bg-surface-2 rounded-lg px-3 py-2 text-sm">
          <span className="text-text-secondary">Est. {side === "buy" ? "cost" : "proceeds"}:</span>
          <span className="ml-2 font-semibold mono">
            ${estimatedCost.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>
        </div>
      )}

      {error && <p className="text-xs text-red-loss">{error}</p>}

      {placeOrder.isSuccess && (
        <p className="text-xs text-green-profit">Order submitted successfully!</p>
      )}

      <button
        type="submit"
        disabled={!symbol || placeOrder.isPending || !accountId}
        className={clsx(
          "w-full py-2.5 rounded-lg text-sm font-semibold transition-colors",
          confirmed
            ? "bg-orange-500 text-white hover:bg-orange-600"
            : side === "buy"
              ? "bg-green-profit text-white hover:bg-green-600"
              : "bg-red-loss text-white hover:bg-red-600"
        )}
      >
        {placeOrder.isPending
          ? "Placing…"
          : confirmed
            ? `Confirm ${side.toUpperCase()} ${symbol}`
            : `Review ${side.toUpperCase()} Order`}
      </button>
      {confirmed && (
        <button
          type="button"
          onClick={() => setConfirmed(false)}
          className="w-full text-xs text-text-secondary hover:text-text-primary"
        >
          Cancel
        </button>
      )}
    </form>
  );
}
