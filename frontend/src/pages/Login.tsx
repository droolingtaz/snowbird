import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bird } from "lucide-react";
import api from "../api/client";
import { useAuthStore } from "../store/auth";

export default function Login() {
  const navigate = useNavigate();
  const { setToken } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.post("/auth/login", { email, password });
      setToken(res.data.access_token);
      navigate("/dashboard");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-surface-0 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-accent/10 flex items-center justify-center mb-3">
            <Bird className="w-7 h-7 text-accent" strokeWidth={1.5} />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">Snowbird</h1>
          <p className="text-text-secondary text-sm mt-1">Portfolio Analytics + Trading</p>
        </div>

        <form onSubmit={handleSubmit} className="card space-y-4">
          <div>
            <label className="label">Email</label>
            <input
              className="input"
              type="email"
              autoComplete="email"
              placeholder="demo@local"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && <p className="text-xs text-red-loss">{error}</p>}

          <button type="submit" className="btn-primary w-full py-2.5" disabled={loading}>
            {loading ? "Signing in…" : "Sign In"}
          </button>

          <p className="text-center text-xs text-text-tertiary">
            Demo: demo@local / demo12345
          </p>
        </form>
      </div>
    </div>
  );
}
