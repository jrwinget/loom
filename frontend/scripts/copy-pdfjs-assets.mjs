// copy pdf.js CMap + standard-font data into public/pdfjs/ so vite serves
// it in dev and emits it to dist/ on build. without these, PDFs that use
// non-embedded standard-14 fonts or CJK encodings render with missing
// glyphs. resolved from the installed package so it tracks the pinned
// pdfjs-dist version; the destination is generated (gitignored).
import { createRequire } from 'node:module';
import { cpSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const pdfjsDir = dirname(require.resolve('pdfjs-dist/package.json'));
const here = dirname(fileURLToPath(import.meta.url));
const dest = resolve(here, '..', 'public', 'pdfjs');

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
for (const sub of ['cmaps', 'standard_fonts']) {
  cpSync(resolve(pdfjsDir, sub), resolve(dest, sub), { recursive: true });
}
console.log(`copied pdf.js cmaps + standard_fonts -> ${dest}`);
