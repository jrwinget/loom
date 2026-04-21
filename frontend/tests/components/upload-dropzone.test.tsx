import { render, screen } from '@testing-library/react';
import { describe, expect, it, beforeEach } from 'vitest';
import { UploadDropzone } from
  '@/components/asset/upload-dropzone';
import { useUploadStore } from '@/hooks/use-upload';

beforeEach(() => {
  // reset upload store between tests
  useUploadStore.setState({ files: [] });
});

describe('UploadDropzone', () => {
  it('renders drop area', () => {
    render(<UploadDropzone caseId="case-1" />);
    expect(
      screen.getByTestId('drop-area'),
    ).toBeInTheDocument();
  });

  it('shows browse files button', () => {
    render(<UploadDropzone caseId="case-1" />);
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

    render(<UploadDropzone caseId="case-1" />);

    expect(
      screen.getByText('photo.jpg'),
    ).toBeInTheDocument();
  });
});
