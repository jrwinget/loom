import { create } from 'zustand';
import type { User } from '@/types';

export interface AuthState {
  token: string | null;
  user: User | null;
  mfaChallengeToken: string | null;
  setAuth: (token: string, user: User) => void;
  clearAuth: () => void;
  setMfaChallenge: (token: string) => void;
  clearMfaChallenge: () => void;
  isAuthenticated: () => boolean;
  requiresMfa: () => boolean;
}

export const useAuthStore = create<AuthState>(
  (set, get) => ({
    token: null,
    user: null,
    mfaChallengeToken: null,
    setAuth: (token: string, user: User) =>
      set({ token, user, mfaChallengeToken: null }),
    clearAuth: () =>
      set({
        token: null,
        user: null,
        mfaChallengeToken: null,
      }),
    setMfaChallenge: (token: string) =>
      set({ mfaChallengeToken: token }),
    clearMfaChallenge: () =>
      set({ mfaChallengeToken: null }),
    isAuthenticated: () => get().token !== null,
    requiresMfa: () => get().mfaChallengeToken !== null,
  }),
);
