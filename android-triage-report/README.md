# android-triage-report — how it fits together

Posts the Android team's Linear **Triage** queue to **#android** every Monday as a short linked
bullet list, and attaches the per-issue research as a comment on each Linear issue — marked as an
unreviewed machine suggestion.

`SKILL.md` is the instructions Claude follows. This file is the wiring around it.

## The chain

```
launchd (Mon 08:55)
  → io.amit.claude-android-triage-report.plist
    → run-claude-routine.sh android-triage-report
      → claude -p /android-triage-report   (opus-5, 100 turns, cwd = ~/dev/nutrient/monorepo)
        → SKILL.md
          → Linear (read + ONE comment per issue) · monorepo (read) · Slack (post)
```

| Piece | Lives at | Tracked in |
| --- | --- | --- |
| Skill | `~/.claude/skills/android-triage-report/` → symlink to this dir | `amit-nayar/skills` |
| launchd plist | `~/Library/LaunchAgents/io.amit.claude-android-triage-report.plist` | `amit-nayar/environment`, `launchd/` |
| Runner | `~/Library/Application Support/claude-routines/run-claude-routine.sh` | same repo |
| Wake-up catch-up | `~/.wakeup` | same repo, as `launchd/wakeup.sh` |
| Logs | `~/Library/Logs/claude-routines/android-triage-report{,.err}.log` | — |

**The skill is a symlink, everything else is a copy.** Editing this directory changes the live
skill immediately. The plists, `~/.wakeup` and the runner each exist twice — once live, once in
`environment/launchd/` — so **edit both**, or the change either doesn't take effect or isn't
tracked.

## Why it runs weekly, and what happens when the Mac is asleep

This runs on a laptop, so a Monday 08:55 fire can land while the lid is shut. macOS gives a
DarkWake job ~180s, which is not enough — the run dies with `Connection closed mid-response`
and exits 1. That is a real failure mode, not theoretical: it happened on 17 Aug 2026.

`~/.wakeup` (via `sleepwatcher`) covers it. On a genuine wake it checks whether each routine has
already succeeded today and kickstarts the ones that haven't:

```
check_and_kickstart io.amit.claude-android-triage-report android-triage-report 855 12
```

The trailing `12` is what makes this one weekly: **Tuesday is the only catch-up day.** Without it,
a missed Monday would be retried every day for a week.

Two guards in `run-claude-routine.sh` keep the retry safe: a once-per-day success marker, and a
lock directory so a launchd fire and a wake-triggered retry can never overlap. `~/.wakeup` also
never passes `-k` to `launchctl kickstart` — that would SIGKILL a run in flight and strand the
lock, blocking the routine permanently.

## Belt and braces: the dedup check

The launchd/wake-up guards are per-day. The skill adds its own check (step 2) by searching #android
for a post in the last 6 days, because the same report going out twice is the failure the team
would actually notice. Both layers held on 18 Aug 2026 — the wake-up retry ran, found Monday's
post, and skipped.

`--force` overrides it for manual test runs, and labels the post `(test run)` so nobody mistakes it
for the weekly one.

## Running it by hand

```bash
/android-triage-report --dry-run      # build everything, write nothing anywhere
/android-triage-report --no-comment   # Slack only, leave Linear untouched
/android-triage-report --no-research  # Slack only, skip research entirely
/android-triage-report --force        # ignore the 6-day Slack dedup check
```

A dry run is the right way to check the research depth before it lands on customer-visible issues.
`--force` only overrides the *Slack* dedup; the per-issue comment marker always applies.

## Things that will bite you

- **One comment is the entire write surface.** The report proposes a priority; it never sets one,
  and it never touches status, assignee or labels.
- **Comments are deduped by a marker, not by date.** Each comment starts with
  `<!-- android-triage-report -->`; the skill skips any issue that already has one. Without that,
  a slow-moving queue collects one comment per issue per week. A previous comment is never edited
  or deleted — it is a dated snapshot someone may already have acted on.
- **The disclaimer header is mandatory.** The Linear MCP connection is Amit's account, not a bot,
  so every comment is signed "Amit Nayar" — the header is the only thing telling a reader a machine
  wrote it. The proposals are labelled `Suggested fix` / `Suggested priority` for the same reason.
- **Comments are read before the research, not after.** They are both an input (a colleague may
  have already tested the thing) and the dedup source. Reading them last once produced a
  confidently wrong conclusion on AND-1982.
- **Unfurling must be off.** The bullets are full of `linear.app` links, and the Linear Slack app
  answers each one with its own blank message. `unfurl_links: false` + `unfurl_media: false`.
- **The Linear issue is the only source of report context.** No Zendesk, no other ticket system —
  no API call, no CLI, no fetching a linked ticket URL. A linked ticket is counted and named from
  Linear's own metadata as customer signal, and left unopened.
  This is deliberate. Whoever files the issue owns putting the reproduction detail in it, so an
  issue that can't be triaged from its own contents is an incomplete issue. Reconstructing the
  context from elsewhere hides that, and the next report arrives just as thin — so a thin issue gets
  a `Needs info` comment naming exactly what's missing, and stays in `Triage`.
- **`SLACK_API_TOKEN_OFT` comes from `~/.zprofile`**, which a non-login shell does not inherit —
  `set -a && . ~/.zprofile >/dev/null 2>&1; set +a` first.
- **The scheduled run reaches Linear over GraphQL, not MCP.** The claude.ai Linear connector is
  authenticated interactively, so `claude -p --dangerously-skip-permissions` under launchd usually
  can't use it. That is expected, not an outage: the skill's **Transport** section carries the
  `$LINEAR_API_KEY` queries, the team and state ids, and the single sanity check that makes an empty
  queue trustworthy. Before 24 Aug 2026 none of this was written down, and each Monday run
  rediscovered it from scratch.
- **Empty queue posts nothing** and exits 0. A non-zero exit tells the runner it failed, and it
  will retry on the next wake.
- **`node` is not on launchd's PATH**, so plugin `SessionEnd` hooks fail on every scheduled run.
  Harmless, but it is why `.err.log` is never empty.

## History

Until 18 Aug 2026 a second routine, `io.amit.claude-jira-triage`, ran `/linear-issue-triage
Android` every weekday and DM'd a deep per-issue report. It covered the same queue as this Monday
post, ~30 minutes apart. It was removed and its research folded into this report — so if the
research ever feels thin, the fix belongs here rather than in a new daily routine.

The research first went out as Slack thread replies (18 Aug 2026). It moved to Linear comments the
same day: the detail belongs where the engineer already is and where it is still findable next
month, and Slack threads are neither.
