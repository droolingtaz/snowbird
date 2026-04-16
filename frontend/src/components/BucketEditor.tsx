import { useState } from "react";
import { useCreateBucket, useUpdateBucket } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import { Plus, Trash2 } from "lucide-react";

interface Holding {
  symbol: string;
  target_weight_within_bucket_pct: number;
}

interface BucketEditorProps {
  existingBucket?: {
    id: number;
    name: string;
    target_weight_pct: number;
    color?: string;
    notes?: string;
    holdings: Holding[];
  };
  onClose: () => void;
}

const COLORS = ["#4f7cff", "#22c55e", "#f97316", "#a855f7", "#14b8a6", "#eab308", "#ec4899"];

export default function BucketEditor({ existingBucket, onClose }: BucketEditorProps) {
  const accountId = useAuthStore((s) => s.accountId);
  const createBucket = useCreateBucket();
  const updateBucket = useUpdateBucket();

  const [name, setName] = useState(existingBucket?.name ?? "");
  const [targetWeight, setTargetWeight] = useState(String(existingBucket?.target_weight_pct ?? ""));
  const [color, setColor] = useState(existingBucket?.color ?? COLORS[0]);
  const [notes, setNotes] = useState(existingBucket?.notes ?? "");
  const [holdings, setHoldings] = useState<Holding[]>(existingBucket?.holdings ?? []);
  const [error, setError] = useState("");

  function addHolding() {
    setHoldings([...holdings, { symbol: "", target_weight_within_bucket_pct: 0 }]);
  }

  function removeHolding(i: number) {
    setHoldings(holdings.filter((_, idx) => idx !== i));
  }

  function updateHolding(i: number, field: keyof Holding, value: string | number) {
    const updated = [...holdings];
    updated[i] = { ...updated[i], [field]: value };
    setHoldings(updated);
  }

  const totalHoldingWeight = holdings.reduce((s, h) => s + (Number(h.target_weight_within_bucket_pct) || 0), 0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!accountId) return;

    const data = {
      account_id: accountId,
      name,
      target_weight_pct: parseFloat(targetWeight),
      color,
      notes: notes || undefined,
      holdings: holdings.filter((h) => h.symbol).map((h) => ({
        symbol: h.symbol.toUpperCase(),
        target_weight_within_bucket_pct: Number(h.target_weight_within_bucket_pct),
      })),
    };

    try {
      if (existingBucket) {
        await updateBucket.mutateAsync({ id: existingBucket.id, data });
      } else {
        await createBucket.mutateAsync(data);
      }
      onClose();
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Failed to save bucket");
    }
  }

  const isPending = createBucket.isPending || updateBucket.isPending;

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="label">Bucket Name</label>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} required placeholder="Growth ETFs" />
      </div>

      <div>
        <label className="label">Target Weight % of Portfolio</label>
        <input className="input" type="number" step="0.01" min="0" max="100" value={targetWeight} onChange={(e) => setTargetWeight(e.target.value)} required placeholder="30" />
      </div>

      <div>
        <label className="label">Color</label>
        <div className="flex gap-2">
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className="w-6 h-6 rounded-full transition-transform hover:scale-110"
              style={{ background: c, outline: c === color ? "2px solid white" : "none", outlineOffset: 2 }}
            />
          ))}
        </div>
      </div>

      <div>
        <label className="label">Notes (optional)</label>
        <textarea className="input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Strategy notes…" />
      </div>

      {/* Holdings */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="label mb-0">Holdings</label>
          <button type="button" onClick={addHolding} className="btn-ghost text-xs gap-1 py-1 px-2">
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>

        {holdings.length === 0 && (
          <p className="text-xs text-text-tertiary">No holdings. Add symbols to this bucket.</p>
        )}

        <div className="space-y-2">
          {holdings.map((h, i) => (
            <div key={i} className="flex gap-2 items-center">
              <input
                className="input flex-1 uppercase"
                placeholder="AAPL"
                value={h.symbol}
                onChange={(e) => updateHolding(i, "symbol", e.target.value.toUpperCase())}
              />
              <input
                className="input w-24"
                type="number"
                step="0.01"
                min="0"
                max="100"
                placeholder="100"
                value={h.target_weight_within_bucket_pct}
                onChange={(e) => updateHolding(i, "target_weight_within_bucket_pct", e.target.value)}
              />
              <span className="text-xs text-text-tertiary">%</span>
              <button type="button" onClick={() => removeHolding(i)} className="text-red-loss hover:text-red-400 p-1">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>

        {holdings.length > 0 && (
          <p className={`text-xs mt-1 ${Math.abs(totalHoldingWeight - 100) < 0.01 ? "text-green-profit" : "text-orange-400"}`}>
            Total within bucket: {totalHoldingWeight.toFixed(1)}% (should sum to 100)
          </p>
        )}
      </div>

      {error && <p className="text-xs text-red-loss">{error}</p>}

      <div className="flex gap-2 pt-2">
        <button type="submit" disabled={isPending} className="btn-primary flex-1">
          {isPending ? "Saving…" : existingBucket ? "Update Bucket" : "Create Bucket"}
        </button>
        <button type="button" onClick={onClose} className="btn-ghost flex-1">
          Cancel
        </button>
      </div>
    </form>
  );
}
