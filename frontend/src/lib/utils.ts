import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// asset bytes are served cross-origin by the sidecar, so the <a download>
// attribute is ignored by the browser. ask the endpoint for an attachment
// content-disposition so the file saves instead of navigating/previewing.
export function attachmentHref(src: string): string {
  if (!src) return src;
  return `${src}${src.includes('?') ? '&' : '?'}disposition=attachment`;
}

// minio presigned urls reject extra query params (unsigned params break
// the sigv4 check), so downloads fetched imperatively navigate a
// synthetic anchor to the url exactly as signed.
export function triggerDownload(url: string): void {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
