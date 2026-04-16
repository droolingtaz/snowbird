import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import { useEffect } from "react";
import { useAuthStore } from "../store/auth";
import { useMe } from "../api/hooks";

export default function Layout() {
  const { data: user } = useMe();
  const setUser = useAuthStore((s) => s.setUser);

  useEffect(() => {
    if (user) setUser(user);
  }, [user, setUser]);

  return (
    <div className="flex h-screen overflow-hidden bg-surface-0">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
