import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUploadStore } from '@/hooks/use-upload';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
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
    const files = [
      new File(['a'], 'a.mp4'),
      new File(['b'], 'b.mp4'),
    ];
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
    const files = [
      new File(['a'], 'a.mp4'),
      new File(['b'], 'b.mp4'),
    ];
    useUploadStore.getState().addFiles(files);
    expect(useUploadStore.getState().files).toHaveLength(2);

    useUploadStore.getState().clear();
    expect(useUploadStore.getState().files).toHaveLength(0);
  });

  it('addFiles preserves existing files', () => {
    useUploadStore.getState().addFiles([
      new File(['a'], 'a.mp4'),
    ]);
    useUploadStore.getState().addFiles([
      new File(['b'], 'b.mp4'),
    ]);

    expect(useUploadStore.getState().files).toHaveLength(2);
  });
});
