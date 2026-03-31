import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User } from '@/types';

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      setAuth: (token: string, user: User) =>
        set({ token, user }),
      clearAuth: () => set({ token: null, user: null }),
      isAuthenticated: () => get().token !== null,
    }),
    {
      name: 'loom-auth',
      storage: {
        getItem: (name) => {
          const value = sessionStorage.getItem(name);
          try {
            return value ? JSON.parse(value) : null;
          } catch {
            sessionStorage.removeItem(name);
            return null;
          }
        },
        setItem: (name, value) =>
          sessionStorage.setItem(
            name,
            JSON.stringify(value),
          ),
        removeItem: (name) =>
          sessionStorage.removeItem(name),
      },
      partialize: (state) =>
        ({
          token: state.token,
          user: state.user,
        }) as unknown as AuthState,
    },
  ),
);
