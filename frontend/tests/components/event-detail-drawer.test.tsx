import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EventDetailDrawer } from '@/components/timeline/event-detail-drawer';
import type { EvidenceLink, TimelineEventDetail } from '@/types/timeline';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

function makeLink(overrides: Partial<EvidenceLink> = {}): EvidenceLink {
  return {
    id: 'link-1',
    eventId: 'evt-1',
    assetId: 'asset-1',
    annotationId: null,
    derivativeId: null,
    clipStart: null,
    clipEnd: null,
    relationship: 'supports',
    notes: null,
    linkedBy: 'user-1',
    linkedAt: '2026-03-15T18:00:00Z',
    ...overrides,
  };
}

function makeEvent(
  overrides: Partial<TimelineEventDetail> = {},
): TimelineEventDetail {
  return {
    id: 'evt-1',
    caseId: 'case-1',
    title: 'Protest at City Hall',
    description: 'Large gathering observed',
    eventTimeStart: '2026-03-15T14:00:00Z',
    eventTimeEnd: null,
    timePrecision: 'approximate',
    locationDescription: null,
    locationLat: null,
    locationLon: null,
    locationConfidence: 'unknown',
    status: 'draft',
    createdBy: 'user-1',
    createdAt: '2026-03-15T18:00:00Z',
    updatedAt: '2026-03-15T18:00:00Z',
    evidenceCount: 0,
    hasContradictions: false,
    evidence: [],
    ...overrides,
  };
}

function renderDrawer(
  event: TimelineEventDetail = makeEvent(),
  onClose = vi.fn(),
): { onClose: ReturnType<typeof vi.fn> } {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <EventDetailDrawer caseId="case-1" event={event} onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose };
}

describe('EventDetailDrawer', () => {
  beforeEach(async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.patch).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
    vi.mocked(apiClient.get).mockResolvedValue({
      items: [
        { id: 'asset-1', originalFilename: 'bodycam.mp4' },
        { id: 'asset-2', originalFilename: 'bystander.mov' },
      ],
    });
  });

  it('renders event detail with dialog semantics', () => {
    renderDrawer(
      makeEvent({ evidenceCount: 1, evidence: [makeLink()] }),
    );

    const panel = screen.getByTestId('event-detail-panel');
    expect(panel).toHaveAttribute('role', 'dialog');
    expect(panel).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByText('Protest at City Hall')).toBeInTheDocument();
    expect(screen.getByText('Large gathering observed')).toBeInTheDocument();
    expect(screen.getByText('draft')).toBeInTheDocument();
    expect(screen.getByText('approximate')).toBeInTheDocument();
    expect(screen.getByText('1 link')).toBeInTheDocument();
  });

  it('calls onClose from the backdrop', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDrawer();

    await user.click(screen.getByLabelText('Close panel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('shows relationship badges with per-relationship styling', () => {
    renderDrawer(
      makeEvent({
        evidenceCount: 3,
        evidence: [
          makeLink({ id: 'l1', relationship: 'supports' }),
          makeLink({ id: 'l2', relationship: 'contradicts' }),
          makeLink({ id: 'l3', relationship: 'context' }),
        ],
      }),
    );

    const badges = screen.getAllByTestId('relationship-badge');
    expect(badges).toHaveLength(3);
    expect(badges[0]).toHaveTextContent('supports');
    expect(badges[0].className).toContain('green');
    expect(badges[1]).toHaveTextContent('contradicts');
    expect(badges[1].className).toContain('red');
    expect(badges[2]).toHaveTextContent('context');
    expect(badges[2].className).toContain('gray');
  });

  it('shows the clip range when present', () => {
    renderDrawer(
      makeEvent({
        evidenceCount: 1,
        evidence: [makeLink({ clipStart: 12, clipEnd: 40 })],
      }),
    );

    expect(screen.getByText(/12.*40/)).toBeInTheDocument();
  });

  it('unlinks evidence via the api', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

    renderDrawer(
      makeEvent({ evidenceCount: 1, evidence: [makeLink({ id: 'link-9' })] }),
    );

    await user.click(screen.getByTestId('unlink-btn-link-9'));

    await waitFor(() =>
      expect(vi.mocked(apiClient.delete)).toHaveBeenCalledWith(
        '/cases/case-1/events/evt-1/evidence/link-9',
      ),
    );
  });

  it('submits an edit with the api payload shape', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.patch).mockResolvedValueOnce(makeEvent());

    renderDrawer();

    await user.click(screen.getByTestId('edit-event-btn'));
    const title = screen.getByLabelText('Title');
    await user.clear(title);
    await user.type(title, 'Confirmed protest');
    await user.selectOptions(screen.getByLabelText('Status'), 'confirmed');
    await user.selectOptions(screen.getByLabelText('Precision'), 'exact');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(vi.mocked(apiClient.patch)).toHaveBeenCalledWith(
        '/cases/case-1/events/evt-1',
        expect.objectContaining({
          title: 'Confirmed protest',
          status: 'confirmed',
          time_precision: 'exact',
          event_time_start: '2026-03-15T14:00:00.000Z',
        }),
      ),
    );
  });

  it('offers the new status vocabulary in edit mode', async () => {
    const user = userEvent.setup();
    renderDrawer();

    await user.click(screen.getByTestId('edit-event-btn'));
    const options = Array.from(
      screen.getByLabelText<HTMLSelectElement>('Status').options,
    ).map((o) => o.value);
    expect(options).toEqual(['draft', 'confirmed', 'disputed']);
  });

  it('cancel leaves edit mode without saving', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');

    renderDrawer();

    await user.click(screen.getByTestId('edit-event-btn'));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByTestId('event-edit-form')).not.toBeInTheDocument();
    expect(vi.mocked(apiClient.patch)).not.toHaveBeenCalled();
  });

  it('links new evidence with the api payload shape', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(makeLink());

    renderDrawer();

    await user.click(screen.getByTestId('add-evidence-btn'));
    await user.selectOptions(
      await screen.findByLabelText('Asset'),
      'asset-2',
    );
    await user.selectOptions(
      screen.getByLabelText('Relationship'),
      'contradicts',
    );
    await user.type(screen.getByLabelText('Clip start (s)'), '5');
    await user.type(screen.getByLabelText('Clip end (s)'), '10');
    await user.type(screen.getByLabelText('Notes'), 'counter angle');
    await user.click(
      screen.getByRole('button', { name: 'Link evidence' }),
    );

    await waitFor(() =>
      expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
        '/cases/case-1/events/evt-1/evidence',
        {
          asset_id: 'asset-2',
          relationship: 'contradicts',
          clip_start: 5,
          clip_end: 10,
          notes: 'counter angle',
        },
      ),
    );
  });

  it('omits clip range and notes when left empty', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(makeLink());

    renderDrawer();

    await user.click(screen.getByTestId('add-evidence-btn'));
    await user.selectOptions(
      await screen.findByLabelText('Asset'),
      'asset-1',
    );
    await user.click(
      screen.getByRole('button', { name: 'Link evidence' }),
    );

    await waitFor(() =>
      expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
        '/cases/case-1/events/evt-1/evidence',
        {
          asset_id: 'asset-1',
          relationship: 'supports',
        },
      ),
    );
  });
});
