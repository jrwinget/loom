# Branch protection

Checked-in branch-protection configs for `main` and `dev`,
plus a one-shot script to apply them. The configs match the
two-trunk workflow described in
[`docs/contributing.md`](../../docs/contributing.md).

These are **applied** (the repo is public). The files remain
the source of truth: edit here, then re-run `apply.sh` —
never adjust protections only in the GitHub UI, or the next
apply will silently revert them.

## Files

- **`main.json`** — protection for the release branch. Full
  CI must pass (including `Verify Versions`, `Security Scan`
  and `Build & Verify`), conversation resolution required,
  linear history, no force pushes, no deletions.
- **`dev.json`** — relaxed integration-branch protection.
  Strips the two slowest checks (`Security Scan`, `Build &
  Verify`) for fast iteration; keeps version sync + lint +
  unit tests + migrations. Force pushes allowed for clean
  rebases.
- **`apply.sh`** — applies both configs via `gh api`.

Neither branch requires an approving review: this is a
solo-maintainer repo and a review requirement would block
self-merge. Status checks gate every merge instead, and the
Dependabot auto-merge workflow adds its own approval. Add a
`required_pull_request_reviews` block back when a second
maintainer joins.

`Validate branch name` (branch-guard) is deliberately not a
required check: it is skipped for `dependabot/*` branches,
and a skipped run would otherwise hold those PRs forever.
It still fails visibly on misnamed human branches.

## Applying

```bash
./.github/branch-protection/apply.sh
```

The script requires `gh` authenticated against a token with
`administration:write` on the repo (the default user token
has this for repos you own).

To target a fork or a transferred repo, set
`LOOM_REPO=owner/repo` in the environment.

## Verifying

After applying:

```bash
gh api repos/jrwinget/loom/branches/main/protection \
    --jq '{checks: .required_status_checks.contexts, linear: .required_linear_history.enabled}'
gh api repos/jrwinget/loom/branches/dev/protection \
    --jq '{checks: .required_status_checks.contexts, force_push: .allow_force_pushes.enabled}'
```

Or visit <https://github.com/jrwinget/loom/settings/branches>.
