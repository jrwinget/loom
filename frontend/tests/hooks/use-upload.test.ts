import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useUpload, useUploadStore } from '@/hooks/use-upload';
import { queryKeys } from '@/lib/query-keys';

const { addToast, uploadAssetXhr } = vi.hoisted(() => ({
  addToast: vi.fn(),
  uploadAssetXhr: vi.fn(),
}));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

vi.mock('@/hooks/use-assets', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  uploadAssetXhr,
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast }),
  },
}));

describe('useUploadStore', () => {
  beforeEach(() => {
    useUploadStore.setState({ files: [] });
  });

  it('starts with empty files', () => {
    expect(useUploadStore.getState().files).toHaveLength(0);
  });

  it('addFiles adds files from array', () => {
    const files = [
      new File(['content'], 'video.mp4', { type: 'video/mp4' }),
      new File(['content'], 'photo.jpg', { type: 'image/jpeg' }),
    ];

    useUploadStore.getState().addFiles(files);

    const state = useUploadStore.getState();
    expect(state.files).toHaveLength(2);
    expect(state.files[0]?.file.name).toBe('video.mp4');
    expect(state.files[1]?.file.name).toBe('photo.jpg');
    expect(state.files[0]?.status).toBe('pending');
    expect(state.files[0]?.progress).toBe(0);
  });

  it('addFiles generates unique ids', () => {
    const file = new File(['x'], 'a.mp4');
    useUploadStore.getState().addFiles([file]);
    useUploadStore.getState().addFiles([file]);

    const ids = useUploadStore.getState().files.map((f) => f.id);
    expect(new Set(ids).size).toBe(2);
  });

  it('removeFile removes by id', () => {
    const file = new File(['x'], 'a.mp4');
    useUploadStore.getState().addFiles([file]);

    const id = useUploadStore.getState().files[0]?.id;
    expect(id).toBeTruthy();

    useUploadStore.getState().removeFile(id!);
    expect(useUploadStore.getState().files).toHaveLength(0);
  });

  it('removeFile ignores unknown id', () => {
    const file = new File(['x'], 'a.mp4');
    useUploadStore.getState().addFiles([file]);

    useUploadStore.getState().removeFile('nonexistent');
    expect(useUploadStore.getState().files).toHaveLength(1);
  });

  it('updateFile patches matching file', () => {
    const file = new File(['x'], 'a.mp4');
    useUploadStore.getState().addFiles([file]);

    const id = useUploadStore.getState().files[0]?.id;
    expect(id).toBeTruthy();

    useUploadStore.getState().updateFile(id!, {
      status: 'uploading',
      progress: 50,
    });

    const updated = useUploadStore.getState().files[0];
    expect(updated?.status).toBe('uploading');
    expect(updated?.progress).toBe(50);
  });

  it('updateFile does not affect other files', () => {
    const files = [new File(['a'], 'a.mp4'), new File(['b'], 'b.mp4')];
    useUploadStore.getState().addFiles(files);

    const id = useUploadStore.getState().files[0]?.id;
    useUploadStore.getState().updateFile(id!, {
      status: 'complete',
      progress: 100,
    });

    const second = useUploadStore.getState().files[1];
    expect(second?.status).toBe('pending');
    expect(second?.progress).toBe(0);
  });

  it('clear removes all files', () => {
    const files = [new File(['a'], 'a.mp4'), new File(['b'], 'b.mp4')];
    useUploadStore.getState().addFiles(files);
    expect(useUploadStore.getState().files).toHaveLength(2);

    useUploadStore.getState().clear();
    expect(useUploadStore.getState().files).toHaveLength(0);
  });

  it('addFiles preserves existing files', () => {
    useUploadStore.getState().addFiles([new File(['a'], 'a.mp4')]);
    useUploadStore.getState().addFiles([new File(['b'], 'b.mp4')]);

    expect(useUploadStore.getState().files).toHaveLength(2);
  });
});

describe('useUpload uploadAll', () => {
  let queryClient: QueryClient;

  function renderUpload(): ReturnType<
    typeof renderHook<ReturnType<typeof useUpload>, unknown>
  > {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return renderHook(() => useUpload(), {
      wrapper: ({ children }) =>
        createElement(QueryClientProvider, { client: queryClient }, children),
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    useUploadStore.setState({ files: [] });
  });

  it('refreshes the asset grid and toasts a summary on success', async () => {
    uploadAssetXhr.mockResolvedValue({ id: 'asset-1' });
    const { result } = renderUpload();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    act(() => {
      result.current.addFiles([
        new File(['a'], 'a.mp4'),
        new File(['b'], 'b.mp4'),
      ]);
    });
    await act(async () => {
      await result.current.uploadAll('case-1');
    });

    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.assets.byCase('case-1'),
    });
    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: '2 files uploaded',
    });
    const statuses = useUploadStore.getState().files.map((f) => f.status);
    expect(statuses).toEqual(['complete', 'complete']);
  });

  it('surfaces the backend detail and counts failures in the summary', async () => {
    uploadAssetXhr
      .mockResolvedValueOnce({ id: 'asset-1' })
      .mockRejectedValueOnce(new Error('file type not allowed'));
    const { result } = renderUpload();

    act(() => {
      result.current.addFiles([
        new File(['a'], 'a.mp4'),
        new File(['b'], 'b.exe'),
      ]);
    });
    await act(async () => {
      await result.current.uploadAll('case-1');
    });

    const failedEntry = useUploadStore
      .getState()
      .files.find((f) => f.status === 'error');
    expect(failedEntry?.error).toBe('file type not allowed');
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: '1 uploaded, 1 failed',
    });
  });

  it('does not refresh or toast when nothing was pending', async () => {
    const { result } = renderUpload();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    await act(async () => {
      await result.current.uploadAll('case-1');
    });

    expect(invalidate).not.toHaveBeenCalled();
    expect(addToast).not.toHaveBeenCalled();
  });
});
