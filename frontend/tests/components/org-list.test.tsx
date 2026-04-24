import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrgList } from '@/components/organization/org-list';
import type { Organization } from '@/types/organization';

const mockOrgs: Organization[] = [
  {
    id: '1',
    name: 'Legal Observers Chicago',
    description: 'Chicago chapter',
    isActive: true,
    memberCount: 5,
    createdAt: '2026-01-01T00:00:00Z',
  },
  {
    id: '2',
    name: 'Legal Observers Boston',
    description: 'Boston chapter',
    isActive: true,
    memberCount: 3,
    createdAt: '2026-02-01T00:00:00Z',
  },
];

function renderOrgList(
  props: Partial<{
    organizations: Organization[];
    isLoading: boolean;
    onCreateOrg: (name: string, description: string) => void;
  }> = {},
): void {
  render(
    <OrgList
      organizations={props.organizations ?? []}
      isLoading={props.isLoading ?? false}
      onCreateOrg={props.onCreateOrg ?? vi.fn()}
    />,
  );
}

describe('OrgList', () => {
  it('renders correct number of org cards', () => {
    renderOrgList({ organizations: mockOrgs });
    const cards = screen.getAllByTestId('org-card');
    expect(cards).toHaveLength(2);
    expect(screen.getByText('Legal Observers Chicago')).toBeInTheDocument();
    expect(screen.getByText('Legal Observers Boston')).toBeInTheDocument();
  });

  it('shows member count badges', () => {
    renderOrgList({ organizations: mockOrgs });
    const badges = screen.getAllByTestId('member-count-badge');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent('5 members');
    expect(badges[1]).toHaveTextContent('3 members');
  });

  it('shows create button', () => {
    renderOrgList({ organizations: mockOrgs });
    expect(screen.getByTestId('create-org-btn')).toBeInTheDocument();
  });

  it('shows skeleton when loading', () => {
    renderOrgList({ isLoading: true });
    const skeletons = screen.getAllByTestId('org-skeleton');
    expect(skeletons).toHaveLength(4);
  });

  it('shows empty state when no orgs', () => {
    renderOrgList({ organizations: [] });
    expect(screen.getByTestId('org-empty-state')).toBeInTheDocument();
    expect(screen.getByText('No organizations yet')).toBeInTheDocument();
  });
});
