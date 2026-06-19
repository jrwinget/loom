import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as pdfjs from 'pdfjs-dist';

import { loadPdf } from './pdf';

vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({
  default: 'worker-url',
}));
vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: vi.fn(),
}));

const getDocument = vi.mocked(pdfjs.getDocument);

function fakeTask() {
  const render = vi.fn().mockReturnValue({ promise: Promise.resolve() });
  const getViewport = vi.fn().mockReturnValue({ width: 100.4, height: 200.9 });
  const getPage = vi.fn().mockResolvedValue({ getViewport, render });
  const doc = { numPages: 2, getPage };
  // getDocument returns a loading task: { promise, destroy }
  const destroy = vi.fn();
  return {
    promise: Promise.resolve(doc),
    destroy,
    _render: render,
  };
}

beforeEach(() => {
  getDocument.mockReset();
});

describe('loadPdf', () => {
  it('configures the worker source from the bundled url', () => {
    expect(pdfjs.GlobalWorkerOptions.workerSrc).toBe('worker-url');
  });

  it('exposes the document page count', async () => {
    const task = fakeTask();
    getDocument.mockReturnValue(
      task as unknown as ReturnType<typeof pdfjs.getDocument>,
    );

    const pdf = await loadPdf('http://x/doc.pdf');

    expect(pdf.numPages).toBe(2);
    expect(getDocument).toHaveBeenCalledWith(
      expect.objectContaining({ url: 'http://x/doc.pdf' }),
    );
  });

  it('sizes the canvas to the page viewport and renders', async () => {
    const task = fakeTask();
    getDocument.mockReturnValue(
      task as unknown as ReturnType<typeof pdfjs.getDocument>,
    );

    const pdf = await loadPdf('http://x/doc.pdf');
    const canvas = document.createElement('canvas');
    await pdf.renderPage(1, canvas, 1.5);

    expect(canvas.width).toBe(101);
    expect(canvas.height).toBe(201);
    expect(task._render).toHaveBeenCalledOnce();
  });

  it('destroys the underlying loading task', async () => {
    const task = fakeTask();
    getDocument.mockReturnValue(
      task as unknown as ReturnType<typeof pdfjs.getDocument>,
    );

    const pdf = await loadPdf('http://x/doc.pdf');
    pdf.destroy();

    expect(task.destroy).toHaveBeenCalledOnce();
  });
});
