---
name: cleanup-branches
description: Clean up local git branches whose PR has merged, across every repo clone under ~/dev/nutrient. Runs gh-poi plus a name-based fallback for branches finished on a different clone, then posts a summary to Slack.
user-invocable: true
allowed-tools: Bash
---

# Cleanup Merged/Stale Branches

Delete local branches across every git repo under `~/dev/nutrient` (all monorepo and
website clones, plus every other repo there) once their PR has merged — the daily
manual `gh poi` sweep, automated.

## Why this exists (context, not steps)

`gh poi` matches a local branch to a PR by searching GitHub for the branch tip's
**commit hash**. If the PR was actually finished and merged from a *different* local
clone — extra commits, a rebase, an amend happened there instead — this clone's branch
tip SHA never appears in the merged PR's commit list. `gh poi`'s hash search then finds
nothing, and the branch is silently never cleaned up here even though the PR is long
merged. The fallback pass below closes that gap by matching on **branch name** instead,
which is clone-independent.

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
- `git fetch --all --prune`
- `gh poi --state merged --scan deep` (hash-based match; only actually deletes when
  `--live` is passed — otherwise it's the `--dry-run` variant)
- A name-based fallback pass over whatever branches `gh poi` found **no PR at all** for:
  `gh pr list --head <branch> --state merged` looked up by branch name. Only branches
  with zero PR annotation from gh-poi are checked this way — branches gh-poi already
  associated with an (open) PR are left alone.
- Skips the currently checked-out branch, any branch checked out in another worktree of
  that repo, `master`/`main`, and anything locked via `gh poi lock` (git config
  `branch.<name>.gh-poi-protected`).

It prints one machine-readable line per action:
```
HASH_MATCH|<repo>|<branch>
NAME_FALLBACK|<repo>|<branch>|<pr_url>
SKIPPED_LOCKED|<repo>|<branch>
```

### 2. Build the Slack summary

Group by repo. For each repo with any `HASH_MATCH` or `NAME_FALLBACK` lines, list the
branches removed (or, in dry-run mode, that *would* be removed) as a bullet list;
mark `NAME_FALLBACK` entries with a short note since those are the cross-clone catch —
e.g. "`amit/andr-1900-foo` — merged via #55642 (finished on another clone)". Skip repos
with nothing to report. If `SKIPPED_LOCKED` lines exist, add one trailing note per repo
naming the locked branches — never delete those, just surface that they were seen and
left alone.

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
