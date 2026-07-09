# End-to-end tests

Playwright smoke tests that drive the real UI against a real
lite-profile backend — the same `python -m loom` entrypoint (and
schema bootstrap) the desktop sidecar uses.

## Running locally

```bash
cd frontend
pnpm exec playwright install chromium   # once
pnpm test:e2e
```

Playwright starts both servers itself (see `playwright.config.ts`):

- `scripts/e2e-backend.sh` — lite backend on `127.0.0.1:8000` with a
  fresh SQLite database and data dir under
  `${TMPDIR:-/tmp}/loom-e2e-backend` (wiped at startup)
- `pnpm dev` — Vite on `localhost:3000`, proxying `/api`

Both ports must be free: the smoke spec exercises the first-run flow
and requires an empty database, so `reuseExistingServer` is
deliberately `false`. Stop any running dev servers first.

## Conventions

- Specs are named `*.spec.ts` so Vitest (which only includes
  `*.test.*` under `tests/` and `src/`) never picks them up, and
  `tsconfig.json` (`include: ["src"]`) doesn't typecheck them —
  Playwright transpiles them itself.
- Auth tokens are held in memory only. Never `page.goto()` or reload
  after logging in; navigate by clicking links.
- Prefer role/label/placeholder selectors; fall back to the
  `data-testid` attributes that already exist in components.
- Use `test.step()` so failures name the journey stage.

## Flake policy

CI retries twice (`retries: 2`) and uploads the HTML report and
traces on failure. If a spec needs a retry more than occasionally,
treat it as broken: find the missing await/assertion rather than
raising timeouts. Under WSL2, the first run is slow while uv and
Vite warm their caches — the 120s `webServer` timeout accounts for
this; don't shorten it.
