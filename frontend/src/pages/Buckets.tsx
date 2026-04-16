import { useState } from "react";
import { useBuckets, useBucketDrift, useDeleteBucket } from "../api/hooks";
import { useAuthStore } from "../store/auth";
import Card from "../components/Card";
import BucketEditor from "../components/BucketEditor";
import RebalancePanel from "../components/RebalancePanel";
import { Plus, Edit2, Trash2, Scale } from "lucide-react";
import { clsx } from "clsx";

function RingChart({ actual, target, color }: { actual: number; target: number; color?: string }) {
  const size = 56;
  const r = 22;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * r;
  const targetDash = (target / 100) * circumference;
  const actualDash = (actual / 100) * circumference;

  return (
    <svg width={size} height={size}>
      {/* Track */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1e2433" strokeWidth={6} />
      {/* Target (dashed) */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none" stroke={color ?? "#4f7cff"} strokeWidth={4}
        strokeDasharray={`${targetDash} ${circumference}`}
        strokeDashoffset={0} opacity={0.3}
        style={{ transform: "rotate(-90deg)", transformOrigin: "50% 50%" }}
      />
      {/* Actual */}
      <circle
        cx={cx} cy={cy} r={r}
        fill="none" stroke={color ?? "#4f7cff"} strokeWidth={6}
        strokeDasharray={`${actualDash} ${circumference}`}
        strokeDashoffset={0}
        style={{ transform: "rotate(-90deg)", transformOrigin: "50% 50%" }}
      />
      <text x={cx} y={cy + 4} textAnchor="middle" fill="white" fontSize={10} fontWeight={600}>
        {actual.toFixed(0)}%
      </text>
    </svg>
  );
}

export default function Buckets() {
  const accountId = useAuthStore((s) => s.accountId);
  const { data: buckets = [], isLoading } = useBuckets();
  const { data: drift = [] } = useBucketDrift();
  const deleteBucket = useDeleteBucket();

  const [showCreate, setShowCreate] = useState(false);
  const [editingBucket, setEditingBucket] = useState<any>(null);
  const [showRebalance, setShowRebalance] = useState(false);

  const totalTarget = (buckets as any[]).reduce((s: number, b: any) => s + b.target_weight_pct, 0);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Buckets</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Total target: {totalTarget.toFixed(1)}% {Math.abs(totalTarget - 100) > 0.1 && (
              <span className="text-orange-400">(≠ 100%)</span>
            )}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowRebalance(true)}
            className="btn-ghost gap-1.5 text-sm"
          >
            <Scale className="w-4 h-4" /> Rebalance
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary gap-1.5 text-sm"
          >
            <Plus className="w-4 h-4" /> New Bucket
          </button>
        </div>
      </div>

      {/* Bucket cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => <div key={i} className="card h-32 animate-pulse" />)}
        </div>
      ) : (buckets as any[]).length === 0 ? (
        <div className="text-center py-16 text-text-tertiary">
          <p>No buckets yet.</p>
          <button onClick={() => setShowCreate(true)} className="btn-primary mt-4">Create Your First Bucket</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {(buckets as any[]).map((bucket) => (
            <div key={bucket.id} className="card">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <RingChart
                    actual={bucket.actual_weight_pct ?? 0}
                    target={bucket.target_weight_pct}
                    color={bucket.color}
                  />
                  <div>
                    <h3 className="font-medium">{bucket.name}</h3>
                    <p className="text-xs text-text-secondary">
                      Target: {bucket.target_weight_pct}%
                    </p>
                    <p className={clsx(
                      "text-xs mono",
                      Math.abs(bucket.drift_pct ?? 0) < 2 ? "text-green-profit" : "text-orange-400"
                    )}>
                      Drift: {(bucket.drift_pct ?? 0).toFixed(2)}%
                    </p>
                  </div>
                </div>
                <div className="flex gap-1">
                  <button
                    onClick={() => setEditingBucket(bucket)}
                    className="btn-ghost p-1.5 rounded"
                  >
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => deleteBucket.mutate(bucket.id)}
                    className="btn-ghost p-1.5 rounded text-red-loss hover:text-red-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              {/* Holdings chips */}
              <div className="flex flex-wrap gap-1">
                {bucket.holdings.map((h: any) => (
                  <span key={h.symbol} className="badge bg-surface-2 text-text-secondary">
                    {h.symbol} {h.target_weight_within_bucket_pct}%
                  </span>
                ))}
              </div>

              {bucket.notes && (
                <p className="text-xs text-text-tertiary mt-2 line-clamp-1">{bucket.notes}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Drift table */}
      {(drift as any[]).length > 0 && (
        <Card title="Drift Detail">
          <div className="overflow-x-auto">
            <table className="table-auto">
              <thead>
                <tr>
                  <th>Bucket / Symbol</th>
                  <th className="text-right">Target %</th>
                  <th className="text-right">Actual %</th>
                  <th className="text-right">Drift</th>
                  <th className="text-right">Market Value</th>
                </tr>
              </thead>
              <tbody>
                {(drift as any[]).flatMap((bucket) => [
                  <tr key={`b-${bucket.bucket_id}`} className="bg-surface-2">
                    <td className="font-medium text-text-primary" colSpan={5}>{bucket.bucket_name}</td>
                  </tr>,
                  ...bucket.holdings.map((h: any) => (
                    <tr key={`${bucket.bucket_id}-${h.symbol}`}>
                      <td className="pl-6 text-text-secondary">{h.symbol}</td>
                      <td className="text-right mono">{h.target_pct.toFixed(2)}%</td>
                      <td className="text-right mono">{h.actual_pct.toFixed(2)}%</td>
                      <td className={clsx(
                        "text-right mono",
                        Math.abs(h.drift_pct) < 1 ? "text-green-profit" :
                        Math.abs(h.drift_pct) < 3 ? "text-orange-400" : "text-red-loss"
                      )}>
                        {h.drift_pct >= 0 ? "+" : ""}{h.drift_pct.toFixed(2)}%
                      </td>
                      <td className="text-right mono">${h.market_value.toFixed(2)}</td>
                    </tr>
                  )),
                ])}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create modal */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-surface-1 rounded-xl border border-border w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold mb-4">New Bucket</h2>
            <BucketEditor onClose={() => setShowCreate(false)} />
          </div>
        </div>
      )}

      {/* Edit modal */}
      {editingBucket && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-surface-1 rounded-xl border border-border w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold mb-4">Edit Bucket</h2>
            <BucketEditor existingBucket={editingBucket} onClose={() => setEditingBucket(null)} />
          </div>
        </div>
      )}

      {/* Rebalance modal */}
      {showRebalance && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-surface-1 rounded-xl border border-border w-full max-w-md p-5 max-h-[90vh] overflow-y-auto">
            <h2 className="font-semibold mb-4">Rebalance Portfolio</h2>
            <RebalancePanel onClose={() => setShowRebalance(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
