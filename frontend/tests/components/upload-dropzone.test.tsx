import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { UploadDropzone } from
  '@/components/asset/upload-dropzone';
import { useUploadStore } from '@/hooks/use-upload';

// the dropzone renders StorageAdvisory, which calls into first-run
// and storage hooks. stub them so these tests do not need a live
// backend. useUpload itself needs a QueryClient in scope (it
// invalidates the assets query after a batch).
vi.mock('@/hooks/use-first-run', () => ({
  useFirstRunStatus: () => ({ data: { deploymentProfile: 'server' } }),
}));

vi.mock('@/hooks/use-storage', () => ({
  useStorageUsage: () => ({ data: undefined }),
  useStorageCheck: () => ({
    data: undefined,
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
  }),
}));

function renderDropzone(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <UploadDropzone caseId="case-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // reset upload store between tests
  useUploadStore.setState({ files: [] });
});

describe('UploadDropzone', () => {
  it('renders drop area', () => {
    renderDropzone();
    expect(
      screen.getByTestId('drop-area'),
    ).toBeInTheDocument();
  });

  it('shows browse files button', () => {
    renderDropzone();
    expect(
      screen.getByTestId('browse-button'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Browse files'),
    ).toBeInTheDocument();
  });

  it('displays queued files', () => {
    // pre-populate the store with files
    const mockFile = new File(
      ['test'],
      'photo.jpg',
      { type: 'image/jpeg' },
    );
    useUploadStore.getState().addFiles([mockFile]);

    renderDropzone();

    expect(
      screen.getByText('photo.jpg'),
    ).toBeInTheDocument();
  });
});
