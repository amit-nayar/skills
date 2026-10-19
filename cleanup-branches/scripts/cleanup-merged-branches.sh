#!/bin/bash
# Clean up local branches whose PR has merged, across every git repo under ~/dev/nutrient.
#
# Three passes per repo:
#   1. `gh poi` (hash-based match: PR found by searching for the branch tip's commit).
#   2. Name-based fallback: for branches gh-poi found NO PR for at all, look up
#      `gh pr list --head <branch> --state merged` by branch name instead of commit hash.
#      This catches the case where the PR was actually finished/merged from a
#      *different* local clone (extra commits/rebase there), so this clone's branch
#      tip SHA never appears in the merged PR — gh-poi's hash search misses it, but
#      the branch name still matches the merged PR's head ref.
#   3. Orphan agent-worktree reaping: `worktree-agent-*` branches left behind by Claude
#      Code's worktree isolation. The worktree directory is auto-removed when unchanged
#      but the branch ref survives, and since these have no upstream and no PR, passes 1
#      and 2 can never match them — they would accumulate forever. Only reaped when the
#      branch provably holds no work (no upstream AND an ancestor of the default branch).
#   4. Stale foreign branches: local branches nobody-here has touched — no commit on them
#      is authored or committed by us — that are older than CLEANUP_FOREIGN_MIN_AGE_DAYS.
#      These are colleagues' branches picked up by a `fetch`-and-checkout that then sat
#      around. Only reaped when fully recoverable from origin (see safety below), and
#      never when the branch NAME is ours or is release-shaped, because a branch we own
#      can legitimately carry only someone else's commits (a colleague pushing a fix to
#      our PR) and a `*-stable` branch is mostly other people's commits by nature.
#
# Safety, all passes:
#   - never touches the currently checked-out branch in a repo
#   - never touches a branch checked out in another worktree of that repo
#   - respects `gh poi lock <branch>` (stored as git config branch.<name>.gh-poi-protected)
#   - never touches master/main
#   - passes 3 and 4 additionally never delete anything that is not recoverable: the
#     branch must either be an ancestor of the default branch (holds no work at all) or
#     have an upstream it is not ahead of (every commit is already on origin)
#
# Usage: cleanup-merged-branches.sh [--live]
#   (no args)  dry-run: prints what WOULD be deleted, deletes nothing
#   --live     actually deletes the matched branches
#
# Env: CLEANUP_BASE_DIR overrides the directory swept (default ~/dev/nutrient).
#      Exists so the passes can be exercised against a throwaway fixture.
#      CLEANUP_FOREIGN_MIN_AGE_DAYS  age gate for pass 4 (default 7).
#      CLEANUP_OWNED_PREFIXES        space-separated branch-name prefixes that mark a
#                                    branch as ours regardless of who authored its
#                                    commits (default "amit", i.e. any branch whose
#                                    name starts with amit).
#      CLEANUP_MY_IDENTS             author/committer names or emails counting as us, on
#                                    top of git config user.email/user.name (default
#                                    "amit@nutrient.io amit.nyr@gmail.com" — both
#                                    addresses are ours, git config knows only one).
#      CLEANUP_PROTECTED_GLOBS       space-separated globs never deleted by pass 4
#                                    (default "*-stable *-release release/* releases/*
#                                    develop dev staging production").
#
# Output: one line per action, machine-parseable:
#   HASH_MATCH|<repo>|<branch>
#   NAME_FALLBACK|<repo>|<branch>|<pr_url>
#   WORKTREE_ORPHAN|<repo>|<branch>
#   FOREIGN_STALE|<repo>|<branch>|<last_author>|<age_days>
#   SKIPPED_LOCKED|<repo>|<branch>
#   SKIPPED_ORPHAN_UNMERGED|<repo>|<branch>|<ahead_count>
#   SKIPPED_FOREIGN_UNPUSHED|<repo>|<branch>|<ahead_count>

set -o pipefail

LIVE=false
if [[ "${1:-}" == "--live" ]]; then
  LIVE=true
fi

BASE_DIR="${CLEANUP_BASE_DIR:-$HOME/dev/nutrient}"
FOREIGN_MIN_AGE_DAYS="${CLEANUP_FOREIGN_MIN_AGE_DAYS:-7}"
read -r -a OWNED_PREFIXES <<< "${CLEANUP_OWNED_PREFIXES:-amit}"
read -r -a PROTECTED_GLOBS <<< "${CLEANUP_PROTECTED_GLOBS:-*-stable *-release release/* releases/* develop dev staging production}"
read -r -a EXTRA_IDENTS <<< "${CLEANUP_MY_IDENTS:-amit@nutrient.io amit.nyr@gmail.com}"
NOW_EPOCH="$(date +%s)"

for repo_path in "$BASE_DIR"/*/; do
  repo_path="${repo_path%/}"
  [[ -e "$repo_path/.git" ]] || continue
  repo_name="$(basename "$repo_path")"

  cd "$repo_path" || continue
  git remote get-url origin >/dev/null 2>&1 || continue

  git fetch --all --prune --quiet 2>/dev/null

  # Drop metadata for worktrees whose directory is already gone, so the list below
  # reflects live checkouts only (a vanished worktree must not protect its branch).
  git worktree prune 2>/dev/null

  current_branch="$(git branch --show-current 2>/dev/null)"
  worktree_branches="$(git worktree list --porcelain 2>/dev/null | awk '/^branch /{sub("refs/heads/","",$2); print $2}')"

  # Default branch, preferring the remote tip (accurate right after the fetch above).
  default_ref=""
  default_branch="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"
  default_branch="${default_branch#origin/}"
  for candidate in "$default_branch" master main; do
    [[ -z "$candidate" ]] && continue
    if git show-ref --verify --quiet "refs/remotes/origin/$candidate"; then
      default_ref="origin/$candidate"
      break
    elif git show-ref --verify --quiet "refs/heads/$candidate"; then
      default_ref="$candidate"
      break
    fi
  done

  poi_output="$(gh poi --state merged --scan deep --dry-run 2>/dev/null)"

  # --- Pass 1: parse gh-poi's hash-based matches ---
  hash_matched=()
  while IFS= read -r line; do
    hash_matched+=("$line")
    echo "HASH_MATCH|$repo_name|$line"
  done < <(echo "$poi_output" | awk '
    /^Deleted branches/{grab=1; next}
    /^Branches not deleted/{grab=0}
    grab && /^  [^ └├]/{gsub(/^  /,""); if ($0 != "There are no branches in the current directory") print}
  ')

  # Branches gh-poi listed under "not deleted" WITHOUT any PR annotation at all —
  # these are the ones hash-matching found nothing for, and our fallback should check.
  no_pr_candidates=()
  while IFS= read -r line; do
    no_pr_candidates+=("$line")
  done < <(echo "$poi_output" | awk '
    /^Branches not deleted/{grab=1; next}
    !grab{next}
    /^  [^ ]/{
      if (branch != "" && !has_pr) print branch
      branch=$0; sub(/^  \* /,"",branch); sub(/^  /,"",branch); has_pr=0
    }
    /^    [└├]/{has_pr=1}
    END{ if (branch != "" && !has_pr) print branch }
  ')

  if $LIVE; then
    gh poi --state merged --scan deep >/dev/null 2>&1
  fi

  # --- Pass 2: name-based fallback for the no-PR-found branches ---
  for branch in "${no_pr_candidates[@]}"; do
    [[ -z "$branch" ]] && continue
    [[ "$branch" == "$current_branch" ]] && continue
    [[ "$branch" == "master" || "$branch" == "main" ]] && continue
    printf '%s\n' "$worktree_branches" | grep -qxF "$branch" && continue

    if [[ "$(git config --bool "branch.$branch.gh-poi-protected" 2>/dev/null)" == "true" ]]; then
      echo "SKIPPED_LOCKED|$repo_name|$branch"
      continue
    fi

    pr_json="$(gh pr list --head "$branch" --state merged --json url,mergedAt --limit 1 2>/dev/null)"
    [[ -z "$pr_json" || "$pr_json" == "[]" ]] && continue

    pr_url="$(echo "$pr_json" | jq -r '.[0].url')"
    echo "NAME_FALLBACK|$repo_name|$branch|$pr_url"

    if $LIVE; then
      git branch -D "$branch" >/dev/null 2>&1
    fi
  done

  # --- Pass 3: reap orphan `worktree-agent-*` branches with no work in them ---
  # Left behind by Claude Code worktree isolation: the worktree is cleaned up, the
  # branch ref is not. No upstream and no PR, so passes 1 and 2 never see them.
  # No default branch to compare against means nothing here is provably empty; this is
  # the last pass, so skipping straight to the next repo is safe.
  [[ -n "$default_ref" ]] || continue

  while IFS= read -r branch; do
    [[ -z "$branch" ]] && continue
    [[ "$branch" == "$current_branch" ]] && continue
    [[ "$branch" == "master" || "$branch" == "main" ]] && continue
    printf '%s\n' "$worktree_branches" | grep -qxF "$branch" && continue

    if [[ "$(git config --bool "branch.$branch.gh-poi-protected" 2>/dev/null)" == "true" ]]; then
      echo "SKIPPED_LOCKED|$repo_name|$branch"
      continue
    fi

    # A pushed branch is somebody's shared state, not a local leftover — leave it.
    git rev-parse --verify --quiet "$branch@{upstream}" >/dev/null 2>&1 && continue

    # Only reap when the tip is already contained in the default branch, i.e. the
    # worktree was abandoned without a single commit. Anything ahead is real work.
    if ! git merge-base --is-ancestor "$branch" "$default_ref" 2>/dev/null; then
      ahead="$(git rev-list --count "$default_ref..$branch" 2>/dev/null)"
      echo "SKIPPED_ORPHAN_UNMERGED|$repo_name|$branch|${ahead:-?}"
      continue
    fi

    echo "WORKTREE_ORPHAN|$repo_name|$branch"

    if $LIVE; then
      # -d is the safe form and suffices given the ancestor check; -D covers the
      # case where HEAD is a feature branch that -d measures against.
      git branch -d "$branch" >/dev/null 2>&1 || git branch -D "$branch" >/dev/null 2>&1
    fi
  done < <(git for-each-ref --format='%(refname:short)' 'refs/heads/worktree-agent-*')

  # --- Pass 4: stale branches nobody here has touched ---
  # Identities that count as "us". Authorship alone is not enough to claim a branch
  # (see OWNED_PREFIXES below), but it is enough to disqualify one from deletion.
  my_idents=()
  for ident in "$(git config user.email)" "$(git config user.name)" \
               "$(git config --global user.email)" "$(git config --global user.name)" \
               "${EXTRA_IDENTS[@]}"; do
    [[ -n "$ident" ]] && my_idents+=("$ident")
  done

  while IFS='|' read -r branch tip_epoch last_author; do
    [[ -z "$branch" ]] && continue
    [[ "$branch" == "$current_branch" ]] && continue
    [[ "$branch" == "master" || "$branch" == "main" ]] && continue
    printf '%s\n' "$worktree_branches" | grep -qxF "$branch" && continue

    # Pass 3 owns these, including its decision to leave pushed ones alone. Without
    # this, an agent branch gets reported twice and a pushed one gets reaped here on
    # authorship grounds after pass 3 deliberately spared it.
    [[ "$branch" == worktree-agent-* ]] && continue

    if [[ "$(git config --bool "branch.$branch.gh-poi-protected" 2>/dev/null)" == "true" ]]; then
      echo "SKIPPED_LOCKED|$repo_name|$branch"
      continue
    fi

    # Release-shaped branches are mostly other people's commits by nature — never ours
    # to reap on authorship grounds.
    protected=false
    for glob in "${PROTECTED_GLOBS[@]}"; do
      # shellcheck disable=SC2053
      [[ "$branch" == $glob ]] && { protected=true; break; }
    done
    $protected && continue

    # A branch under one of our own name prefixes is ours even when every commit on it
    # was authored by someone else (a colleague pushing onto our PR branch).
    owned=false
    for prefix in "${OWNED_PREFIXES[@]}"; do
      [[ "$branch" == "$prefix"* ]] && { owned=true; break; }
    done
    $owned && continue

    # Age gate: measured from the branch tip's commit date.
    age_days=$(( (NOW_EPOCH - tip_epoch) / 86400 ))
    (( age_days < FOREIGN_MIN_AGE_DAYS )) && continue

    # Any commit we authored OR committed makes this ours — don't touch it.
    mine=false
    while IFS= read -r ident; do
      [[ -z "$ident" ]] && continue
      for me in "${my_idents[@]}"; do
        if [[ "$ident" == "$me" ]]; then
          mine=true
          break 2
        fi
      done
    done < <(git log --format='%ae%n%ce%n%an%n%cn' "$default_ref..$branch" 2>/dev/null)
    $mine && continue

    # Recoverable-or-skip: either the branch holds no work at all, or every commit on
    # it is already pushed to its upstream. Anything else would be a real deletion.
    if ! git merge-base --is-ancestor "$branch" "$default_ref" 2>/dev/null; then
      upstream="$(git rev-parse --abbrev-ref --symbolic-full-name "$branch@{upstream}" 2>/dev/null)"
      if [[ -z "$upstream" ]]; then
        echo "SKIPPED_FOREIGN_UNPUSHED|$repo_name|$branch|no-upstream"
        continue
      fi
      unpushed="$(git rev-list --count "$upstream..$branch" 2>/dev/null)"
      if [[ "${unpushed:-1}" != "0" ]]; then
        echo "SKIPPED_FOREIGN_UNPUSHED|$repo_name|$branch|$unpushed"
        continue
      fi
    fi

    echo "FOREIGN_STALE|$repo_name|$branch|$last_author|$age_days"

    if $LIVE; then
      git branch -d "$branch" >/dev/null 2>&1 || git branch -D "$branch" >/dev/null 2>&1
    fi
  done < <(git for-each-ref --format='%(refname:short)|%(committerdate:unix)|%(authorname)' refs/heads/)
done
