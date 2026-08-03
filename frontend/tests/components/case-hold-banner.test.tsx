/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import { describe, expect, it } from 'vitest';
import { CaseHoldBanner } from '@/components/case/case-hold-banner';
import type { Case } from '@/types';

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 'c1',
    name: 'Operation Nightingale',
    description: null,
    status: 'active',
    assetCount: 2,
    eventCount: 0,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    holdActive: true,
    holdReason: 'Doe v. City litigation',
    holdSetBy: 'u1',
    holdSetAt: '2026-07-20T12:00:00Z',
    ...overrides,
  };
}

describe('CaseHoldBanner', () => {
  it('renders nothing when the case is not held', () => {
    const { container } = render(
      <CaseHoldBanner
        caseData={makeCase({
          holdActive: false,
          holdReason: null,
          holdSetBy: null,
          holdSetAt: null,
        })}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the hold notice, reason, and set date while held', () => {
    render(<CaseHoldBanner caseData={makeCase()} />);

    const banner = screen.getByTestId('case-hold-banner');
    expect(banner).toHaveTextContent(
      'This case is under litigation hold — destructive actions are disabled.',
    );
    expect(banner).toHaveTextContent('Doe v. City litigation');
    expect(banner).toHaveTextContent(/jul 20, 2026/i);
  });

  it('announces itself to assistive technology', () => {
    render(<CaseHoldBanner caseData={makeCase()} />);

    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<CaseHoldBanner caseData={makeCase()} />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
