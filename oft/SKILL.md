---
name: oft
description: Generate and post a sectioned "Out for Today" summary (GitHub PRs + Claude session work + Slack discussions) to your personal Slack DM as a draft for #mobile. Groups work by workstream, writes outcome + why-it-matters bullets, and filters out small follow-ups on already-reported PRs.
user-invocable: true
allowed-tools: Bash, Read, Agent
---

# Out for Today

Generate an "Out for Today" (OFT) post from GitHub PR activity, Claude Code session history and
Slack discussions, then post it to my personal Slack DM. I read the draft, tweak it, and repost it
to #mobile (`C0273MG80J2`), so write it for that audience: the mobile team and engineering leads,
who want to know what moved and why it matters, not what I touched.

## The bar: what an OFT is for

A reader should be able to skim the post in 20 seconds and come away knowing what changed for
customers, the SDK, the release, or the team. Every bullet has to earn its place.

**Include**
- Work that produced a new PR that day (fix, feature, refactor, docs, tooling), summarised as an outcome.
- A substantial rework of an existing PR (new approach, big scope change), phrased as "Reworked …".
- Investigations, benchmarks, root causes and design decisions that shaped what we will build, even without a PR.
- Decisions with consequences: release scope, backport calls, API shape, ownership.
- Blockers, hand-offs and agreements ("X agreed to take Y").
- Customer-facing threads where I did the analysis or made the call.
- A review where I found something substantive (a real defect, a design concern). Plain approvals are not listed.

**Exclude**
- Small follow-ups to PRs that already exist: review feedback, a small bug fixed on an open branch, CI nudges, rebases, merges, version bumps.
- PRs already reported in a recent OFT unless the target day added genuinely new scope.
- Minor decisions nobody outside the thread will care about tomorrow.
- Coordination noise: review requests, FYIs, ticket assignments, meetings, acknowledgements.
- "Looked into / worked on" filler with no outcome.

Litmus test: if a lead read only this bullet, would it change what they know about the product,
the release or the team? If not, cut it or fold it into a sibling bullet.

## Arguments

Optional date argument: `$ARGUMENTS`

- No argument: **today**.
- Otherwise a natural-language date ("yesterday", "last friday", "2 days ago", "thursday and friday").
- **"last business day"**: yesterday, rolled back over the weekend. On Monday this is the preceding Friday.

## Steps

Steps 2, 3 and 4 are independent and should be run together. Step 5 filters, Step 6 groups and
writes, Step 7 posts. **Do not end the turn until Step 7 has posted or you have decided there is
nothing to post.** Never hand work to a background subagent in this skill: a routine run (`claude -p`)
that ends its turn while an agent is still working is killed after 600s, the post is lost, and the
run still exits 0 and is marked done for the day. Everything here is done inline with the two helper
scripts in `scripts/`.

### 1. Determine the target date(s) FIRST

```bash
TARGET_ISO=$(date +"%Y-%m-%d")                 # today
TARGET_ISO=$(date -v-1d +"%Y-%m-%d")           # yesterday
# last business day
if [ "$(date +%u)" = "1" ]; then TARGET_ISO=$(date -v-3d +"%Y-%m-%d"); else TARGET_ISO=$(date -v-1d +"%Y-%m-%d"); fi
NEXT_ISO=$(date -j -v+1d -f "%Y-%m-%d" "$TARGET_ISO" +"%Y-%m-%d")
DAY_NAME=$(LC_TIME=en_US.UTF-8 date -j -f "%Y-%m-%d" "$TARGET_ISO" +"%A")
SCRATCH=<the session scratchpad directory>   # all intermediate files go here
```

**Header label** (never include a date in parentheses):
- Target is today: `Out for today:`
- Target is yesterday: `Out for yesterday:`
- Any other single day: `Out for Friday:`
- A range: `Out for Thursday & Friday:` or `Out for Monday, Tuesday & Wednesday:`

The header reflects the **target** day(s), not the current day. **Never name a weekday from
memory.** Run `date +%A` for today and the `DAY_NAME` command above for each target date, and use
only those outputs, in the header and in any bullet that mentions a day ("landed Wednesday").

### 2. Gather GitHub PR activity

```bash
gh api search/issues -X GET -f q="author:@me is:pr updated:>=${TARGET_ISO}" --jq '.items[] | {title, html_url, number, repository_url, draft, state}'
```

For each PR:
- `gh api repos/{owner}/{repo}/pulls/{number}/commits --jq '.[] | {sha: .sha[0:7], date: .commit.author.date, msg: .commit.message}'`
  and keep only commits whose author date (in local time) falls on the target day.
- `gh api repos/{owner}/{repo}/pulls/{number}` for `created_at`, `merged_at`, `draft`, body.
- Classify:
  - **New PR** (`created_at` on the target day): candidate for a bullet.
  - **Existing PR, substantial new work** (new approach, large diff, scope change): candidate, phrased as "Reworked …" or "Extended …".
  - **Existing PR, small follow-up** (review fixes, a small bug, CI, rebase, merge only): **drop**. Do not list it, do not add a sub-bullet for it.
- Note `draft: false` for **RTR** marking.
- Reviews I gave that day: `gh api search/issues -X GET -f q="commenter:<login> org:PSPDFKit is:pr updated:>=${TARGET_ISO}"`, then `pulls/{n}/reviews` and `pulls/{n}/comments` filtered to my login and the target date. Keep only reviews with substantive findings.
- Read the PR body and commits to understand the *effect* of the change, and the motivation (customer report, dogfooding, release, flaky CI). That is what the bullet should say.

### 3. Scan Claude Code session history

PRs and Slack miss investigations, benchmarks, decisions and unfinished work. Recover them from
sessions with the bundled digest script (streams the JSONL files, keeps only user/assistant text
timestamped on the target day in Europe/Vienna, and prints a head + tail per session):

```bash
python3 ~/dev/me/skills/oft/scripts/extract_sessions.py ${TARGET_ISO} --per-file 40 --max-chars 300 > "$SCRATCH/sessions.txt"
grep -n '^SESSION' "$SCRATCH/sessions.txt"     # one line per session: project, time span, PR/ticket refs
```

Read the digest (it is ~30 KB for a normal day; read it in one or two `sed -n` chunks). Ignore the
routine sessions (the OFT run itself, branch cleanup, triage report). For each real session note:
what was asked, the outcome, any root cause / benchmark / comparison with numbers, any decision and
its reasoning, any blocker or hand-off, and whether it was new work, a rework, or a small follow-up
on an existing PR. Match sessions to PRs by branch name or PR number.

If the digest leaves an outcome unclear, grep the specific transcript for the PR number, ticket or
keyword rather than reading it whole. Only if a day has many long sessions and the digest is still
ambiguous, dispatch an `Agent` (sonnet) with the same extraction rules and keep working on Steps 2
and 4 while it runs; do not finish the turn before its result is in.

### 4. Gather Slack activity

- **Token**: `SLACK_API_TOKEN_OFT` from `~/.zprofile` (`set -a && . ~/.zprofile >/dev/null 2>&1; set +a`). Do NOT use the `slack` CLI; it is broken on this machine.
- **Identity**: `curl -s https://slack.com/api/auth.test --header "Authorization: Bearer $SLACK_API_TOKEN_OFT"`. Use `.user_id` as `USER_ID` (post target: posting to your own id opens the self-DM) and `.user` (username for search).
- **My messages that day**:
  ```bash
  curl -s "https://slack.com/api/search.messages?query=from%3A<username>+on%3A${TARGET_ISO}&count=100" --header "Authorization: Bearer $SLACK_API_TOKEN_OFT"
  ```
- Group by thread (`thread_ts` in the permalink); fetch `conversations.replies` for threads where I wrote more than a one-liner, to get the question, the alternatives and the outcome.
- Keep only threads where I contributed analysis or made a call (customer investigations, technical decisions, release scope, ownership). Drop announcements, review requests, assignments, meetings, chit-chat, and my own OFT posts.

### 5. Dedup and filter

- Search my recent OFT posts: `search.messages` with `query=from:<username> "Out for"` over the last ~7 days (they land in the self-DM and in #mobile). Collect PR numbers (`#(\d+)`) already reported.
- Drop any PR in that set unless the target day added genuinely new scope (see Step 2). When in doubt, drop.
- Apply the include/exclude bar from the top of this file to everything: PRs, session work, threads.
- **Merge siblings**: several PRs that are one story (three flaky-test fixes, a stack of PRs for one feature, migration guide + release notes) become **one bullet with several links**. Do not list them separately.

### 6. Group and write

#### Sections

Group bullets under **bold workstream headers**. Pick names a reader of #mobile recognises; derive
them from the actual work, do not force the list. Typical ones:

- `Android SDK` (or a feature name when a day is dominated by one: `Keyboard handling`, `Document grid`)
- `Viewer app` (dogfooding fixes surface here)
- `Release` (patch/minor scope, migration guide, release notes, backport decisions)
- `Website & docs`
- `Tooling & CI`
- `Discussions` (customer threads, ownership, cross-team calls that have no PR)

Rules:
- 2 to 5 sections. A section may hold a single bullet if it is a distinct workstream (Nick does this).
- When the whole day is one workstream and there are 3 or fewer bullets, skip headers and post a flat list.
- Order sections by importance to the reader: customer or release impact first, tooling and discussions last.

#### Bullets

Each top-level bullet is **one or two sentences**: the outcome, then, when it adds signal, why it
matters or what triggered it. Link(s) go at the **end**. Numbers stay when they exist (test count,
timings, sizes, percentages).

- Lead with the effect: "Fixed", "Added", "Made", "Kept", "Removed", "Reworked", "Decided", "Settled on". For in-progress work use "Drafting", "Continuing", "Building".
- Say what the reader gains: "so custom layouts keep the document above the keyboard", "found while dogfooding the viewer, not from a customer report", "unblocks the 11.7 release".
- Plain words over identifiers. A code identifier (in `code` style) is fine when it is the clearest name for the thing.
- No mechanism, file names, or repro steps on the bullet line; the PR carries them.
- Mark non-draft PRs with bold **RTR** after the link.
- Slack links use a descriptive label: `thread`, `#android thread`, `Slack handover`.

**Sub-bullets** (`indent: 1`) are for a second layer of signal only:
- a finding from a session (root cause, benchmark result, "turned out X had already built this");
- a decision and its one-line reasoning;
- a blocker, hand-off or next step ("Erhard agreed to take it before the gateway goes to master", "Next: QA next week").

Never add a sub-bullet to restate the PR, and never add one for a small follow-up.

#### Example (rendered)

```
Out for yesterday:

Keyboard handling
• Made the document and its editing toolbars follow the keyboard's slide animation instead of jumping to the final position; this was the most visible rough edge in the viewer app #58821 #58860 RTR
    ◦ Audited every text-entry surface for the same jump; content editing's bar sync only works by timing luck, left as a follow-up risk
• Kept the document visible above the keyboard in custom layouts that handle their own window insets #58818

Document grid & rendering
• Fixed a blank flash when scrolling back to an already-rendered page #58865
• Fixed a background flash and page drift during grid zoom transitions #58803 RTR

Release
• Decided against backporting two changes into the 11.7 patch: the Instant Comments feature adds public API a patch shouldn't carry, and the grid-zoom fix only exists in Compose-only 12.0 code
• Settled on the immersive-mode status bar design: a surface-tinted scrim built into the SDK, not left to viewer apps

Website & docs
• Exposed the latest product versions on the website so Kapa can answer version questions #6025

Viewer app
• Started rebuilding the document tab bar in Compose for Material 3, then dropped it after finding Akshay had already built the same thing #58811
```

#### Block Kit structure

Write the post as a small Markdown outline and let the bundled builder emit the Block Kit JSON:

```bash
cat > "$SCRATCH/outline.md" <<'OUTLINE'
Out for yesterday:

## Release 11.7.0
- Backported the five fixes queued for 11.7.0 onto the release branch and handed a new draft to QA [#58726](https://github.com/PSPDFKit/PSPDFKit/pull/58726) [thread](https://pspdfkit.slack.com/archives/C0C37TMJJ6A/p1790159475183769?thread_ts=1790095447.022169)

## Sepia page appearance
- Reworked the sepia tone to match iOS's measured tone curve; paper colour now matches the iOS app [#58678](https://github.com/PSPDFKit/PSPDFKit/pull/58678)
  - Two variants sit on the branch to test before deciding: two-pass render with a new core flag, or a single pass with no core change
OUTLINE
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" --preview   # eyeball it
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" > "$SCRATCH/oft.json"
```

Outline rules: first line is the header label; `## Name` starts a section; `- ` is a bullet and
`  - ` (two leading spaces) a sub-bullet; inline `[label](url)` for links, `` `code` `` for
identifiers, `**RTR**` for bold. Leave out the `## ` lines for a flat post.

The builder emits one `rich_text` block: each section is a `rich_text_section` holding a newline,
the bold header and a newline, followed by a `rich_text_list` (`indent: 0`); sub-bullets are a
following `rich_text_list` with `indent: 1`. This is the structure Nick's posts use and it renders
with a blank line between sections.

Conventions the outline must follow:
- PR link label is the number only: `#58726`. Several related PRs: links separated by a space, one **RTR** at the end if the set is ready for review.
- Slack link labels are descriptive: `thread`, `#design`, `#engineering thread`, `Slack handover`.
- No emoji.

### 7. Post to the personal DM

- ```bash
  curl -s https://slack.com/api/chat.postMessage --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" --header "Content-Type: application/json; charset=utf-8" --data @"$SCRATCH/oft.json"
  ```
  Use `--header`, not `-H`, and check `"ok": true` in the response.
- Confirm to the user that it was posted and include the `--preview` text in the reply so the routine log shows what went out.
- If nothing meets the bar, post nothing and say so.

## Pitfalls

1. **Never end the turn with a background agent still running.** Use the digest script; if you must use an Agent, wait for its result before finishing. The routine run gets killed after 600s and reports success with no post.
2. **Don't list small follow-ups on existing PRs.** A review fix, a small bug on an open branch, a CI nudge or a rebase is not a bullet and not a sub-bullet.
3. **Don't re-report a PR from a recent OFT** unless the day added real new scope.
4. **Don't split one story across bullets.** Three flaky-test fixes are one bullet with three links.
5. **Don't describe mechanism.** The bullet says what changed for the reader; the PR says how.
6. **Don't pad sections.** No header for a single throwaway bullet; fold it into the nearest workstream or drop it.
7. **Don't use the `slack` CLI or Node helper scripts.** curl + `SLACK_API_TOKEN_OFT` + Block Kit JSON only.
8. **Don't put a date in the header.**
9. **Don't guess weekday names.** Every day name in the post comes from `date`; a wrong day name in the header is the most visible mistake possible.
10. **Slack search results HTML-escape `&`** ("Out for Tuesday &amp; Wednesday"). Match on the timestamp or unescape before comparing when looking up an earlier post (for example to `chat.update` it).
