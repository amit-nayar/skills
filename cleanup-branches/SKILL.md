---
name: cleanup-branches
description: Clean up local git branches across every repo clone under ~/dev/nutrient — merged PRs (gh-poi plus a name-based fallback for branches finished on a different clone), orphan agent-worktree branches, and stale branches nobody here has touched. Posts a summary to Slack.
user-invocable: true
allowed-tools: Bash
---

# Cleanup Merged/Stale Branches

Delete local branches across every git repo under `~/dev/nutrient` (all monorepo and
website clones, plus every other repo there) once they are finished with — the daily
manual `gh poi` sweep, automated, plus the classes of dead branch `gh poi` cannot see:
merged-elsewhere, abandoned agent worktrees, and colleagues' branches gone stale.

## Why this exists (context, not steps)

`gh poi` matches a local branch to a PR by searching GitHub for the branch tip's
**commit hash**. If the PR was actually finished and merged from a *different* local
clone — extra commits, a rebase, an amend happened there instead — this clone's branch
tip SHA never appears in the merged PR's commit list. `gh poi`'s hash search then finds
nothing, and the branch is silently never cleaned up here even though the PR is long
merged. The name-fallback pass closes that gap by matching on **branch name** instead,
which is clone-independent.

Two further classes of branch have no PR at all, so neither of those passes can ever
reach them, and they accumulate indefinitely:

- **Orphan agent-worktree branches.** Claude Code's worktree isolation creates a
  `worktree-agent-<hash>` branch off HEAD. When the agent changes nothing the worktree
  directory is auto-removed, but the branch ref survives with no upstream and no PR.
  Two of these sat in `~/dev/nutrient/monorepo` for over a month before anyone noticed.
- **Stale foreign branches.** A colleague's branch checked out locally to review or
  test, then left behind. Nothing here ever touched it and it is fully on origin, so
  the local ref is pure clutter.

## Arguments

`$ARGUMENTS` may contain `--live`. Pass it straight through to the script (see Step 1).
With no arguments, the run is a dry-run (report only, nothing is deleted) — this is the
default while the branch-name fallback is still being trusted/observed.

## Steps

### 1. Run the cleanup script

```bash
~/dev/bin/cleanup-merged-branches.sh $ARGUMENTS
```

This sweeps every repo under `~/dev/nutrient` (~24 as of writing) and typically takes
5-7 minutes. Give the Bash call a generous timeout (e.g. 600000ms) rather than the
default 2 minutes.

This script does the actual work, per repo under `~/dev/nutrient`:
- `git fetch --all --prune`, then `git worktree prune` (so a worktree whose directory is
  already gone stops protecting its branch)
- **Pass 1** — `gh poi --state merged --scan deep` (hash-based match; only actually
  deletes when `--live` is passed — otherwise it's the `--dry-run` variant)
- **Pass 2** — a name-based fallback over whatever branches `gh poi` found **no PR at
  all** for: `gh pr list --head <branch> --state merged` looked up by branch name. Only
  branches with zero PR annotation from gh-poi are checked this way — branches gh-poi
  already associated with an (open) PR are left alone.
- **Pass 3** — orphan `worktree-agent-*` branches, reaped only when they provably hold
  no work: no upstream **and** an ancestor of the default branch. One that is ahead is
  reported as `SKIPPED_ORPHAN_UNMERGED` and left alone; one that has been pushed is
  shared state and skipped silently.
- **Pass 4** — stale branches nobody here has touched: no commit between the default
  branch and the tip is authored *or* committed by us, and the tip is older than
  `CLEANUP_FOREIGN_MIN_AGE_DAYS` (default 7).
- Skips, in every pass: the currently checked-out branch, any branch checked out in a
  live worktree of that repo, `master`/`main`, and anything locked via `gh poi lock`
  (git config `branch.<name>.gh-poi-protected`).

It prints one machine-readable line per action:
```
HASH_MATCH|<repo>|<branch>
NAME_FALLBACK|<repo>|<branch>|<pr_url>
WORKTREE_ORPHAN|<repo>|<branch>
FOREIGN_STALE|<repo>|<branch>|<last_author>|<age_days>
SKIPPED_LOCKED|<repo>|<branch>
SKIPPED_ORPHAN_UNMERGED|<repo>|<branch>|<ahead_count>
SKIPPED_FOREIGN_UNPUSHED|<repo>|<branch>|<ahead_count|no-upstream>
```

#### What keeps pass 4 from eating real work

Authorship alone is a bad ownership test, so three guards sit in front of it. Each one
exists because a real branch in `~/dev/nutrient` would otherwise have been deleted:

1. **Recoverable-or-skip.** A branch is only deleted if it is an ancestor of the default
   branch (holds nothing) or has an upstream it is **not ahead of** (every commit is
   already on origin). Anything else prints `SKIPPED_FOREIGN_UNPUSHED`. This is the rule
   that makes the pass safe: a deleted branch is always re-creatable from origin.
2. **Owned name prefixes** (`CLEANUP_OWNED_PREFIXES`, default `amit` — *any* branch
   whose name starts with `amit`, covering `amit/…`, `amit-nayar/…` and anything else).
   Such a branch is ours even when every commit on it was authored by someone else —
   `nutrient-website/amit-nayar/prose-mechanics-review-sample` has a tip commit by a
   colleague who pushed onto the PR, and pure authorship matching would have reaped it.
3. **Protected globs** (`CLEANUP_PROTECTED_GLOBS`, default `*-stable *-release
   release/* releases/* develop dev staging production`). Release branches are mostly
   other people's commits by nature. `android-11.6-stable` is checked out in all three
   monorepo clones and would have qualified as "foreign" as soon as its tip aged past a
   week.

Identity comes from `git config user.email`/`user.name` (repo **and** global) plus
`CLEANUP_MY_IDENTS`, which defaults to **both** of our addresses:
`amit@nutrient.io amit.nyr@gmail.com`. Both are ours, and git config only ever knows one
of them (it is set to the gmail address), so neither can be dropped.

`CLEANUP_BASE_DIR` overrides the swept directory; it exists so these passes can be
exercised against a throwaway fixture instead of live repos.

### 2. Build the Slack summary

Group by repo. For each repo with any `HASH_MATCH`, `NAME_FALLBACK`, `WORKTREE_ORPHAN`
or `FOREIGN_STALE` line, list the branches removed (or, in dry-run mode, that *would* be
removed) as a bullet list. Annotate the non-obvious kinds, since a wrong match needs to
be easy to spot:
- `NAME_FALLBACK` — the cross-clone catch, e.g. "`amit/andr-1900-foo` — merged via
  #55642 (finished on another clone)".
- `WORKTREE_ORPHAN` — e.g. "`worktree-agent-a1b2c72` — abandoned agent worktree, no
  commits".
- `FOREIGN_STALE` — always name the author and age, e.g. "`obalolu/vertical-scroll-inset`
  — Abdullahi Gbadamosi, 44 days old, fully pushed". This is the pass most likely to
  surprise, so it must never appear as a bare branch name.

Skip repos with nothing to report. If `SKIPPED_LOCKED` lines exist, add one trailing
note per repo naming the locked branches — never delete those, just surface that they
were seen and left alone. `SKIPPED_ORPHAN_UNMERGED` and `SKIPPED_FOREIGN_UNPUSHED` mean
a branch held work that is not on origin: mention those too, briefly, because they are a
standing invitation to look before they get lost.

If the run was a dry-run (no `--live` in `$ARGUMENTS`), title the message
"Branch cleanup (dry run):" so it's clear nothing was actually deleted. If `--live` was
passed, title it "Branch cleanup:".

If there is nothing to report at all (no matches anywhere), don't post — same as `oft`.

Use plain Block Kit `rich_text` with a `rich_text_list` (`indent: 0`) per repo, preceded
by a bold repo-name section when more than one repo has results (same grouping
convention as the `oft` skill — flat single list when only one repo has activity).

### 3. Post to Slack

- Token: `SLACK_API_TOKEN_OFT` from `~/.zprofile` — same token the `oft` skill uses.
- Resolve the target with `auth.test` and post to `.user_id` (self-DM), same as `oft`.
- Write the JSON to a temp file, `curl --data @<tmpfile>` to `chat.postMessage`, use
  `--header` (not `-H`) for the auth header.
- Confirm to the user that it posted (or that there was nothing to report).

## Common Pitfalls

1. **Don't invoke `gh poi` or `git branch -D` directly from this skill** — always go
   through `cleanup-merged-branches.sh` so the worktree/lock/current-branch safety
   checks and the name-fallback pass stay in one place.
2. **Don't treat a `NAME_FALLBACK` match as equivalent in confidence to `HASH_MATCH`** —
   call it out distinctly in the Slack message so a wrong match is easy to spot and
   report back.
3. **Don't run this with `--live` casually from an interactive session** without the
   user asking — it deletes local branches across every repo clone under
   `~/dev/nutrient`. Fine for the scheduled unattended run; ask first otherwise.
4. **Never widen pass 4 by relaxing the recoverable-or-skip rule.** Deleting a local
   branch is only harmless because every commit on it is already on origin. A variant
   that reaps unpushed foreign branches destroys work with no undo.
5. **`gh` is not on the Bash tool's default PATH** (`/opt/homebrew/bin` is missing), and
   every `gh` call in the script is wrapped in `2>/dev/null`. A run with a broken PATH
   therefore reports *zero* results and looks like a clean sweep. Source `~/.zprofile`
   or prepend `/opt/homebrew/bin` to PATH before invoking the script, and treat a
   completely empty result across all ~24 repos as suspicious rather than as good news.
6. **Wait for the sweep to finish before ending the session.** The script takes 5-7
   minutes; a scheduled run that backgrounds it and exits early records `success`
   without ever posting to Slack (this happened on 2026-08-21). Run it in the foreground
   with a generous timeout.
