---
name: work-status
description: Post a short status of all my current Nutrient work to my Slack DM — open PRs (what needs action), PRs waiting on my review, unfinished local branches, in-flight Linear issues and Linear projects that need an update. Fixes Linear PR links and states and re-queues PRs dequeued on infra failures itself. Runs Mondays and Thursdays 8:00 via launchd with `cleanup`, which also runs the branch cleanup and posts its results as a thread reply; run /work-status any time for a fresh snapshot.
user-invocable: true
argument-hint: "[all] [cleanup]"
allowed-tools: Bash, Read
---

# Work status

A concise "where is everything" snapshot, posted to my personal Slack DM. Skimmable in 30 seconds;
every line says what and the action.

It changes things only through `act.py`, and only these: links a PR to a Linear issue, moves a
Linear issue to Done when its own PRs merged, and re-queues an approved PR Mergify dequeued when
that merge-queue build's failures don't look real. Everything else is report-only: never queue a PR
that wasn't queued before, never re-run CI, never touch a branch (the `cleanup` run's branch deletions go through the
cleanup-branches scripts only).

**Do not end the turn until the Slack post has gone out.** No background agents (a routine run that
ends with one still running is killed after 600s and reports success with nothing posted). Everything
is inline with the helper scripts.

## Steps

0. Only when invoked with `cleanup` (the scheduled run): run the branch cleanup first, so the
   status below doesn't list branches it is about to delete. Follow Step 1 and 1b of
   `~/dev/me/skills/cleanup-branches/SKILL.md` with `--live`, in the foreground with a 600000ms
   timeout (the sweep takes 5-7 minutes), and keep the output:

   ```bash
   set -a && . ~/.zprofile >/dev/null 2>&1; set +a
   { ~/dev/me/skills/cleanup-branches/scripts/cleanup-merged-branches.sh --live
     ~/dev/me/skills/cleanup-branches/scripts/cleanup-agent-emulators.sh --live; } > "$SCRATCH/cleanup.txt" 2>&1
   ```

   If it fails, carry on with the status and say so in the cleanup thread reply (see Post).

1. Gather (takes ~10s). PRs are limited to the Nutrient GitHub orgs (`PSPDFKit`, `PSPDFKit-labs`);
   when invoked as `/work-status all`, add `--all` to include personal and other repos too.

   ```bash
   set -a && . ~/.zprofile >/dev/null 2>&1; set +a
   python3 ~/dev/me/skills/work-status/scripts/gather.py > "$SCRATCH/status.json"  # add --all for `all`
   ```

   `SCRATCH` is the session scratchpad. The JSON has:
   - `complete` / `errors` — if `complete` is false, some source failed (gh auth, rate limit,
     Linear). Start the post with `Snapshot incomplete: <errors, briefly>` and never say
     "everything is quiet" — missing data is not an empty queue.
   - `prs` — open PRs with review/CI/merge state (release PRs from `release/…` into a `*-stable`
     branch are left out: they merge without review as part of the release) and the clone(s) holding the branch (matched on
     repo + branch). Checks are deduplicated to the newest run: `failed_checks` are real failures,
     `cancelled_checks` didn't finish (not a failure). `merge_queue` is the Mergify queue check's
     title for approved PRs. `unsigned_commits` lists short SHAs GitHub doesn't show as verified
     (`null` = lookup failed, unknown). Skip classifying a PR with `detail_missing: true`; list it as
     "couldn't load". `ci_failures` has one entry per failed Buildkite job: `kind` is `real` (failing
     tests, compile errors, lint, formatting), `infra` (rate limits, network, lost agents, emulator
     boot or APK install) or `unknown`, with the job `url` and the log line that decided it.
     `dequeued` is set when Mergify dequeued an approved PR and it hasn't been queued since:
     `failures` are that merge-queue build's jobs, classified the same way.
     Website PRs (`PSPDFKit/nutrient-website`, not release branches) also have `copy`: "approved"
     (Natalye, `deutschbitte`, approved), "requested" (`needs copy review` label), "skipped" (`skip
     copy review` label) or "not requested"; and `release`: the open website release PR (`version`,
     `url`) the PR ships with, matched on platform and version in its branch or title, else null.
   - `review_requests` — open PRs by others waiting on my review. `direct` is true when I was
     asked by name, false when only a team I'm in was asked; `age_days` is since the PR opened.
   - `clones` — clones with uncommitted files.
   - `branches_without_pr` — my branches (named `amit/…`, or started by me under a type prefix like
     `fix/…`; branches named for someone else, like `akshay/…`, are theirs) ahead of the default
     branch with no open PR in that repo. Branches whose tip was merged are already dropped. `push_state` is `never` / `ahead` (local
     commits not pushed) / `gone` (remote deleted) / `pushed`; `ahead_of_default` is `null` when the
     comparison failed (see `errors`). `last_pr` is the most recent closed PR for the branch, if any.
   - `linear` — assigned issues (each linked PR with its `state`: OPEN / MERGED / CLOSED) and
     projects I lead. `null` if Linear failed (see `errors`).

2. Make the routine fixes:

   ```bash
   python3 ~/dev/me/skills/work-status/scripts/act.py "$SCRATCH/status.json" > "$SCRATCH/done.json"
   ```

   `done` lists what it changed, `errors` what it tried and couldn't. Items it fixed don't also go
   in the sections below (a linked issue isn't "no PR linked" any more; a re-queued PR isn't
   "dequeued").

3. Write the outline (format below) and post it (see Post). If `gather.py` itself crashes, post
   `Work status: snapshot failed — <error>` rather than nothing.

## What goes in the post

Header `Work status:`, then only the sections that have something. One line per item with a link.
Add where the branch lives (`clone · branch`, plus `(dirty)` when that clone has uncommitted files)
only when the action needs a checkout: rebase, re-sign, or a real CI failure to fix. Group PRs that
share a story or need the same thing into one line (a stack of eval PRs is one line, not nine).

**Done for you** — first, one line per `done.json` entry: "Linked [#123](…) to AND-…", "Moved
AND-… to Done ([#123](…) merged)", "Re-queued [#123](…), dequeued on infra failures ([summary](…))".
Add a line for each entry in its `errors`.

**Needs action** — PRs where the next move is mine:
- website PRs follow their own path instead of the queue rule below. Approved by the content
  reviewer, then copy review by Natalye, then merge:
  - approved and `copy` is "not requested": "add `needs copy review`" (or `skip copy review` when
    the change is one or two lines).
  - `copy` "approved" or "skipped" and approved: "queue it" — unless `release` is set; then it goes
    under Waiting on others as "ready, waits for the [12.1 release](release url) to publish".
  - `copy` "requested" without Natalye's approval: Waiting on others, "copy review (Natalye)".
  Group the website PRs of one release into one line per state.
- approved and `merge_queue` is "Merge queue is ready" (not queued yet): "queue it". Any other
  `merge_queue` title means it's already queued or merging; leave it out unless the title says it
  failed or was dequeued.
- merge conflicts: "rebase"
- unsigned commits (`unsigned_commits` non-empty): "re-sign <shas>". List every PR that has
  them, approved or not: the merge queue won't take them, and fixing them takes a force-push, so
  flag them early. Put these first.
- failing CI: one line per PR, split by `ci_failures` kind and linking each job: "real: [lint](job
  url), [unit tests](…)" — fix these; "infra: [lint](…) (Maven Central 429)" — say in a few words
  what the evidence shows, nothing for me to fix but a re-run; "unknown: [check](…)" — look. A PR
  whose failures are all infra goes in one collapsed line at the end of the section ("Infra-only
  failures, re-run when ready: [#…](…) [#…](…)"). Only cancelled checks: "re-run <check>".
- dequeued and `act.py` didn't re-queue it (a failure was real or unknown): "dequeued on
  [real failure](job url) — fix, then queue".
- changes requested (`review` is `CHANGES_REQUESTED`): "address feedback"
- a draft with green CI that looks ready: "mark ready"

**Review requests** — PRs others are waiting on me to review, direct requests first, one line
each: link, author, a few words of title, age. Team-only requests (`direct: false`) collapse into
one line ("plus N team requests: [#…](…) …"). Skip drafts unless I was asked directly.

**Waiting on others** — ready PRs with no human review yet (`human_reviewers` empty), or reviewed
but not yet approved, with days idle. Pending CI alone is not waiting on others.

**Drafts in progress** — drafts not otherwise listed. Drafts with activity in the last 7 days get
a line each; the rest collapse into one line of links: "Also idle: [#…](…) 13d, [#…](…) 20d".
Drafts idle over 30 days add "— close or revive?".

**Unfinished branches** — from `branches_without_pr`, oldest first, at most 5 lines plus "+N more".
Each line: `clone · branch`, idle days, and the push state in words ("never pushed", "unpushed
commits", "remote deleted"). When `last_pr` is a closed (unmerged) PR, link it: "PR [#123](…)
closed unmerged — drop or reopen?". When it is `MERGED`, check `last_pr.tip_covered`: `false` means
commits were added after that merge ("new commits since [#123](…) merged"); `null` means it couldn't
be verified ("[#123](…) merged, not sure whether the branch has newer commits"). Never claim new
work from `null`. Group branches of one effort into one line. Don't list dirty clones on their own.

**Linear** — in-flight issues (type `started`) with no PR link, or whose linked PRs are all
`MERGED`/`CLOSED`, so the status is probably wrong (use each PR's `state`; a `null` state is unknown,
not closed). Don't list `unstarted` issues for being untouched: Todo sitting is normal. Skip
issues already covered by a PR line above (cross-reference by PR url) except to flag a state
mismatch (e.g. PR merged but issue still In Review). Only PRs with `for_issue: true` say anything
about an issue's state: a merged PR that doesn't name the issue (a prerequisite from another issue)
is not a reason to move it. Never call an issue "no PR linked" without checking its `prs` list.
**Projects needing an update** — projects I lead with `days_since_update` over 14 or null, one line
each with the project link. `gather.py` already drops backlog, completed and canceled projects.

Judgement calls: leave out PRs that need nothing and are fresh unless they matter; don't repeat the
PR title when the number plus a few words say it; no emoji, no padding. If everything is quiet
(and `complete` is true), say so in one line.

## Post

Use the OFT builder for the Block Kit message, and post to my own DM:

```bash
cat > "$SCRATCH/outline.md" <<'OUTLINE'
Work status:

## Needs action
- Queue the approved PRs [#59297](https://github.com/PSPDFKit/PSPDFKit/pull/59297) [#59291](...) — `monorepo2 · amit/and-pending-migration-notes`
OUTLINE
USER_ID=$(curl -s https://slack.com/api/auth.test --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["user_id"])')
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" --preview
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" > "$SCRATCH/status-msg.json"
curl -s https://slack.com/api/chat.postMessage --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" --header "Content-Type: application/json; charset=utf-8" --data @"$SCRATCH/status-msg.json" | tee "$SCRATCH/status-resp.json"
```

Outline rules are the same as `oft`: `## Name` sections, `- ` bullets, inline `[label](url)`,
PR link label is the number only. Check `"ok": true`, and include the `--preview` text in the reply so
a routine log shows what was posted.

### Cleanup thread reply (only with `cleanup`)

After the status post succeeds, reply in its thread with the cleanup results. Build the outline
from `$SCRATCH/cleanup.txt` by the rules in Step 2 of `~/dev/me/skills/cleanup-branches/SKILL.md`
(group by repo as `## <repo>` sections, annotate `NAME_FALLBACK`, `WORKTREE_ORPHAN` and
`FOREIGN_STALE`, an Emulators section, then locked and skipped-unpushed notes), titled "Branch
cleanup:". If the sweep reported nothing, still reply with one line, "Branch cleanup: nothing to
remove"; if it failed or every repo came back empty, say that instead (an all-empty sweep usually
means a broken PATH, not a clean tree).

```bash
TS=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["ts"])' "$SCRATCH/status-resp.json")  # save the status post's response here
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/cleanup-outline.md" "$USER_ID" --preview
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/cleanup-outline.md" "$USER_ID" \
  | python3 -c 'import json,sys;m=json.load(sys.stdin);m["thread_ts"]=sys.argv[1];print(json.dumps(m))' "$TS" > "$SCRATCH/cleanup-msg.json"
curl -s https://slack.com/api/chat.postMessage --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" --header "Content-Type: application/json; charset=utf-8" --data @"$SCRATCH/cleanup-msg.json"
```

Check `"ok": true` here too.
