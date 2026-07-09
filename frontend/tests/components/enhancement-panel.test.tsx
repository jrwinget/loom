/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EnhancementPanel } from '@/components/review/enhancement-panel';
import type {
  EnhancementDerivative,
  EnhancementSuggestion,
} from '@/hooks/use-enhancements';
import type { EngineCapability } from '@/hooks/use-capabilities';

const mockSuggest = vi.fn();
const mockCreate = vi.fn();

let enhancements: EnhancementDerivative[] = [];
let mediaPipeline: EngineCapability = {
  status: 'available',
  remedy: null,
  version: null,
};

vi.mock('@/hooks/use-capabilities', () => ({
  useCapabilities: () => ({
    data: { engines: { mediaPipeline } },
  }),
}));

vi.mock('@/hooks/use-enhancements', () => ({
  NEUTRAL_PARAMS: {
    brightness: 0,
    contrast: 1,
    saturation: 1,
    gamma: 1,
    denoise: 0,
    sharpen: 0,
    deinterlace: false,
    scaleFactor: 1,
  },
  useEnhancements: () => ({ data: enhancements }),
  useSuggestEnhancement: () => ({ mutate: mockSuggest, isPending: false }),
  useCreateEnhancement: () => ({ mutate: mockCreate, isPending: false }),
}));

function renderPanel(): void {
  render(<EnhancementPanel caseId="c1" assetId="a1" filename="clip.mp4" />);
}

describe('EnhancementPanel', () => {
  beforeEach(() => {
    enhancements = [];
    mediaPipeline = { status: 'available', remedy: null, version: null };
    mockSuggest.mockReset();
    mockCreate.mockReset();
  });

  it('states the deterministic-only policy plainly', () => {
    renderPanel();
    expect(screen.getByTestId('enhancement-policy')).toHaveTextContent(
      'Deterministic filters only — no AI, no super-resolution.',
    );
  });

  it('pre-fills parameters and lists reasons after suggest', () => {
    const suggestion: EnhancementSuggestion = {
      params: {
        brightness: 0.12,
        contrast: 1.3,
        saturation: 1,
        gamma: 1.4,
        denoise: 4,
        sharpen: 0,
        deinterlace: true,
        scaleFactor: 2,
      },
      reasons: [
        'footage is very dark (luma avg 30) -> gamma 1.4',
        'interlacing detected -> deinterlace (yadif)',
      ],
    };
    mockSuggest.mockImplementation((_vars, opts) => opts?.onSuccess?.(suggestion));

    renderPanel();
    fireEvent.click(screen.getByTestId('enhancement-suggest'));

    expect(mockSuggest).toHaveBeenCalled();
    // the gamma value display reflects the pre-filled suggestion
    expect(screen.getByTestId('enhancement-reasons')).toHaveTextContent(
      'interlacing detected',
    );
    const gamma = screen.getByLabelText(/Gamma/) as HTMLInputElement;
    expect(gamma.value).toBe('1.4');
  });

  it('dispatches an enhancement run with the current parameters', () => {
    renderPanel();
    fireEvent.click(screen.getByTestId('enhancement-run'));
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({ scaleFactor: 1, brightness: 0 }),
    );
  });

  it('shows the provenance of a produced enhancement', () => {
    enhancements = [
      {
        id: 'd1',
        downloadUrl: 'http://storage/enh/d1.mp4?sig=x',
        createdAt: '2026-07-09T00:00:00Z',
        generationParams: {
          modelName: 'ffmpeg-deterministic-filter',
          modelVersion: '7.1',
          modelParams: { brightness: 0.2, filterChain: 'eq=brightness=0.2' },
        },
      },
    ];
    renderPanel();

    expect(screen.getByTestId('enhancement-item')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('why-popover-trigger'));
    const popover = screen.getByTestId('why-popover-content');
    expect(popover).toHaveTextContent('ffmpeg-deterministic-filter');
    expect(popover).toHaveTextContent('eq=brightness=0.2');
  });

  it('gates on media-pipeline availability with the remedy', () => {
    mediaPipeline = {
      status: 'missing',
      remedy: 'install ffmpeg and put it on PATH',
      version: null,
    };
    renderPanel();

    expect(screen.getByTestId('enhancement-unavailable')).toHaveTextContent(
      'install ffmpeg and put it on PATH',
    );
    expect(screen.getByTestId('enhancement-run')).toBeDisabled();
    expect(screen.getByTestId('enhancement-suggest')).toBeDisabled();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <EnhancementPanel caseId="c1" assetId="a1" filename="clip.mp4" />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
