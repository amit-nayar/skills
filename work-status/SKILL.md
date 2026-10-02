---
name: work-status
description: Post a short status of all my current Nutrient work to my Slack DM — open PRs (what needs action), unfinished local branches, in-flight Linear issues and Linear projects that need an update. Runs Mondays 8:30 via launchd; run /work-status any time for a fresh snapshot.
user-invocable: true
allowed-tools: Bash, Read
---

# Work status

A concise "where is everything" snapshot, posted to my personal Slack DM. Read-only: never touch
GitHub, Linear or any branch. Skimmable in 30 seconds; every line says what, where, and the action.

**Do not end the turn until the Slack post has gone out.** No background agents (a routine run that
ends with one still running is killed after 600s and reports success with nothing posted). Everything
is inline with the helper scripts.

## Steps

1. Gather (takes ~10s):

   ```bash
   set -a && . ~/.zprofile >/dev/null 2>&1; set +a
   python3 ~/dev/me/skills/work-status/scripts/gather.py > "$SCRATCH/status.json"
   ```

   `SCRATCH` is the session scratchpad. The JSON has `prs` (open PRs with review/CI/merge state and
   the clone(s) holding the branch), `clones` (clones with uncommitted files), `branches_without_pr`
   (my unfinished local branches with no open PR), and `linear` (assigned issues, projects I lead).

2. Write the outline (format below) and post it, as in step 3.

## What goes in the post

Header `Work status:`, then only the sections that have something. One line per item, a link, and
where it lives as `clone · branch`. Add `(dirty)` when that clone has uncommitted files. Group PRs
that share a story or need the same thing into one line (a stack of eval PRs is one line, not nine).

**Needs action** — PRs where the next move is mine:
- approved and not yet queued: "queue it"
- merge conflicts: "rebase"
- failing CI: name the failing check(s)
- review feedback waiting on me, or a draft with a green CI that looks ready: "mark ready"

**Waiting on others** — ready PRs with no human review yet (`human_reviewers` empty) or
changes-requested pending, with days idle.

**Drafts in progress** — drafts not otherwise listed, with days idle.

**Stale** — anything (PR, branch, issue) idle more than 30 days: "close or revive?". Collapse
into a single line when several.

**Local branches without a PR** — from `branches_without_pr`, with `clone · branch`, idle days, and
whether it is unpushed. Also mention clones with uncommitted files that aren't explained by a PR above.

**Linear** — in-flight issues (type `started`) with no PR link, or whose PR is merged/closed, so the
status is probably wrong; `unstarted` issues untouched for a long time can be one summary line. Skip
issues already covered by a PR line above (cross-reference by PR url) except to flag a state
mismatch (e.g. PR merged but issue still In Review).
**Projects needing an update** — projects I lead with `days_since_update` over 14 or null, one line
each with the project link.

Judgement calls: leave out PRs that need nothing and are fresh unless they matter; don't repeat the
PR title when the number plus a few words say it; no emoji, no padding. If everything is quiet,
say so in one line.

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
curl -s https://slack.com/api/chat.postMessage --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" --header "Content-Type: application/json; charset=utf-8" --data @"$SCRATCH/status-msg.json"
```

Outline rules are the same as `oft`: `## Name` sections, `- ` bullets, inline `[label](url)`,
PR link label is the number only. Check `"ok": true`, and include the `--preview` text in the reply so
a routine log shows what was posted.
