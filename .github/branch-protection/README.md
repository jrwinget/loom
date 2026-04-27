# Branch protection

Checked-in branch-protection configs for `main` and `dev`,
plus a one-shot script to apply them. The configs match the
two-trunk workflow described in
[`docs/contributing.md`](../../docs/contributing.md).

## Why this is in the repo

`jrwinget/loom` is currently a **free-tier private** GitHub
repository. Branch-protection and ruleset APIs are gated
behind GitHub Pro on private repos and return:

> Upgrade to GitHub Pro or make this repository public to
> enable this feature.

These configs cannot be applied today. They live in the repo
so that the moment the repo goes public (or upgrades to a
paid plan) the protections are a one-shot `gh api` call away
— no model-design work needed at that moment.

## Files

- **`main.json`** — protection for the release branch. Full
  CI must pass, conversation resolution required, linear
  history, no force pushes, no deletions, 1 review. Mirrors
  `Beesystrategy/capacity-calc`'s `main` rules adapted to
  the Loom check names.
- **`dev.json`** — relaxed integration-branch protection.
  Strips the slowest checks (`Security Scan`, `Build &
  Verify`) for fast iteration; keeps lint + unit tests +
  migrations. Force pushes allowed for clean rebases.
- **`apply.sh`** — applies both configs via `gh api`.

## Applying

Once the repo is public (or upgraded), run:

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
    --jq '{checks: .required_status_checks.contexts, reviews: .required_pull_request_reviews.required_approving_review_count, linear: .required_linear_history.enabled}'
gh api repos/jrwinget/loom/branches/dev/protection \
    --jq '{checks: .required_status_checks.contexts, reviews: .required_pull_request_reviews.required_approving_review_count, force_push: .allow_force_pushes.enabled}'
```

Or visit <https://github.com/jrwinget/loom/settings/branches>.

## Adjusting for solo development

If you're the only committer, the `required_approving_review_count: 1`
rule on both branches blocks self-merge. Two options:

1. **Drop the review requirement** by setting
   `required_pull_request_reviews` to `null` in `main.json` /
   `dev.json` and re-applying. Status checks still gate
   merges.
2. **Keep the rule and use admin override** by setting
   `enforce_admins: false` (already set) and having the
   maintainer click "merge without waiting for requirements"
   in the PR UI when no other reviewer is available.

Option 2 keeps the audit trail honest (every merge is logged
as an admin override) and matches the capacity-calc
pattern.
