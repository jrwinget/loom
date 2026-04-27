# Contributing

Thanks for your interest in improving Loom. This doc covers the
practical bits — how to get a working dev environment, how the
codebase is laid out, and what's expected of a pull request.

## Development setup

You need Python 3.12+, Node 22+ with pnpm 10, Docker + Docker
Compose, and [uv](https://docs.astral.sh/uv/). Then:

```bash
git clone https://github.com/jrwinget/loom.git
cd loom
cp .env.example .env             # populate the required vars
make up                          # start postgres, minio, temporal
cd backend && uv sync --all-extras && cd ..
cd frontend && pnpm install && cd ..
make migrate                     # run database migrations
make dev                         # start backend + frontend
```

The compose stack now refuses to start without `LOOM_SECRET_KEY`,
`POSTGRES_PASSWORD`, `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`,
and `GRAFANA_ADMIN_PASSWORD` set in `.env`. The example file
ships sensible dev sentinels; production must override them.

API: <http://localhost:8000/docs>. Frontend:
<http://localhost:3000>.

## Code style

### Python (backend)

- 4-space indent, 80-char lines
- Type hints on every function signature; `mypy` is in strict
  mode
- Ruff for linting and formatting
- Inline comments lowercase; user-facing strings and commits
  properly cased
- Max cyclomatic complexity 10

### TypeScript (frontend)

- 2-space indent, 80-char lines
- Strict mode, no `any` (use `unknown` and narrow at boundaries)
- Single quotes, trailing commas (Prettier)
- ESLint with `--max-warnings=0`
- Inline comments lowercase

## Tests

- Backend: `pytest` with `pytest-asyncio` (≥90% coverage gate)
- Frontend: Vitest with React Testing Library + MSW
  (≥90% coverage gate)
- E2E: Playwright

Run `make test` before pushing. CI rejects PRs that drop
coverage below 90% on either side.

## Branching model

Loom follows a **two-trunk** model:

```
feature/* ──► dev ──► main
```

- **`main`** is the release branch. Every commit on `main`
  represents a state we'd ship — Desktop installers and
  production-server deploys are cut from here. Strict
  protection: full CI must pass, conversation resolution
  required, linear history, no force pushes.
- **`dev`** is the integration branch. Day-to-day work
  lands here first, after a lighter checks pass. This lets
  multiple in-progress features cohabit before being
  promoted as a batch to `main`.
- **`feature/*` / `fix/*` / `docs/*` / `chore/*`** are
  short-lived topic branches off `dev`. One concern per
  branch.

Promotion to `main` happens via a release PR from `dev`,
generally batching several merged feature PRs.

The intended branch protections are checked in under
[`.github/branch-protection/`](../.github/branch-protection/).
They cannot be applied directly while the repo is on the
free-tier private plan; a one-shot apply script is included
for the moment the repo goes public (or upgrades).

## Commits and pull requests

- Branch off **`dev`** with a short topical name
  (`fix/<n>-...`, `feat/<n>-...`, `docs/...`, `chore/...`).
  Use `release/<version>` for `dev` → `main` promotions.
- Keep commits focused: one concern per commit, present-tense
  summary line, 2-4 bullet points explaining the *why* below.
- Use `Fixes #<n>` (or `Closes #<n>`) trailers when a PR
  resolves an issue. **Do not include `Co-authored-by`
  trailers.**
- Open feature PRs against **`dev`**. The full check set
  (lint, tests, migrations, security scan, Docker build)
  must pass before merge. `dev` strips the slowest checks
  (Security Scan, Build & Verify) for fast iteration once
  protections are applied; for now run them locally with
  `make lint && make test` before pushing.
- Open release PRs from `dev` against **`main`**. The full
  check set is required.
- Squash-merge is the default — keeps the history scannable
  and the linear-history requirement satisfiable.

For larger pieces of work, please open an issue first so we
can talk through the design before code lands. The
[core principles in the README](../README.md#security-approach)
and the [beta requirements doc](requirements.md) are constraints,
not suggestions; PRs that conflict with them will be redirected.

## Issue scope

When filing an issue, scope it to one concern (backend OR
frontend OR docs OR a single question). Umbrella trackers
covering many unrelated items are hard to act on; we'll ask
to split them.

## Architecture decisions

Major changes should reference
[`docs/architecture.md`](architecture.md). The evidence-spine
model — originals are immutable, derivatives are regenerable,
chain of custody is append-only, contradictions are surfaced —
is load-bearing across the product.
