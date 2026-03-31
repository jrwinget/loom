import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Sidebar } from '@/components/layout/sidebar';
import { useUiStore } from '@/stores/ui-store';

// mock useParams so we can control caseId
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useParams: () => ({}),
  };
});

function renderSidebar(
  route = '/',
): ReturnType<typeof render> {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe('Sidebar', () => {
  it('renders navigation links', () => {
    renderSidebar();
    expect(
      screen.getByText('Dashboard'),
    ).toBeInTheDocument();
    expect(screen.getByText('Cases')).toBeInTheDocument();
    expect(
      screen.getByText('Organizations'),
    ).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('highlights active route with aria-current', () => {
    renderSidebar('/cases');
    const casesLink = screen.getByText('Cases');
    expect(casesLink).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('does not highlight inactive routes', () => {
    renderSidebar('/cases');
    const dashLink = screen.getByText('Dashboard');
    expect(dashLink).not.toHaveAttribute('aria-current');
  });

  it('collapses when sidebar is closed', () => {
    // close the sidebar via zustand store
    useUiStore.setState({ sidebarOpen: false });

    renderSidebar();
    const aside = screen.getByTestId('sidebar');
    expect(aside.className).toContain('w-14');

    // restore
    useUiStore.setState({ sidebarOpen: true });
  });

  it('expands when sidebar is open', () => {
    useUiStore.setState({ sidebarOpen: true });

    renderSidebar();
    const aside = screen.getByTestId('sidebar');
    expect(aside.className).toContain('w-60');
  });

  it('toggles sidebar on button click', async () => {
    useUiStore.setState({ sidebarOpen: true });
    const user = userEvent.setup();

    renderSidebar();
    const toggleBtn = screen.getByRole('button', {
      name: 'Collapse sidebar',
    });

    await user.click(toggleBtn);

    expect(useUiStore.getState().sidebarOpen).toBe(false);

    // restore
    useUiStore.setState({ sidebarOpen: true });
  });

  it('has proper aria roles for navigation', () => {
    renderSidebar();
    const aside = screen.getByTestId('sidebar');
    expect(aside).toHaveAttribute(
      'aria-label',
      'Main navigation',
    );

    const nav = screen.getByRole('navigation', {
      name: 'Primary',
    });
    expect(nav).toBeInTheDocument();
  });

  it('shows abbreviated labels when collapsed', () => {
    useUiStore.setState({ sidebarOpen: false });

    renderSidebar();
    // first letter of "Dashboard" => "D"
    expect(screen.getByText('D')).toBeInTheDocument();
    // first letter of "Cases" => "C"
    // (there may be multiple C's if conflicts link shows)
    expect(screen.getAllByText('C').length).toBeGreaterThan(0);

    // restore
    useUiStore.setState({ sidebarOpen: true });
  });
});
