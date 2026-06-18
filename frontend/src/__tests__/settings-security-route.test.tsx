/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// keep FirstRunGuard from redirecting and give the sidebar a profile
vi.mock('@/hooks/use-first-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/use-first-run')>();
  return {
    ...actual,
    useFirstRunStatus: () => ({
      data: {
        firstRunRequired: false,
        deploymentProfile: 'lite',
        dataDir: null,
      },
    }),
  };
});

import { App } from '@/app';
import { useAuthStore } from '@/stores/auth-store';

describe('/settings/security route is wired', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: 'test-token',
      user: {
        id: 'u1',
        email: 'a@example.com',
        displayName: 'A',
        role: 'analyst',
        mfaEnabled: false,
      },
    });
    window.history.pushState({}, '', '/settings/security');
  });

  it('resolves to the Security settings page, not the 404 view', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { name: 'Security Settings' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Page not found')).not.toBeInTheDocument();
  });
});
