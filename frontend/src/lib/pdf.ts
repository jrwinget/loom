// thin wrapper around pdf.js so the rest of the app depends on our own
// small interface (and tests mock this, not the third-party lib). we render
// pages ourselves instead of relying on the webview's native pdf viewer,
// which WebKitGTK (the linux desktop webview) does not have.
import * as pdfjs from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export interface LoadedPdf {
  readonly numPages: number;
  renderPage(
    pageNumber: number,
    canvas: HTMLCanvasElement,
    scale: number,
  ): Promise<void>;
  destroy(): void;
}

// pdf.js CMap + standard-font assets, copied into the bundle by
// vite-plugin-static-copy (see vite.config.ts). BASE_URL keeps the path
// correct under both the desktop (root) and any sub-path web deploy.
const PDF_ASSET_BASE = `${import.meta.env.BASE_URL}pdfjs/`;

export async function loadPdf(url: string): Promise<LoadedPdf> {
  const task = pdfjs.getDocument({
    url,
    cMapUrl: `${PDF_ASSET_BASE}cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `${PDF_ASSET_BASE}standard_fonts/`,
  });
  const doc = await task.promise;
  return {
    numPages: doc.numPages,
    async renderPage(pageNumber, canvas, scale) {
      const page = await doc.getPage(pageNumber);
      const viewport = page.getViewport({ scale });
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvas, viewport }).promise;
    },
    destroy() {
      // tearing down the loading task aborts the request and the worker.
      void task.destroy();
    },
  };
}
