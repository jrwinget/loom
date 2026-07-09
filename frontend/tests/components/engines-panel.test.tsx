/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EnginesPanel } from '@/components/settings/engines-panel';
import type { EnginesStatus } from '@/hooks/use-engines';

const mockDownload = vi.fn();
const mockDelete = vi.fn();
let enginesData: EnginesStatus | undefined;
let loading = false;

vi.mock('@/hooks/use-engines', () => ({
  useEngines: () => ({ data: enginesData, isLoading: loading }),
  useDownloadModel: () => ({ mutate: mockDownload, isPending: false }),
  useDeleteModel: () => ({ mutate: mockDelete, isPending: false }),
}));

function status(over?: Partial<EnginesStatus>): EnginesStatus {
  return {
    engines: {
      transcriptionLocal: {
        status: 'missing',
        remedy: 'no speech model is downloaded',
        version: null,
      },
      sceneDetection: { status: 'available', remedy: null, version: null },
    },
    models: [
      {
        name: 'tiny',
        sizeBytes: 78_000_000,
        downloaded: false,
        downloadStatus: null,
        bytesDone: null,
        bytesTotal: null,
        error: null,
      },
      {
        name: 'base',
        sizeBytes: 148_000_000,
        downloaded: true,
        downloadStatus: null,
        bytesDone: null,
        bytesTotal: null,
        error: null,
      },
    ],
    ...over,
  };
}

describe('EnginesPanel', () => {
  beforeEach(() => {
    enginesData = status();
    loading = false;
    mockDownload.mockReset();
    mockDelete.mockReset();
  });

  it('shows engine availability with remedies', () => {
    render(<EnginesPanel />);
    const local = screen.getByTestId('engine-transcriptionLocal');
    expect(local).toHaveTextContent('Unavailable');
    expect(local).toHaveTextContent('no speech model is downloaded');
    expect(screen.getByTestId('engine-sceneDetection')).toHaveTextContent(
      'Available',
    );
  });

  it('downloads only on click and states the egress plainly', () => {
    render(<EnginesPanel />);
    expect(screen.getByText(/only network request/)).toBeInTheDocument();
    expect(mockDownload).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('model-download-tiny'));
    expect(mockDownload).toHaveBeenCalledWith('tiny');
  });

  it('offers delete for downloaded models', () => {
    render(<EnginesPanel />);
    fireEvent.click(screen.getByTestId('model-delete-base'));
    expect(mockDelete).toHaveBeenCalledWith('base');
  });

  it('shows progress while downloading', () => {
    enginesData = status({
      models: [
        {
          name: 'tiny',
          sizeBytes: 78_000_000,
          downloaded: false,
          downloadStatus: 'downloading',
          bytesDone: 39_000_000,
          bytesTotal: 78_000_000,
          error: null,
        },
      ],
    });
    render(<EnginesPanel />);
    expect(screen.getByTestId('model-progress-tiny')).toHaveValue(50);
    expect(screen.getByTestId('model-download-tiny')).toBeDisabled();
  });

  it('surfaces a failed download inline', () => {
    enginesData = status({
      models: [
        {
          name: 'tiny',
          sizeBytes: 78_000_000,
          downloaded: false,
          downloadStatus: 'failed',
          bytesDone: 0,
          bytesTotal: null,
          error: 'sha256 mismatch against the pinned manifest',
        },
      ],
    });
    render(<EnginesPanel />);
    expect(screen.getByRole('alert')).toHaveTextContent('sha256 mismatch');
  });
});
