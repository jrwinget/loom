import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NarrativePanel } from '@/components/case/narrative-panel';
import type { NarrativeDraft } from '@/hooks/use-narratives';

const mockGenerate = vi.fn();
const mockApprove = vi.fn();
const mockReject = vi.fn();

let narrativesState: { data: NarrativeDraft[] | undefined };
let generateState: { mutate: typeof mockGenerate; isPending: boolean };
let approveState: { mutate: typeof mockApprove; isPending: boolean };
let rejectState: { mutate: typeof mockReject; isPending: boolean };

vi.mock('@/hooks/use-narratives', () => ({
  useNarratives: () => narrativesState,
  useGenerateNarrative: () => generateState,
  useApproveNarrative: () => approveState,
  useRejectNarrative: () => rejectState,
}));

function draft(overrides: Partial<NarrativeDraft> = {}): NarrativeDraft {
  return {
    id: 'n1',
    caseId: 'case-1',
    assetId: null,
    status: 'draft',
    text: 'On the dates below, the following custody events occurred.',
    sourceEntryIds: ['e1', 'e2'],
    modelName: 'cloud:my-model',
    modelVersion: 'api',
    modelParams: null,
    generatedBy: 'u1',
    reviewedBy: null,
    reviewedAt: null,
    createdAt: '2026-09-14T12:00:00Z',
    updatedAt: '2026-09-14T12:00:00Z',
    ...overrides,
  };
}

function renderPanel(): void {
  render(<NarrativePanel caseId="case-1" />);
}

describe('NarrativePanel', () => {
  beforeEach(() => {
    mockGenerate.mockReset();
    mockApprove.mockReset();
    mockReject.mockReset();
    narrativesState = { data: [] };
    generateState = { mutate: mockGenerate, isPending: false };
    approveState = { mutate: mockApprove, isPending: false };
    rejectState = { mutate: mockReject, isPending: false };
  });

  it('shows an empty state with no narratives', () => {
    renderPanel();
    expect(screen.getByText('No narrative drafted yet.')).toBeInTheDocument();
  });

  it('drafts a narrative when the button is clicked', async () => {
    renderPanel();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('generate-narrative-btn'));

    expect(mockGenerate).toHaveBeenCalledWith(undefined);
  });

  it('always shows a persistent AI-drafted badge, even before review', () => {
    narrativesState = { data: [draft({ status: 'draft' })] };
    renderPanel();

    const badge = screen.getByTestId('ai-drafted-badge');
    expect(badge).toHaveTextContent('AI-DRAFTED');
    expect(badge).toHaveTextContent('unreviewed');
  });

  it('keeps the badge after approval, with the reviewer decision', () => {
    narrativesState = {
      data: [
        draft({
          status: 'approved',
          reviewedBy: 'u2',
          reviewedAt: '2026-09-14T13:00:00Z',
        }),
      ],
    };
    renderPanel();

    const badge = screen.getByTestId('ai-drafted-badge');
    expect(badge).toHaveTextContent('AI-DRAFTED');
    expect(badge).toHaveTextContent('approved');
  });

  it('offers approve/reject only for an unreviewed draft', () => {
    narrativesState = { data: [draft({ status: 'draft' })] };
    renderPanel();

    expect(screen.getByTestId('approve-narrative-btn')).toBeInTheDocument();
    expect(screen.getByTestId('reject-narrative-btn')).toBeInTheDocument();
  });

  it('hides approve/reject once a narrative has been reviewed', () => {
    narrativesState = { data: [draft({ status: 'approved' })] };
    renderPanel();

    expect(
      screen.queryByTestId('approve-narrative-btn'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('reject-narrative-btn'),
    ).not.toBeInTheDocument();
  });

  it('approves a narrative', async () => {
    narrativesState = { data: [draft({ id: 'n42', status: 'draft' })] };
    renderPanel();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('approve-narrative-btn'));

    expect(mockApprove).toHaveBeenCalledWith('n42');
  });

  it('rejects a narrative', async () => {
    narrativesState = { data: [draft({ id: 'n42', status: 'draft' })] };
    renderPanel();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('reject-narrative-btn'));

    expect(mockReject).toHaveBeenCalledWith('n42');
  });
});
