// shared formatting helpers.

const BYTE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

export function formatBytes(bytes: number, fractionDigits = 1): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '0 B';
  }
  const k = 1024;
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(k)),
    BYTE_UNITS.length - 1,
  );
  const val = bytes / Math.pow(k, i);
  // integers render without trailing zeroes for bytes.
  const digits = i === 0 ? 0 : fractionDigits;
  return `${val.toFixed(digits)} ${BYTE_UNITS[i]}`;
}
