/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { describe, expect, it, vi } from 'vitest';
import { SceneBrowser } from '@/components/review/scene-browser';
import type { SceneInfo } from '@/types/transcript';

function makeScene(overrides: Partial<SceneInfo> = {}): SceneInfo {
  return {
    id: 's1',
    assetId: 'asset-1',
    sceneNumber: 1,
    startTime: 0,
    endTime: 30,
    thumbnailUrl: null,
    duration: 30,
    modelName: 'pyscenedetect',
    modelVersion: '0.6',
    modelParams: null,
    ...overrides,
  };
}

const scenes: SceneInfo[] = [
  makeScene(),
  makeScene({ id: 's2', sceneNumber: 2, startTime: 30, endTime: 90 }),
];

describe('SceneBrowser', () => {
  it('shows an empty state when there are no scenes', () => {
    render(<SceneBrowser scenes={[]} currentTime={0} onSeek={vi.fn()} />);

    expect(screen.getByText('No scenes detected')).toBeInTheDocument();
  });

  it('marks the scene containing the current time as active', () => {
    render(<SceneBrowser scenes={scenes} currentTime={45} onSeek={vi.fn()} />);

    expect(screen.getByTestId('scene-s2')).toHaveAttribute(
      'data-active',
      'true',
    );
    expect(screen.getByTestId('scene-s1')).toHaveAttribute(
      'data-active',
      'false',
    );
  });

  it('seeks to the scene start time when a scene is clicked', async () => {
    const user = userEvent.setup();
    const onSeek = vi.fn();
    render(<SceneBrowser scenes={scenes} currentTime={0} onSeek={onSeek} />);

    await user.click(screen.getByTestId('scene-s2'));

    expect(onSeek).toHaveBeenCalledWith(30);
  });

  it('labels each scene with its formatted time range', () => {
    render(<SceneBrowser scenes={scenes} currentTime={0} onSeek={vi.fn()} />);

    expect(
      screen.getByRole('button', { name: 'Scene 2: 00:30 to 01:30' }),
    ).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <SceneBrowser scenes={scenes} currentTime={45} onSeek={vi.fn()} />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
