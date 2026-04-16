import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuthStore } from "./store/auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Performance from "./pages/Performance";
import Dividends from "./pages/Dividends";
import Buckets from "./pages/Buckets";
import Trade from "./pages/Trade";
import Orders from "./pages/Orders";
import Settings from "./pages/Settings";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="holdings" element={<Holdings />} />
          <Route path="performance" element={<Performance />} />
          <Route path="dividends" element={<Dividends />} />
          <Route path="buckets" element={<Buckets />} />
          <Route path="trade" element={<Trade />} />
          <Route path="orders" element={<Orders />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
