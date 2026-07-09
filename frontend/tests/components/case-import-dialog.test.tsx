/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CaseImportDialog } from '@/components/case/case-import-dialog';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockRun = vi.fn();
vi.mock('@/hooks/use-import-bundle', () => ({
  useImportBundle: () => ({
    importing: false,
    progress: 0,
    error: '',
    run: mockRun,
    reset: vi.fn(),
  }),
}));

const mockRegister = vi.fn();
vi.mock('@/stores/job-store', () => ({
  useJobStore: (sel: (s: unknown) => unknown) =>
    sel({ registerJob: mockRegister }),
}));

const mockAddToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: mockAddToast }) },
}));

function renderDialog() {
  return render(
    <MemoryRouter>
      <CaseImportDialog open onOpenChange={vi.fn()} />
    </MemoryRouter>,
  );
}

function pickFile(name = 'bundle.zip'): void {
  const input = screen.getByTestId('import-file-input') as HTMLInputElement;
  const file = new File(['zip-bytes'], name, { type: 'application/zip' });
  fireEvent.change(input, { target: { files: [file] } });
}

describe('CaseImportDialog', () => {
  beforeEach(() => {
    mockRun.mockReset();
    mockRegister.mockReset();
    mockAddToast.mockReset();
    mockNavigate.mockReset();
  });

  it('disables import until a file is chosen', () => {
    renderDialog();
    expect(screen.getByTestId('import-submit')).toBeDisabled();
    pickFile();
    expect(screen.getByTestId('import-submit')).not.toBeDisabled();
  });

  it('registers a job and navigates on success', async () => {
    mockRun.mockResolvedValue({
      caseId: 'case-1',
      workflowId: 'bundle-import-case-1',
      signatureStatus: 'signed_trusted',
    });
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByTestId('import-submit'));

    await waitFor(() => expect(mockRegister).toHaveBeenCalled());
    expect(mockRegister).toHaveBeenCalledWith(
      expect.objectContaining({
        workflowId: 'bundle-import-case-1',
        caseId: 'case-1',
        kind: 'bundle_import',
      }),
    );
    expect(mockNavigate).toHaveBeenCalledWith('/cases/case-1');
  });

  it('surfaces an untrusted-signature import in the toast copy', async () => {
    mockRun.mockResolvedValue({
      caseId: 'case-2',
      workflowId: 'bundle-import-case-2',
      signatureStatus: 'signed_untrusted',
    });
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByTestId('import-submit'));

    await waitFor(() => expect(mockAddToast).toHaveBeenCalled());
    const arg = mockAddToast.mock.calls[0][0];
    expect(arg.message).toMatch(/does not trust/);
    expect(arg.type).toBe('info');
  });

  it('does not register a job when the import fails', async () => {
    mockRun.mockResolvedValue(null);
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByTestId('import-submit'));

    await waitFor(() => expect(mockRun).toHaveBeenCalled());
    expect(mockRegister).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
