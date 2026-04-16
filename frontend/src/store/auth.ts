import { create } from "zustand";

interface User {
  id: number;
  email: string;
  created_at: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  accountId: number | null;
  setToken: (token: string) => void;
  setUser: (user: User) => void;
  setAccountId: (id: number | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem("access_token"),
  user: null,
  accountId: null,

  setToken: (token) => {
    localStorage.setItem("access_token", token);
    set({ token });
  },

  setUser: (user) => set({ user }),

  setAccountId: (id) => {
    if (id !== null) {
      localStorage.setItem("account_id", String(id));
    } else {
      localStorage.removeItem("account_id");
    }
    set({ accountId: id });
  },

  logout: () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("account_id");
    set({ token: null, user: null, accountId: null });
  },
}));

// Rehydrate accountId from localStorage
const storedAccountId = localStorage.getItem("account_id");
if (storedAccountId) {
  useAuthStore.setState({ accountId: parseInt(storedAccountId, 10) });
}
