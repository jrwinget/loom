#!/usr/bin/env bash
#
# apply branch protections to main and dev.
#
# requires the repo to be public OR on a paid GitHub plan
# (Pro / Team / Enterprise). on free-tier private repos
# both the branch-protection and rulesets APIs return 403
# with "Upgrade to GitHub Pro or make this repository public
# to enable this feature."
#
# usage:
#   ./.github/branch-protection/apply.sh
#
# requires: gh CLI authenticated against a token with the
# repo "administration:write" permission (the default
# user-level token has this for repos you own).

set -euo pipefail

REPO="${LOOM_REPO:-jrwinget/loom}"
HERE="$(dirname "$0")"

apply_one() {
    local branch="$1"
    local file="$2"
    echo "applying $file to $REPO@$branch ..."
    gh api \
        --method PUT \
        --header "Accept: application/vnd.github+json" \
        "repos/$REPO/branches/$branch/protection" \
        --input "$file"
}

apply_one main "$HERE/main.json"
apply_one dev  "$HERE/dev.json"

echo "done. verify at: https://github.com/$REPO/settings/branches"
