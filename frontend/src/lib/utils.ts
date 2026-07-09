import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

// minio presigned urls reject extra query params (unsigned params break
// the sigv4 check), so downloads fetched imperatively navigate a
// synthetic anchor to the url exactly as signed. the content-disposition
// is signed into the url by the backend, so no client-side append.
export function triggerDownload(url: string): void {
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
