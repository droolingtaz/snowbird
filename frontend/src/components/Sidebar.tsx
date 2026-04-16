import { NavLink } from "react-router-dom";
import { clsx } from "clsx";
import {
  LayoutDashboard, Briefcase, TrendingUp, DollarSign,
  Grid3x3, ShoppingCart, ClipboardList, Settings, Bird
} from "lucide-react";

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/holdings", icon: Briefcase, label: "Holdings" },
  { to: "/performance", icon: TrendingUp, label: "Performance" },
  { to: "/dividends", icon: DollarSign, label: "Dividends" },
  { to: "/buckets", icon: Grid3x3, label: "Buckets" },
  { to: "/trade", icon: ShoppingCart, label: "Trade" },
  { to: "/orders", icon: ClipboardList, label: "Orders" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Sidebar() {
  return (
    <aside className="w-56 flex-shrink-0 bg-surface-1 border-r border-border flex flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-5 border-b border-border">
        <Bird className="w-6 h-6 text-accent" strokeWidth={1.5} />
        <span className="font-semibold text-base tracking-tight">Snowbird</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-accent/10 text-accent font-medium"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
              )
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" strokeWidth={1.5} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-border">
        <p className="text-2xs text-text-tertiary">Snowbird v1.0</p>
      </div>
    </aside>
  );
}
