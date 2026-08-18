---
name: android-triage-report
description: Post a weekly snapshot of the Android team's Linear Triage queue to the #android Slack channel, and attach the per-issue research as a comment on each Linear issue, so untriaged issues don't sit unnoticed. Use when asked for a triage report, the triage queue, or what's waiting in Android triage.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob, mcp__claude_ai_Linear__list_issues, mcp__claude_ai_Linear__get_issue, mcp__claude_ai_Linear__list_comments, mcp__claude_ai_Linear__save_comment
---

# Android triage queue — weekly report

Snapshot every issue sitting in the **Android** team's `Triage` status in Linear, post it to
**#android** (`C01FUDUNAE7`) as a nudge to get the queue cleared, and attach the research as a
comment on each Linear issue so whoever picks it up starts with the investigation already done —
clearly marked as an unreviewed machine suggestion.

**Guiding principles**
- **Actionable, not decorative** — the reader should be able to pick an issue and triage it from the post.
- **Slack nudges, Linear holds the detail** — the channel message stays a short linked list; the
  research goes on the issue, where the person doing the work already is and where it stays findable
  next month. Never let the Slack post grow into an analysis dump.
- **Suggestions, never verdicts** — every conclusion is an LLM's reading of the issue and the code,
  unverified by a person. The comment says so at the top, and each proposal is labelled
  `Suggested fix` / `Suggested priority`. An engineer reviews before anything is acted on.
- **Oldest pain first** — something stuck in triage for three weeks matters more than yesterday's report.
- **Customer signal wins** — an issue with a linked support ticket or `customerNeeds` outranks one
  without. The link itself is the signal; the ticket is never opened.
- **Silence when clean** — an empty queue posts nothing at all.
- **One comment, no field changes** — the only write this skill ever makes is a research comment.
  It never sets status, priority, assignee or labels. It proposes; humans decide.
- **Comment once per issue** — a weekly run must not re-comment on an issue it already covered.

## Arguments

`$ARGUMENTS` may contain:
- `--dry-run` — build the report and the comments and print them, but write **nothing** to Slack
  or Linear. Always honour this.
- `--no-research` — post the Slack message only, skipping steps 4 and 7 (no Linear comments). Use
  when Linear is readable but the monorepo checkout is unusable.
- `--no-comment` — do the research and print it, but post only to Slack, leaving Linear untouched.
- `--force` — skip the 6-day dedup check in step 2 and post anyway. **Manual test runs only.**
  Never pass this from the launchd agent: the dedup check is the only thing stopping the Tuesday
  wake-up catch-up from double-posting.
- nothing — build, post to Slack, and comment on each issue.

## Steps

### 1. Fetch the triage queue

```
mcp__claude_ai_Linear__list_issues
  team: "Android"
  state: "triage"
  includeArchived: false
  limit: 100
  fields: ["id", "title", "url", "priority", "createdAt", "labels", "assignee"]
```

`Triage` is the Android team's only triage-type status (verified 2026-08-04 — the old `New`
status no longer exists). Use `state: "triage"` (the type) rather than the name, so a rename
doesn't silently return zero issues.

**If the queue is empty: post nothing and stop.** Log that fact for the user and exit 0 — an
empty run is a success, not a failure.

### 2. Guard against a duplicate post

The launchd agent fires Monday, and `~/.wakeup` may retry it Tuesday if the Mac was asleep.
Before posting, check whether this report already went out in the last 6 days:

```bash
curl --silent --request GET \
  "https://slack.com/api/search.messages?query=from%3A<username>+in%3A%23android+%22Android+triage+queue%22&count=20" \
  --header "Authorization: Bearer $SLACK_API_TOKEN_OFT"
```

If a matching post exists with a `ts` newer than 6 days ago, **skip the Slack post** and say so.
Still run step 7: the per-issue comment has its own marker-based dedup, so it is safe, and an issue
that entered triage since the last run deserves its comment even when Slack has already been
nudged this week.

`--force` skips this check. When it is passed, label the parent so the channel knows it is not the
weekly run: append ` (test run)` to the header text. A test post that looks identical to the real
one makes the next reader distrust both.

### 3. Enrich each issue

The queue is normally small (single digits). For each issue — capped at the 20 oldest if it is
somehow larger — call:

```
mcp__claude_ai_Linear__get_issue
  id: "<identifier>"
  includeCustomerNeeds: true
```

From the response take:
- **Time in triage** — from `stateHistory`, the entry whose `state.name` is `Triage` and whose
  `endedAt` is `null`; the age is now minus its `startedAt`. Fall back to `createdAt` only if no
  such entry exists.
- **Customer pressure** — count `attachments` whose `url` contains `zendesk.com/tickets/`, plus any
  `customerNeeds`, and note the organisation names when the needs carry them. This is Linear
  metadata: counting and naming a linked ticket is fine, **opening it is not** (see step 4a).
- **Existing comments** — call `mcp__claude_ai_Linear__list_comments` for the issue **now**, not
  later. It serves two purposes and both matter:
  1. **Research input.** A colleague may already have tested the thing you are about to hypothesise
     about. On 18 Aug 2026 an engineer's comment on AND-1982 disproved a code-level conclusion this
     skill had already reached from the bindings alone — the field existed, but their device testing
     showed the server never sends it. Reading comments last would have shipped that error.
  2. **The dedup marker** for step 7 (`<!-- android-triage-report -->`).
  Also note any **human triage decision** already recorded ("deferring to backlog", "not
  reproducible"). Never re-litigate one: acknowledge it and scope the research around it.
Do **not** substitute `createdAt` for triage age in general: a migrated issue created in 2025 may
have entered triage last week, and reporting it as "400d in triage" is wrong.

### 4. Research each issue

This is the depth of the report and the reason it runs on opus with a 100-turn budget. Work the
issues in the step-5 order and **timebox to roughly 10 turns each** — a queue of eight must not
starve the last two. If the budget runs short, post bullets for the remainder and say so in their
comments (see "When research can't be done").

Run these four passes per issue. Each maps to one labelled line in the comment.

**a. Support context — from the issue only.** Re-read the description and the comments fetched in
step 3. Weigh a colleague's first-hand testing above anything inferred from the code.

**Do not open a linked support ticket, and do not call the Zendesk API.** The Linear issue is the
only source of report context. Whoever files the issue is responsible for putting the reproduction
detail in it, so an issue that cannot be triaged from its own contents is an incomplete issue — and
the useful response is to say so, not to reconstruct the context from another system. Reconstructing
it hides the gap and the next report arrives just as thin.

Report only facts the issue records, and only ones **not already obvious from it** — the reader has
the issue open in the next tab. Naming the customer and ticket number from Linear's own metadata is
fine; describing the ticket's contents is not.

**b. Duplicate check.** Search with `mcp__claude_ai_Linear__list_issues` using normalized title
keywords via `query`. Search the **whole workspace**, not just Android: the same defect is often
filed against `Core`/`COREL` too, and genuinely cross-platform bugs belong on Core. Check open
issues first, then recently-updated completed ones. Also check the other issues **in this same
queue** against each other — two tickets from one customer report arriving together is the most
common duplicate pattern here.

**c. Code investigation.** The routine runs from `/Users/amit/dev/nutrient/monorepo`. Search for
stack frames, symbols, user-visible strings and feature flags; trace the likely path from entry
point to the symptom; read the implementation, its nearby tests, and recent commits touching the
same lines (`git log -L` or `git log --oneline -- <path>`). Aim for a named root cause in a named
file, not a list of files that matched a grep.

**d. Suggested priority and fix.** Give the smallest safe fix first, then the robust follow-up if
the minimal fix leaves structural risk, and name what could break. Suggest a priority from impact
breadth and severity — confirmed multi-customer impact, a regression in a stable path, data loss
or crashes — not from customer insistence or from how many duplicates you found.

**When the issue doesn't carry enough to reach a conclusion, that is the finding.** Say exactly
what is missing and leave the issue in `Triage` — this skill never changes status anyway, so the
point is to make the gap explicit rather than to paper over it. `Needs info: exact device + SDK
version, and whether it reproduces on a non-rotated document` is a useful comment; an invented root
cause is not. Look for: affected version, platform and device, exact steps, expected versus actual,
frequency, and logs or screenshots. Never present a hypothesis as a finding.

### 5. Order the list

1. Priority `Urgent` then `High` first.
2. Within the same priority, longest time in triage first.
3. `Medium` / `Low` / `None` after those, again oldest-first.

Comments are written in the same order, so the oldest issue gets attention first if the budget runs short.

### 6. Post the queue to #android

Build Block Kit `rich_text` JSON, write it to a temp file, and post with curl:

```bash
curl --silent --request POST "https://slack.com/api/chat.postMessage" \
  --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" \
  --header "Content-Type: application/json; charset=utf-8" \
  --data @/tmp/android-triage-report.json
```

- Token: `SLACK_API_TOKEN_OFT` from `~/.zprofile` (`set -a && . ~/.zprofile >/dev/null 2>&1; set +a`).
  A plain Bash call does not inherit login-shell vars.
- Use `--header`, never `-H`, to avoid shell-parsing issues with the token.
- `"channel": "C01FUDUNAE7"` (#android). No thread — the research goes to Linear in step 7.
- Check `.ok` in the response; report the failure verbatim if it is `false`.
- Set `"unfurl_links": false` and `"unfurl_media": false`. Without them the Linear Slack app answers
  each `linear.app` link with its own near-empty message (`metadata.event_type: "ignoreMessage"`) —
  four issues, four blank posts. Verified 18 Aug 2026; the bullets carry issue links by design, so
  this is not optional.
- A failed Slack post does **not** cancel step 7. The Linear comments are the more durable half of
  this report; post them anyway and report the Slack failure.
- Never `@here`/`@channel` — this is a standing report, not an incident.

### 7. Post the research as a comment on each Linear issue

For each issue, in step-5 order:

**a. Check for a previous automated comment first.** This is the one thing that must not go wrong —
the routine fires every Monday, and an issue can sit in triage for weeks. Use the comments already
fetched in step 3; only re-fetch if that run is old enough that a comment could have landed since.

If any comment already contains the marker string `<!-- android-triage-report -->`, **skip this
issue** and log that it was skipped. Do not post a second comment, and do not edit the old one:
the first comment is a dated snapshot of what the code looked like then, and silently rewriting it
would destroy the only record of what a reader may already have acted on.

**b. Otherwise post one comment:**

```
mcp__claude_ai_Linear__save_comment
  issueId: "<KEY>"
  body: "<the markdown below>"
```

Check the result. If it fails, keep going with the remaining issues and report which ones failed —
a missing comment is better than an aborted run.

**Never** call `save_issue`. No status, priority, assignee, label, or description change, ever,
however obvious the right answer looks. The comment is the entire write surface.

## Output format

### The Linear comment

The body is markdown. The header block is **mandatory and verbatim** apart from the date — it is
the only thing telling a reader this was not written by a colleague:

```md
<!-- android-triage-report -->
### 🤖 Automated triage research — unreviewed

Generated by the `android-triage-report` routine on <YYYY-MM-DD>. This is an LLM's reading of the
issue, its support context and the code. **Nothing here has been verified by an engineer** — treat
it as a starting point to check, not a conclusion to act on. No field on this issue was changed.

---

**Support:** …
**Duplicate:** …
**Code:** …
**Suggested fix:** …
**Suggested priority:** Medium — …
**Watch:** …
**Needs info:** …
```

- Include only the labels that have something to say, in that order.
- **The comment posts under Amit's name**, because the Linear MCP connection is his account — there
  is no bot user. That is precisely why the header block is mandatory and not negotiable: without it
  the comment reads as a colleague's considered analysis, signed by a colleague.
- **`Suggested fix` and `Suggested priority` keep the word "Suggested".** Never `Fix:` or
  `Priority:`, and never phrase a priority as settled ("this is High"). Say
  `Suggested priority: High — <impact rationale>`; the rationale is what lets a human disagree.
- Wrap identifiers, file paths and symbols in backticks. Repo-relative paths only — never
  `/Users/amit/...`.
- Reference other issues by key (`AND-1968`); Linear links them automatically.
- Keep each label to one or two sentences, and the whole comment under ~15 lines. If the
  investigation genuinely needs more room, say the short version and note what was left out.
- **State uncertainty in the line that carries it**, not in a disclaimer at the end. "The mechanism
  is X; whether it is also the regression is unconfirmed" is worth more than a hedge on everything.

### Slack message

Unchanged from before, except the closing line. Research no longer lives in Slack:

```
Android triage queue — 3 waiting

• AND-1937 jira and zd CLIs missing on the triage routine host — Low · 8d
• AND-1952 Crash opening password-protected files — Urgent · 3d · 2 customer tickets (Acme, Globex)
• AND-1948 Toolbar icons misaligned in RTL — no priority · 21d

Research is on each issue as a comment · Triage them in Linear
```

Block Kit shape:
- One bold `rich_text_section` header: `Android triage queue — <n> waiting` (`1 waiting` for one issue).
- One `rich_text_list`, `style: "bullet"`, `indent: 0` — one section per issue:
  - `{"type": "link", "url": "<issue url>", "text": "AND-1937"}` then the title as plain text.
  - Then ` — ` and the metadata, joined with ` · `: priority, age (`8d`, or `3w` past 21 days),
    and `N customer ticket(s) (<orgs>)` only when N > 0.
- Wrap code identifiers in `{"style": {"code": true}}` — CLI names, class names, file paths.
- Closing `rich_text_section`: the plain text `Research is on each issue as a comment · ` followed
  by a link titled `Triage them in Linear` pointing at
  `https://linear.app/nutrient/team/AND/triage`.
  Keep the first half whenever the listed issues **have** a research comment — including ones
  written by an earlier run, which is the normal case from week two onward. Drop it only when no
  listed issue has one at all (`--no-comment` / `--no-research`, or every issue's research failed).
  The test is "is the research there for the reader", not "did this run write it".
- Set the fallback `"text"` field to `Android triage queue — <n> waiting`.
- **No thread.** There are no reply messages any more.

**No research in the Slack post.** No sub-lines, no priority suggestions, no findings.

### When research can't be done

Still post the Slack bullet, and still comment — with the gap stated instead of omitted:

```md
**Needs info:** no repro steps on the issue and no linked customer ticket — which app surface,
which SDK version, and does the author id appear in the raw Instant payload? Leaving this in
`Triage` until that lands.
```

If a data source is down — Linear degraded, monorepo checkout missing — say that once, in plain
words, in the affected line (`**Code:** not investigated — monorepo checkout unavailable this
run.`). Never post a comment whose labels are present but empty, and never let a source outage
silently turn into "nothing found".

If **nothing** could be researched for an issue, post no comment for it rather than a comment that
only contains the disclaimer. An empty automated comment on a customer's issue is pure noise, and
the marker would then block the useful comment a later run could have made.

## Guidelines

- **Rewrite titles for a reader, not a tracker.** Strip ticket-speak and leading prefixes; keep it
  under ~80 chars. `Scheduled jira-triage routine: required jira and zd CLIs are not installed` →
  `jira and zd CLIs missing on the triage routine host`. Never invent detail the issue doesn't have.
- **Say "no priority"** rather than omitting it, so an untriaged priority is visible as a gap.
- **Ages**: `<1d` for under 24h, `Nd` up to 21 days, then `Nw`.
- **Suggested, not decided.** The comment says `Suggested priority: High — <rationale>`; it never
  says the issue *is* High, and this skill never sets the field. Triage stays a human decision.
- **Write for the engineer who picks this up cold.** They have the issue open and have not read the
  Slack post. The comment should stand on its own without it.
- **A human's first-hand test outranks your code reading.** When a comment reports what someone
  actually observed on a device, and the code suggests otherwise, say so explicitly and treat their
  result as the fact. The bindings declaring a field does not prove anything populates it.
- **Don't report issues from other teams**, even if they mention Android. A cross-team duplicate is
  fine to *name* in a `Duplicate:` line — it just doesn't get its own bullet or its own comment.

## Common pitfalls

1. **DON'T use the `slack` CLI** — it is broken on this machine. curl + `SLACK_API_TOKEN_OFT` only.
2. **DON'T comment twice on an issue** — check for the `<!-- android-triage-report -->` marker
   first. This fires weekly against a queue that moves slowly; without the check, a three-week-old
   issue collects three comments.
3. **DON'T edit or delete a previous automated comment** — it is a dated snapshot someone may have
   already acted on. Skip instead.
4. **DON'T call `save_issue`** — no status, priority, assignee, label or description change. The
   comment is the only write.
5. **DON'T drop the header block** — without it the comment reads as a colleague's considered
   analysis, which is exactly the misunderstanding it exists to prevent.
6. **DON'T write `Fix:` or `Priority:`** — they are `Suggested fix:` and `Suggested priority:`.
7. **DON'T put research in the Slack post** — it defeats the queue nudge. Linear holds the detail.
8. **DON'T post to Slack with unfurling on** — the Linear app turns each issue link into a blank
   message. `unfurl_links: false` + `unfurl_media: false`.
9. **DON'T post a comment containing only the disclaimer** — no findings means no comment, or the
   marker blocks a later run that would have had something to say.
10. **DON'T post when the queue is empty** — exit quietly and successfully.
11. **DON'T use `createdAt` as triage age** — migrated issues predate their triage entry by months.
12. **DON'T skip the 6-day dedup check** — the wake-up catch-up can fire this twice in a week.
13. **DON'T filter by status name `"Triage"`** — filter by the `triage` type.
14. **DON'T report support detail the issue doesn't record** — `Needs info` instead.
15. **DON'T touch Zendesk at all** — no API call, no CLI, no ticket URL fetch. The Linear issue is
    the only source of report context; a thin issue gets a `Needs info` comment, not an
    investigation in another system.
16. **DON'T present a hypothesis as a root cause** — `Needs info` is a valid, useful answer.
17. **DON'T research before reading the issue's comments** — the answer, or the disproof of your
    answer, is often already there.
18. **DON'T re-argue a triage decision a human already recorded** — acknowledge it and scope around
    it.
19. **DON'T exit non-zero on "nothing to report"** — the launchd runner treats non-zero as failure
    and will retry on the next wake.
