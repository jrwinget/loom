import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Header } from '@/components/layout/header';

function renderHeader(): ReturnType<typeof render> {
  return render(<Header />);
}

describe('Header', () => {
  it('renders with banner landmark role', () => {
    renderHeader();
    const header = screen.getByRole('banner');
    expect(header).toBeInTheDocument();
  });

  it('renders breadcrumb navigation', () => {
    renderHeader();
    const nav = screen.getByRole('navigation', {
      name: 'Breadcrumb',
    });
    expect(nav).toBeInTheDocument();
    expect(screen.getByText('Home')).toBeInTheDocument();
  });

  it('has keyboard shortcuts button', () => {
    renderHeader();
    const btn = screen.getByRole('button', {
      name: 'Keyboard shortcuts',
    });
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveTextContent('?');
  });

  it('has user menu button', () => {
    renderHeader();
    const btn = screen.getByRole('button', {
      name: 'User menu',
    });
    expect(btn).toBeInTheDocument();
  });
});
