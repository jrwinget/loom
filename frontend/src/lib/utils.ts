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
