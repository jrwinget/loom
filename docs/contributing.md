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

### Generated API types

`frontend/src/types/generated/api.d.ts` is generated from the backend
OpenAPI schema and checked in; CI fails when a backend schema change
lands without regenerating (`make typegen`). Adoption rule: new or
modified API-touching code imports from `types/generated` (use the
`Camel<T>` mapper for post-camelization shapes); the hand-written
`types/*.ts` files are frozen — no new fields — and shrink as modules
migrate. Compile-time assertions in
`src/types/__tests__/generated-contract.test-d.ts` keep the remaining
hand-written types honest against the wire.

## Tests

- Backend: `pytest` with `pytest-asyncio` (≥86% coverage gate)
- Frontend: Vitest with React Testing Library + MSW
  (≥90% coverage gate)
- E2E: Playwright

Run `make test` before pushing. CI rejects PRs that drop
backend coverage below 86% or frontend coverage below 90%.

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

Branch protections are checked in under
[`.github/branch-protection/`](../.github/branch-protection/)
and applied to the repo; edit the JSON there and re-run
`apply.sh` rather than changing settings in the GitHub UI.

Branch names are enforced in CI by the Branch Guard workflow:
`<type>/<kebab>` where type is one of `feat|feature|fix|
hotfix|chore|docs|test|ci|refactor|perf|build`, or
`release/<semver>` for promotions.

## Local hooks and versioning

Enable the repo's git hooks once per clone:

```bash
make hooks
```

Hooks come from [`.pre-commit-config.yaml`](../.pre-commit-config.yaml):

- **pre-commit** lints exactly what is staged (ruff for
  `backend/**.py`, eslint + prettier + tsc for
  `frontend/src/**.ts{,x}`, plus whitespace / large-file /
  merge-conflict / yaml checks), so it stays fast.
- **pre-push** runs `scripts/check-version-sync.sh`: the five
  version-bearing files (`backend/pyproject.toml`,
  `frontend/package.json`, `desktop/package.json`,
  `desktop/src-tauri/tauri.conf.json`,
  `desktop/src-tauri/Cargo.toml`) must agree, and a
  `release/*` branch name must match that version.

Never edit version numbers by hand — bump all five files in
lockstep with:

```bash
scripts/bump-version.sh 0.2.0
```

CI repeats the sync check as the required `Verify Versions`
job, so a drifted version can't merge even without the hooks.

After a bump, run `make typegen`: the exported OpenAPI schema
embeds the app version, so the checked-in `backend/openapi.json`
drifts (and the Contract Typegen CI job fails) until it is
regenerated.

## Dependency updates

Dependabot runs weekly (Monday) against **`dev`** for the
backend (uv), frontend (npm), desktop shell (npm + cargo),
and GitHub Actions. Non-major bumps are grouped per
ecosystem and squash-auto-merged once the required checks
pass. Major bumps wait for manual review.

## Commits and pull requests

- Branch off **`dev`** with a short topical name
  (`fix/<n>-...`, `feat/<n>-...`, `docs/...`, `chore/...`).
  Use `release/<version>` for `dev` → `main` promotions.
- Keep commits focused: one concern per commit, present-tense
  summary line, 2-4 bullet points explaining the *why* below.
- Use `Fixes #<n>` (or `Closes #<n>`) trailers when a PR
  resolves an issue. **Do not include `Co-authored-by`
  trailers.**
- Open feature PRs against **`dev`**. `dev` requires version
  sync, lint, unit tests, and migrations; it strips the two
  slowest checks (Security Scan, Build & Verify) for fast
  iteration. Those still run on every PR — they just don't
  block `dev` merges.
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
