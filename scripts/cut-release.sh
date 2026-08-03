#!/usr/bin/env bash
# cut a release, encoding the process that three releases' worth of
# footguns taught us:
#   - v0.1.1: assets appended across two workflow runs onto one
#     release page (softprops append semantics),
#   - v0.2.0: the openapi schema embeds the version, so a bump
#     without a regenerate drifts the checked-in contract,
#   - v0.2.1: the macos updater archive was missing, and the fix
#     meant delete-release + re-tag by hand,
#   - v0.2.7: squash-merging a release PR leaves main and dev
#     diverged on the version-embedding files; the back-merge
#     skipped after v0.2.6 made the v0.2.7 release PR conflict on
#     all seven of them, silently starving it of pull_request ci
#     (issue #391).
#
# three subcommands:
#   prepare <version>  bump all five version files, regenerate the
#                      version-embedding contract, verify the release
#                      notes exist, and leave a release/<version>
#                      branch staged for a PR to main. runs no git
#                      push and creates no tag — the human opens the
#                      release PR and merges it.
#   tag <version>      after the release PR has merged to main: verify
#                      main carries the version, then create and push
#                      the annotated tag that triggers the installer
#                      + updater-manifest build.
#   reconcile <version>
#                      after the release is published: merge
#                      origin/main back into dev and push, so the
#                      squash-merged version bump doesn't leave the
#                      next release PR conflicting on the
#                      version-embedding files. caveat: dev's branch
#                      protection requires linear history, so pushing
#                      this merge commit relies on the operator's
#                      admin bypass — every main→dev reconcile merge
#                      to date has landed that way.
#
# usage:
#   scripts/cut-release.sh prepare 0.2.2
#   scripts/cut-release.sh tag 0.2.2
#   scripts/cut-release.sh reconcile 0.2.2
set -euo pipefail

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

die() {
    echo "cut-release: $*" >&2
    exit 1
}

require_semver() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][a-z0-9]+)*$ ]] \
        || die "version must be semver, got '$1'"
}

notes_path() {
    echo "docs/release-notes/v$1.md"
}

cmd_prepare() {
    local version="$1"
    require_semver "$version"

    local notes
    notes="$(notes_path "$version")"
    [[ -f "$notes" ]] || die \
        "release notes $notes must exist before preparing the release"
    [[ -s "$notes" ]] || die "release notes $notes are empty"

    # a release is cut from dev; refuse to prepare from a dirty tree
    # so the bump commit is exactly the version change.
    [[ -z "$(git status --porcelain)" ]] \
        || die "working tree is dirty; commit or stash first"

    local branch="release/v$version"
    git rev-parse --verify "$branch" >/dev/null 2>&1 \
        && die "branch $branch already exists"
    git switch -c "$branch"

    scripts/bump-version.sh "$version"

    # the openapi schema embeds the app version; regenerate the
    # checked-in contract so the contract-typegen ci job stays green.
    make typegen

    # fail now, locally, if anything drifted — the same checks ci
    # runs, so a green prepare means a green release PR.
    scripts/check-version-sync.sh "$branch"

    git add -A
    git commit -m "chore(release): bump version to $version"

    cat <<EOF

prepared release/v$version.
next:
  1. push:            git push -u origin release/v$version
  2. open a PR to main, let the full check set pass, squash-merge it
     as "Release v$version: <summary>"
  3. tag:             scripts/cut-release.sh tag $version
EOF
}

cmd_tag() {
    local version="$1"
    require_semver "$version"
    local tag="v$version"

    git rev-parse -q --verify "refs/tags/$tag" >/dev/null \
        && die "tag $tag already exists"

    # the tag must land on main, and main must actually carry this
    # version — guards against tagging before the release PR merged.
    git fetch --quiet origin main
    local main_version
    main_version=$(git show origin/main:backend/pyproject.toml \
        | grep -m1 '^version' \
        | sed -E 's/version *= *"([^"]+)".*/\1/')
    [[ "$main_version" == "$version" ]] || die \
        "origin/main is at '$main_version', not '$version' — merge the" \
        "release PR first"

    local notes
    notes="$(notes_path "$version")"
    git show "origin/main:$notes" >/dev/null 2>&1 \
        || die "release notes $notes are not on main"

    git tag -a "$tag" origin/main -m "Loom $tag"
    git push origin "$tag"

    echo "tagged and pushed $tag — the desktop workflow will build"
    echo "installers and the updater manifest onto the release."
    echo "publish the notes body with:"
    echo "  gh release create $tag --verify-tag --title $tag \\"
    echo "    --notes-file $notes"
    echo "then merge main back into dev so the next release PR"
    echo "doesn't conflict on the version files:"
    echo "  scripts/cut-release.sh reconcile $version"
}

cmd_reconcile() {
    local version="$1"
    require_semver "$version"
    local tag="v$version"

    [[ -z "$(git status --porcelain)" ]] \
        || die "working tree is dirty; commit or stash first"

    git fetch --quiet origin main dev --tags

    git rev-parse -q --verify "refs/tags/$tag" >/dev/null \
        || die "tag $tag does not exist on origin — run" \
            "'cut-release.sh tag $version' first"

    local main_version
    main_version=$(git show origin/main:backend/pyproject.toml \
        | grep -m1 '^version' \
        | sed -E 's/version *= *"([^"]+)".*/\1/')
    [[ "$main_version" == "$version" ]] || die \
        "origin/main is at '$main_version', not '$version' — merge the" \
        "release PR first"

    git switch dev
    git pull --ff-only origin dev

    if ! git merge --no-ff origin/main \
        -m "Merge main ($tag) back into dev"; then
        git merge --abort
        die "merging origin/main into dev conflicted — resolve by" \
            "hand: git merge --no-ff origin/main, then for the" \
            "version-embedding files keep dev's side only if dev is" \
            "already past $version, otherwise take main's; commit" \
            "and git push origin dev"
    fi

    # dev's branch protection requires linear history; pushing this
    # merge commit relies on the operator's admin bypass.
    git push origin dev

    echo "merged $tag from main back into dev and pushed."
}

main() {
    local sub="${1:-}"
    case "$sub" in
        prepare)
            [[ $# -eq 2 ]] || die "usage: cut-release.sh prepare <version>"
            cmd_prepare "$2"
            ;;
        tag)
            [[ $# -eq 2 ]] || die "usage: cut-release.sh tag <version>"
            cmd_tag "$2"
            ;;
        reconcile)
            [[ $# -eq 2 ]] \
                || die "usage: cut-release.sh reconcile <version>"
            cmd_reconcile "$2"
            ;;
        *)
            die "usage: cut-release.sh {prepare|tag|reconcile} <version>"
            ;;
    esac
}

main "$@"
