#!/usr/bin/env bash
# Find local clones/worktrees of a PR's repo and where its head branch lives.
# Usage: find-pr-checkout.sh <owner/repo> <branch> [search roots...]
# Output: one TSV line per candidate, best first:
#   <rank>\t<worktree path>\t<state>\t<current branch>\t<dirty|clean>
# rank/state:
#   1 checked-out  — branch is checked out in this worktree
#   2 local        — branch exists locally but is not checked out anywhere
#   3 clone        — repo clone without the branch (fallback: check out from origin)
set -uo pipefail

repo="${1:?owner/repo required}"
branch="${2:?branch required}"
shift 2
roots=("$@")
[ ${#roots[@]} -eq 0 ] && roots=("$HOME/dev/nutrient" "$HOME/dev/me" "$HOME/dev/others")

repo_lc=$(printf '%s' "$repo" | tr '[:upper:]' '[:lower:]')

matches_repo() {
  local url path
  url=$(git -C "$1" remote get-url origin 2>/dev/null | tr '[:upper:]' '[:lower:]') || return 1
  case "$url" in
    https://github.com/*|http://github.com/*|https://*@github.com/*|http://*@github.com/*|ssh://github.com/*|ssh://*@github.com/*)
      path=${url#*github.com/} ;;
    git@github.com:*|*@github.com:*)
      path=${url#*:} ;;
    *) return 1 ;;
  esac
  path=${path%/}
  path=${path%.git}
  [[ "$path" == "$repo_lc" ]]
}

dirty() {
  [ -n "$(git -C "$1" status --porcelain --untracked-files=normal 2>/dev/null | head -1)" ] && echo dirty || echo clean
}

seen=$'\n'
for root in "${roots[@]}"; do
  [ -d "$root" ] || continue
  for dir in "$root"/*/; do
    dir=${dir%/}
    [ -e "$dir/.git" ] || continue
    common=$(git -C "$dir" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || continue
    case "$seen" in *$'\n'"$common"$'\n'*) continue ;; esac
    seen+="$common"$'\n'
    matches_repo "$dir" || continue

    found_checkout=0
    # Walk all worktrees of this clone (includes the main one).
    while IFS= read -r line; do
      case "$line" in
        "worktree "*) wt=${line#worktree } ;;
        "branch refs/heads/$branch")
          printf '1\t%s\tchecked-out\t%s\t%s\n' "$wt" "$branch" "$(dirty "$wt")"
          found_checkout=1 ;;
      esac
    done < <(git -C "$dir" worktree list --porcelain)

    [ $found_checkout -eq 1 ] && continue
    cur=$(git -C "$dir" symbolic-ref --quiet --short HEAD 2>/dev/null || echo "(detached)")
    if git -C "$dir" show-ref --verify --quiet "refs/heads/$branch"; then
      printf '2\t%s\tlocal\t%s\t%s\n' "$dir" "$cur" "$(dirty "$dir")"
    else
      printf '3\t%s\tclone\t%s\t%s\n' "$dir" "$cur" "$(dirty "$dir")"
    fi
  done
done | sort -t$'\t' -k1,1n -k5,5
