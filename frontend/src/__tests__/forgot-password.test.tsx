/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ForgotPasswordPage } from '@/routes/forgot-password';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/forgot-password']}>
      <Routes>
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/login" element={<div>Sign in here</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function fillForm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/email/i), 'ada@example.org');
  await user.type(
    screen.getByLabelText(/recovery code/i),
    'aaaaa-bbbbb-ccccc-ddddd',
  );
  await user.type(
    screen.getByLabelText(/new password \(min/i),
    'correct-horse-battery',
  );
  await user.type(
    screen.getByLabelText(/confirm new password/i),
    'correct-horse-battery',
  );
}

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  it('rejects passwords shorter than 12 characters', async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    renderPage();

    await user.type(screen.getByLabelText(/email/i), 'ada@example.org');
    await user.type(
      screen.getByLabelText(/recovery code/i),
      'aaaaa-bbbbb-ccccc-ddddd',
    );
    await user.type(screen.getByLabelText(/new password \(min/i), 'short');
    await user.type(screen.getByLabelText(/confirm new password/i), 'short');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /at least 12 characters/i,
    );
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('rejects when passwords do not match', async () => {
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    renderPage();

    await user.type(screen.getByLabelText(/email/i), 'ada@example.org');
    await user.type(
      screen.getByLabelText(/recovery code/i),
      'aaaaa-bbbbb-ccccc-ddddd',
    );
    await user.type(
      screen.getByLabelText(/new password \(min/i),
      'correct-horse-battery',
    );
    await user.type(
      screen.getByLabelText(/confirm new password/i),
      'different-password-xx',
    );
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('posts to /auth/recover-password and shows the success view', async () => {
    mockedPost.mockResolvedValueOnce({ codesRemaining: 7 });
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    renderPage();

    await fillForm(user);
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/auth/recover-password', {
        email: 'ada@example.org',
        recovery_code: 'aaaaa-bbbbb-ccccc-ddddd',
        new_password: 'correct-horse-battery',
      });
    });

    expect(
      await screen.findByTestId('forgot-password-success'),
    ).toBeInTheDocument();
    expect(screen.getByText(/7 recovery codes remaining/i)).toBeInTheDocument();
  });

  it('surfaces backend errors verbatim', async () => {
    mockedPost.mockRejectedValueOnce(
      new Error('invalid email or recovery code'),
    );
    const user = userEvent.setup({
      advanceTimers: vi.advanceTimersByTime.bind(vi),
    });
    renderPage();

    await fillForm(user);
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /invalid email or recovery code/i,
    );
  });
});
