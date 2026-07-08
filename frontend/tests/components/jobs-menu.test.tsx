/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobsMenu } from '@/components/layout/jobs-menu';
import { useJobStore } from '@/stores/job-store';

describe('JobsMenu', () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: [] });
  });

  it('shows no badge when nothing is running', () => {
    render(<JobsMenu />);
    expect(screen.queryByTestId('jobs-running-badge')).not.toBeInTheDocument();
  });

  it('badges the running count and lists jobs', async () => {
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
    });
    useJobStore.getState().registerJob({
      workflowId: 'export-1',
      caseId: 'case-1',
      kind: 'export',
      label: 'Court bundle',
    });
    const user = userEvent.setup();

    render(<JobsMenu />);
    expect(screen.getByTestId('jobs-running-badge')).toHaveTextContent('2');
    expect(screen.getByTestId('jobs-menu-button')).toHaveAttribute(
      'aria-label',
      'Jobs: 2 running',
    );

    await user.click(screen.getByTestId('jobs-menu-button'));
    expect(screen.getByTestId('job-row-transcribe-1')).toBeInTheDocument();
    expect(screen.getByTestId('job-row-export-1')).toBeInTheDocument();
  });

  it('shows the failure reason and retries through the callback', async () => {
    const retry = vi.fn();
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
      retry,
    });
    useJobStore
      .getState()
      .resolveJob(
        'transcribe-1',
        'failed',
        'install the ai extra',
        'engine_unavailable',
      );
    const user = userEvent.setup();

    render(<JobsMenu />);
    await user.click(screen.getByTestId('jobs-menu-button'));
    expect(screen.getByText('install the ai extra')).toBeInTheDocument();

    await user.click(screen.getByTestId('job-retry-transcribe-1'));
    expect(retry).toHaveBeenCalled();
    // the failed entry is dismissed; the retry registers a fresh one
    expect(useJobStore.getState().jobs).toHaveLength(0);
  });

  it('clears finished jobs but keeps running ones', async () => {
    useJobStore.getState().registerJob({
      workflowId: 'a',
      caseId: 'case-1',
      kind: 'ingest',
      label: 'a.mp4',
    });
    useJobStore.getState().registerJob({
      workflowId: 'b',
      caseId: 'case-1',
      kind: 'ingest',
      label: 'b.mp4',
    });
    useJobStore.getState().resolveJob('a', 'completed');
    const user = userEvent.setup();

    render(<JobsMenu />);
    await user.click(screen.getByTestId('jobs-menu-button'));
    await user.click(screen.getByTestId('jobs-clear-finished'));

    expect(useJobStore.getState().jobs.map((j) => j.workflowId)).toEqual(['b']);
  });

  it('has no axe violations with the menu open', async () => {
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
    });
    const user = userEvent.setup();

    // in the app the menu lives inside the banner landmark
    const { baseElement } = render(
      <header role="banner">
        <JobsMenu />
      </header>,
    );
    await user.click(screen.getByTestId('jobs-menu-button'));
    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
