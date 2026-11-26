---
name: pr-status
description: List all my open and draft PRs with their state and next step, one line each with a link. Use when I ask for a PR list, PR rundown, "refresh pr list" or where my PRs stand.
---

# PR status

Run the gatherer, then write the rundown from its output. Read-only; don't change any PR.

```bash
~/dev/me/skills/pr-status/scripts/prs.sh
```

Columns (TSV): repo, number, url, `DRAFT`/`OPEN`, review decision, merge state, failed checks,
pending check count, updated, queued (`1` = in the Mergify queue), title.

PRs that were in an earlier list in the conversation but are missing now: check them with
`gh pr view N -R repo --json state,mergedAt` and report them as merged or closed.

## Output

Answer first with one line of counts: open, how many draft, what merged since the last list, and
whether any check failed. Then sections, only the ones that have PRs, each PR one line
`[#N](url) short title: state, next step`:

1. **Done since last time** (merged or closed) — only if there was an earlier list
2. **Queued** (`queued=1`): wait, with pending checks
3. **Approved** but not queued: queue it once checks are green
4. **Failing**: the failed check names
5. **Waiting on review**: no human review yet, behind its base, conflicts (`DIRTY`), High risk
6. **Drafts**: active ones, with what's left before marking ready
7. **Stale drafts**: untouched for over a month; say rebase, close or decide

Nutrient code-review repo PRs link as `[nutrient-code-review #N](url)`. Mention anything on
HOLD. Don't guess at next steps for PRs whose comments you haven't read: say "needs review" or
"not re-read". "Pending" checks haven't failed yet, so say only that no check has failed
*so far*.
