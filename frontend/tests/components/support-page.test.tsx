/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SupportPage } from '@/routes/settings/support';

const mocks = vi.hoisted(() => ({
  isTauri: true,
  exportDiagnostics: vi.fn<() => Promise<string | null>>(),
}));

vi.mock('@/lib/tauri-bridge', () => ({
  get isTauri() {
    return mocks.isTauri;
  },
  exportDiagnostics: mocks.exportDiagnostics,
}));

describe('SupportPage', () => {
  beforeEach(() => {
    mocks.isTauri = true;
    mocks.exportDiagnostics.mockReset();
    // the page reads the backend version from /openapi.json
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ info: { version: '1.2.3' } }),
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the diagnostics copy and log locations', () => {
    render(<SupportPage />);

    expect(
      screen.getByRole('heading', { name: 'Support' }),
    ).toBeInTheDocument();
    // the contains/excludes contract is user-facing safety copy
    expect(
      screen.getByText(/never includes your evidence/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/backend\.jsonl/)).toBeInTheDocument();
  });

  it('shows the backend version from the openapi document', async () => {
    render(<SupportPage />);

    expect(await screen.findByText(/Loom backend: 1\.2\.3/)).toBeVisible();
  });

  it('disables the export button outside the desktop app', () => {
    mocks.isTauri = false;
    render(<SupportPage />);

    expect(
      screen.getByRole('button', { name: 'Export diagnostics…' }),
    ).toBeDisabled();
    expect(
      screen.getByText('Diagnostics export is available in the desktop app.'),
    ).toBeInTheDocument();
  });

  it('shows the saved path after a successful export', async () => {
    mocks.exportDiagnostics.mockResolvedValueOnce('/tmp/loom-diag.zip');
    const user = userEvent.setup();
    render(<SupportPage />);

    await user.click(
      screen.getByRole('button', { name: 'Export diagnostics…' }),
    );

    expect(await screen.findByRole('status')).toHaveTextContent(
      'Saved to /tmp/loom-diag.zip',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('stays quiet when the user cancels the save dialog', async () => {
    mocks.exportDiagnostics.mockResolvedValueOnce(null);
    const user = userEvent.setup();
    render(<SupportPage />);

    await user.click(
      screen.getByRole('button', { name: 'Export diagnostics…' }),
    );

    expect(mocks.exportDiagnostics).toHaveBeenCalledOnce();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces an export failure as an alert', async () => {
    mocks.exportDiagnostics.mockRejectedValueOnce(
      new Error('cannot create /tmp/loom-diag.zip: permission denied'),
    );
    const user = userEvent.setup();
    render(<SupportPage />);

    await user.click(
      screen.getByRole('button', { name: 'Export diagnostics…' }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'cannot create /tmp/loom-diag.zip: permission denied',
    );
  });

  it('has no axe violations', async () => {
    const { container } = render(<SupportPage />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
