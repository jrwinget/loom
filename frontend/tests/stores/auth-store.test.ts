import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { useAuthStore } from '@/stores/auth-store';
import type { User } from '@/types';

const mockUser: User = {
  id: 'user-1',
  email: 'analyst@example.org',
  displayName: 'Jane Doe',
  role: 'analyst',
};

describe('auth-store', () => {
  beforeEach(() => {
    useAuthStore.setState({ token: null, user: null });
  });

  it('starts unauthenticated', () => {
    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated()).toBe(false);
  });

  it('setAuth stores token and user', () => {
    useAuthStore.getState().setAuth('jwt-token-123', mockUser);

    const state = useAuthStore.getState();
    expect(state.token).toBe('jwt-token-123');
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated()).toBe(true);
  });

  it('clearAuth resets to unauthenticated', () => {
    useAuthStore.getState().setAuth('token', mockUser);
    useAuthStore.getState().clearAuth();

    const state = useAuthStore.getState();
    expect(state.token).toBeNull();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated()).toBe(false);
  });

  it('isAuthenticated reflects token presence', () => {
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);

    useAuthStore.getState().setAuth('t', mockUser);
    expect(useAuthStore.getState().isAuthenticated()).toBe(true);

    useAuthStore.getState().clearAuth();
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);
  });

  it('preserves user data across setAuth calls', () => {
    const admin: User = {
      id: 'admin-1',
      email: 'admin@example.org',
      displayName: 'Admin',
      role: 'admin',
    };

    useAuthStore.getState().setAuth('token-1', mockUser);
    useAuthStore.getState().setAuth('token-2', admin);

    const state = useAuthStore.getState();
    expect(state.token).toBe('token-2');
    expect(state.user?.role).toBe('admin');
  });
});
