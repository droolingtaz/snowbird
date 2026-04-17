import { useState } from "react";
import { useGoal, useGoalProjection, useUpsertGoal } from "../api/hooks";
import Card from "./Card";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine,
} from "recharts";

function ProgressRing({ pct, size = 64 }: { pct: number; size?: number }) {
  const stroke = 5;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const filled = Math.min(pct, 100);
  const offset = circ - (filled / 100) * circ;

  return (
    <svg width={size} height={size} className="transform -rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1e2433" strokeWidth={stroke} />
      <circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={filled >= 100 ? "#22c55e" : "#4f7cff"}
        strokeWidth={stroke}
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        className="transition-all duration-500"
      />
    </svg>
  );
}

function GoalSetupForm({ onSave }: { onSave: (data: any) => void }) {
  const [target, setTarget] = useState("");
  const [growth, setGrowth] = useState("8");
  const [contrib, setContrib] = useState("0");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!target) return;
    onSave({
      target_annual_income: parseFloat(target),
      assumed_annual_growth_pct: parseFloat(growth) || 8,
      assumed_monthly_contribution: parseFloat(contrib) || 0,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="text-xs text-text-secondary block mb-1">Annual Income Target ($)</label>
        <input
          type="number" min="1" step="100" value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm"
          placeholder="50000"
          required
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="text-xs text-text-secondary block mb-1">Growth %/yr</label>
          <input
            type="number" min="0" max="50" step="0.5" value={growth}
            onChange={(e) => setGrowth(e.target.value)}
            className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="text-xs text-text-secondary block mb-1">Monthly Contrib</label>
          <input
            type="number" min="0" step="50" value={contrib}
            onChange={(e) => setContrib(e.target.value)}
            className="w-full bg-surface-2 border border-border rounded px-2 py-1.5 text-sm"
            placeholder="0"
          />
        </div>
      </div>
      <button type="submit" className="btn-primary w-full text-sm py-1.5">Set Goal</button>
    </form>
  );
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-xs shadow-card-lg">
      <p className="text-text-secondary mb-0.5">{label}</p>
      <p className="font-semibold mono text-text-primary">
        ${payload[0].value?.toLocaleString("en-US", { minimumFractionDigits: 0 })}
      </p>
    </div>
  );
}

export default function IncomeGoalCard() {
  const { data: goal, isLoading: goalLoading } = useGoal();
  const { data: projection } = useGoalProjection();
  const upsertGoal = useUpsertGoal();
  const [editing, setEditing] = useState(false);

  const handleSave = (data: any) => {
    upsertGoal.mutate(data, { onSuccess: () => setEditing(false) });
  };

  if (goalLoading) {
    return (
      <Card title="Income Goal">
        <div className="animate-pulse bg-surface-2 rounded h-32" />
      </Card>
    );
  }

  if (!goal || editing) {
    return (
      <Card
        title="Income Goal"
        action={
          goal ? (
            <button onClick={() => setEditing(false)} className="text-xs text-text-secondary hover:text-text-primary">
              Cancel
            </button>
          ) : null
        }
      >
        <GoalSetupForm onSave={handleSave} />
      </Card>
    );
  }

  const pct = projection
    ? Math.min((projection.current_annual_income / goal.target_annual_income) * 100, 100)
    : 0;

  return (
    <Card
      title="Income Goal"
      action={
        <button onClick={() => setEditing(true)} className="text-xs text-text-secondary hover:text-text-primary">
          Edit
        </button>
      }
    >
      {/* Progress ring + stats */}
      <div className="flex items-center gap-4 mb-4">
        <div className="relative flex items-center justify-center">
          <ProgressRing pct={pct} size={64} />
          <span className="absolute text-xs font-semibold mono">{Math.round(pct)}%</span>
        </div>
        <div className="flex-1 space-y-1 text-sm">
          <div className="flex justify-between">
            <span className="text-text-secondary">Current</span>
            <span className="mono font-medium">
              ${projection?.current_annual_income?.toLocaleString("en-US", { minimumFractionDigits: 0 }) ?? "—"}/yr
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-secondary">Target</span>
            <span className="mono font-medium">
              ${goal.target_annual_income.toLocaleString("en-US", { minimumFractionDigits: 0 })}/yr
            </span>
          </div>
          {projection?.eta_year && (
            <div className="flex justify-between">
              <span className="text-text-secondary">ETA</span>
              <span className="mono font-medium text-accent">
                {projection.eta_year} ({projection.years_to_goal}y)
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Projection chart */}
      {projection?.projection?.length > 0 && (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={projection.projection} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e2433" vertical={false} />
            <XAxis
              dataKey="year" tick={{ fontSize: 10, fill: "#4a5568" }}
              tickLine={false} axisLine={false}
              tickFormatter={(v: number) => String(v).slice(2)}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "#4a5568" }} tickLine={false} axisLine={false}
              width={50}
              tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine
              y={goal.target_annual_income}
              stroke="#22c55e" strokeDasharray="4 4" strokeWidth={1.5}
            />
            <Line
              type="monotone" dataKey="projected_income"
              stroke="#4f7cff" strokeWidth={2} dot={false}
              name="Projected Income"
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
