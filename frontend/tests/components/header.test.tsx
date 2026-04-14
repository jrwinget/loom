import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Header } from '@/components/layout/header';
import { useAuthStore } from '@/stores/auth-store';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderHeader(): void {
  render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>,
  );
}

describe('Header user menu', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      token: 'test-token',
      user: {
        id: 'u1',
        email: 'analyst@example.com',
        displayName: 'Test User',
        role: 'analyst',
      },
    });
  });

  it('renders the user menu button', () => {
    renderHeader();
    expect(
      screen.getByTestId('user-menu-button'),
    ).toBeInTheDocument();
  });

  it('shows first letter of email on the button', () => {
    renderHeader();
    expect(
      screen.getByTestId('user-menu-button'),
    ).toHaveTextContent('A');
  });

  it('opens dropdown on click', async () => {
    const user = userEvent.setup();
    renderHeader();

    expect(
      screen.queryByTestId('user-menu-dropdown'),
    ).not.toBeInTheDocument();

    await user.click(screen.getByTestId('user-menu-button'));

    expect(
      screen.getByTestId('user-menu-dropdown'),
    ).toBeInTheDocument();
  });

  it('displays user email in the dropdown', async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByTestId('user-menu-button'));

    expect(
      screen.getByTestId('user-menu-email'),
    ).toHaveTextContent('analyst@example.com');
  });

  it('has a settings link', async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByTestId('user-menu-button'));

    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('navigates to settings on settings click', async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByTestId('user-menu-button'));
    await user.click(screen.getByText('Settings'));

    expect(mockNavigate).toHaveBeenCalledWith(
      '/settings/security',
    );
  });

  it('clears auth and navigates to login on logout', async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByTestId('user-menu-button'));
    await user.click(screen.getByTestId('logout-button'));

    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().user).toBeNull();
    expect(mockNavigate).toHaveBeenCalledWith('/login');
  });

  it('closes dropdown when clicking outside', async () => {
    const user = userEvent.setup();
    renderHeader();

    await user.click(screen.getByTestId('user-menu-button'));
    expect(
      screen.getByTestId('user-menu-dropdown'),
    ).toBeInTheDocument();

    await user.click(document.body);
    expect(
      screen.queryByTestId('user-menu-dropdown'),
    ).not.toBeInTheDocument();
  });
});
