import { create } from 'zustand';
import type { User } from '@/types';

interface AuthState {
  token: string | null;
  user: User | null;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  user: null,
  setAuth: (token: string, user: User) => set({ token, user }),
  clearAuth: () => set({ token: null, user: null }),
  isAuthenticated: () => get().token !== null,
}));
