import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CaseCard } from '@/components/case/case-card';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const defaultProps = {
  id: 'case-1',
  name: 'Test Case',
  description: 'A brief description of the case',
  status: 'active',
  assetCount: 5,
  eventCount: 12,
  createdAt: '2026-01-15T10:00:00Z',
};

function renderCard(
  overrides: Partial<typeof defaultProps> = {},
): void {
  render(
    <MemoryRouter>
      <CaseCard {...defaultProps} {...overrides} />
    </MemoryRouter>,
  );
}

describe('CaseCard', () => {
  it('renders name and description', () => {
    renderCard();
    expect(
      screen.getByText('Test Case'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'A brief description of the case',
      ),
    ).toBeInTheDocument();
  });

  it('shows active status badge with green styling', () => {
    renderCard({ status: 'active' });
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('active');
    expect(badge.className).toContain('green');
  });

  it('shows archived status badge with gray styling', () => {
    renderCard({ status: 'archived' });
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('archived');
    expect(badge.className).toContain('gray');
  });

  it('shows exported status badge with blue styling', () => {
    renderCard({ status: 'exported' });
    const badge = screen.getByTestId('status-badge');
    expect(badge).toHaveTextContent('exported');
    expect(badge.className).toContain('blue');
  });

  it('navigates to case detail on click', async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(
      screen.getByTestId('case-card-case-1'),
    );
    expect(mockNavigate).toHaveBeenCalledWith(
      '/cases/case-1',
    );
  });

  it('truncates long descriptions', () => {
    const longDesc = 'A'.repeat(150);
    renderCard({ description: longDesc });
    const displayed = screen.getByText(/^A+\.\.\.$/);
    expect(displayed).toBeInTheDocument();
  });

  it('displays asset and event counts', () => {
    renderCard();
    expect(
      screen.getByText('5 assets'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('12 events'),
    ).toBeInTheDocument();
  });
});
