---
name: oft
description: Generate and post a combined "Out for Today" summary (GitHub PRs + Claude session work + Slack discussions) to your personal Slack DM. Dedups against recent OFT posts and surfaces non-PR work.
user-invocable: true
allowed-tools: Bash, Read, Agent
---


# Out for Today - Combined Summary

Generate a combined "Out for Today" summary of GitHub PR activity, work done in Claude Code
sessions, and substantive Slack discussions — then post it to my personal Slack DM.

**Guiding principles** (apply to everything below):
- **Outcomes over activity** — describe what was achieved, not what was touched.
- **Signal over noise** — only strategic / substantive work; avoid vague activity logs.
- **Skim-first** — main bullets are one high-level line; the PR link carries the detail.
- **Group only if needed** — flat list by default; group by project only when the day spans several.
- **Call out blockers clearly** — when something is blocked or has an obvious next step, say so.

## Arguments

The user may provide an optional date argument: `$ARGUMENTS`

- If no argument provided, use **today**
- If argument provided, interpret it as a natural language date (e.g., "yesterday", "last friday", "2 days ago")

## Steps

Steps 2, 2.5, and 3 gather from three independent sources and can be run together; Step 3.5 dedups,
Step 4 cross-references, Steps 5–6 format and post.

### 1. Determine the target date(s) FIRST

**CRITICAL: Calculate the target date(s) before doing anything else.**

Use the `date` command to get the ISO date(s) for API queries, and derive a **header label** based on which day(s) are covered.

```bash
# For "yesterday":
TARGET_ISO=$(date -v-1d +"%Y-%m-%d")        # e.g., "2026-01-29"

# For "today" (default):
TARGET_ISO=$(date +"%Y-%m-%d")

# For "last friday" or other dates, calculate accordingly
```

**Header label rules** (use these — do NOT include a date in parentheses):
- Target is today → `Out for today:`
- Target is yesterday → `Out for yesterday:`
- Target is any other single past day → use that day's name, e.g. `Out for Friday:`
- Target is a range of days → list day names joined with `&`, e.g. `Out for Tuesday & Wednesday:` (for a 2-day range), `Out for Monday, Tuesday & Wednesday:` (for 3+ days)

Compute the day name with `LC_TIME=en_US.UTF-8 date -j -f "%Y-%m-%d" "$TARGET_ISO" +"%A"` (e.g., "Friday").

**The header must reflect the TARGET day(s), not the current day.**

### 2. Gather GitHub PR activity

- Use `gh api search/issues` to find PRs: `gh api search/issues -X GET -f q='author:@me is:pr updated:>=${TARGET_ISO}' --jq '.items[]'`
- Include ALL PRs updated on the target date (merged, opened, or updated)
- For each PR, check what work was actually done by examining:
  - `gh api repos/{owner}/{repo}/pulls/{number}/commits` to see commits made that day
  - `gh api repos/{owner}/{repo}/pulls/{number}` to check merged_at, state, title, **and draft status**
- **Skip PRs where the only activity that day was merging** (no commits authored that day). Only include PRs where you made actual changes.
- Check the PR's `draft` field - if `draft: false` (meaning ready to review), mark the PR with **RTR**
- Use commit messages and PR context to write accurate action-oriented summaries

### 2.5. Scan Claude Code session history (surfaces non-PR work)

PRs and Slack miss work that never reached a PR — debugging investigations, benchmark findings,
architectural decisions, and work-in-progress. Scan recent Claude Code sessions to recover it.

1. **Find recent session transcripts** (main sessions only, excluding subagent transcripts):

   ```bash
   find ~/.claude/projects -name "*.jsonl" -mtime -1 -not -path "*/subagents/*" 2>/dev/null
   ```

   `-mtime -1` covers the last 24h. For a target date other than today, widen/scope accordingly.

2. **Dispatch an `Agent` (sonnet) subagent** to summarise the sessions. The subagent should:
   - Read the first ~200 and last ~100 lines of each session JSONL (head/tail piped through
     `python3 -c` to extract user/assistant text — these files are large; do not read whole files)
   - Derive the worktree/branch name from the file path
   - Identify what was asked (first user messages) and summarise key outcomes
   - Return a concise summary organised by work area, focused on: **debugging root causes**,
     **benchmark / comparison findings**, **architectural decisions**, **blockers hit + workarounds**,
     and **substantial work that has no PR yet**

3. **Cross-reference with PRs** (see Step 4): match a session to a PR by branch/worktree and enrich
   that PR with a *finding* sub-bullet; otherwise add a standalone item only if it represents real
   effort (≥~30 min) and genuinely has no code artifact yet.

### 3. Gather Slack activity

- **Token**: use `SLACK_API_TOKEN_OFT` from `~/.zprofile` (e.g. `source ~/.zprofile`, or grep the var). Do NOT use the `slack` CLI — it is not functional on this machine.
- **Identity**: resolve user id + username via the `auth.test` endpoint:
  ```bash
  curl -s "https://slack.com/api/auth.test" --header "Authorization: Bearer $SLACK_API_TOKEN_OFT"
  ```
  Use `.user_id` (the post target — posting to your own user id opens the self-DM) and `.user` (username for the search query below).
- **Search messages** via the Web API directly (the CLI only returns 20 results):
  ```bash
  curl --silent --request GET \
    "https://slack.com/api/search.messages?query=from%3A<username>+on%3A${TARGET_ISO}&count=100" \
    --header "Authorization: Bearer $SLACK_API_TOKEN_OFT"
  ```
- For messages that are part of threads (have `thread_ts` in the permalink), fetch thread context via `conversations.replies` to understand the full discussion
- Group messages by thread to understand full discussion context
- Filter to technical/customer-related discussions only (see Guidelines)

### 3.5. Dedup against recently-reported PRs

We don't save OFT files locally, so dedup against my own recent OFT posts already in Slack:

- Search my recent OFT posts: `search.messages` with `query=from:<username> "Out for"` over the last ~7 days
- Extract PR numbers already reported (regex `#(\d+)`) from those posts into a set
- For any PR in that set, **exclude it** unless it has **new commits authored on the target date**
  (substantial new work — a refactor, feature change, or major rework, not just a merge/rebase/review)
- When in doubt, **exclude** — a recent OFT already covered it

This complements the Step 2 rule ("only PRs with commits authored that day").

### 4. Cross-reference all sources

Build one unified picture before formatting:

| Signal | Cross-reference | Action |
|---|---|---|
| PR with commits that day, not recently reported | — | Include as a main bullet |
| Session work matching a PR's branch | Step 2 PRs | Enrich that PR with a *finding* sub-bullet |
| Substantial session work with no PR (≥30 min) | — | Standalone item (high-level) |
| Slack thread that shaped a PR | Step 2 PRs | Sub-bullet under that PR with the actual outcome/decision |
| Substantive standalone discussion (no PR) | — | Standalone item with a `(thread)` link |
| Blocker / dependency / clear next step | any of the above | Phrase as a blocker item or sub-bullet |

### 5. Build Slack Block Kit JSON

- Use `rich_text` blocks with `rich_text_list` for native bullet formatting
- `indent: 0` for top-level bullets; `indent: 1` for sub-bullets (findings, blockers, discussion outcomes)
- **Use the header label from Step 1** (e.g., "Out for today:") — do NOT append a date in parentheses
- **Grouping**: default to a single flat list. Only when the day clearly spans multiple distinct
  projects, precede each project's `rich_text_list` with a bold standalone header section. Omit
  headers entirely for a single-project day.
- See the format section below

### 6. Post to personal DM using the Slack API

- Post to `.user_id` (from `auth.test`) — this is the self-DM
- Write the JSON to a temp file, then `curl --data @<tmpfile>` to `https://slack.com/api/chat.postMessage`
- **Use `--header` (not `-H`)** to avoid shell-parsing issues with the token
- Confirm to the user that the message was posted. If there's nothing to report, don't post anything.

## Output Format (Slack Block Kit)

A single unified bullet list (no separate GitHub/Slack/session sections). Each item is a **single,
high-level top-level bullet** — one short, outcome-oriented line that captures the gist, with the PR
link at the end for anyone who wants the detail. Reader skims the list, clicks through for specifics.

**Main bullets**: one plain-language sentence describing the broad outcome ("Fixed a flaky layout
test", "Added an OOM placeholder for failed page renders"), not the mechanism, root cause, file names,
or steps. Drop the "why" and "how" — that lives in the PR. Prefer everyday words over code identifiers.

**Sub-bullets** (use sparingly, `indent: 1`): allowed ONLY for genuine value — a finding surfaced from
a session or thread, a blocker / next step, or the outcome of a substantive discussion. **Never add
sub-bullets for routine PRs.**

**Grouping**: flat by default; bold project headers only when the day spans several projects.

Example rendered output (single-project day — flat, no headers):
```
Out for today:

• Fixed the login redirect loop on expired sessions #456
• Added database connection pooling #789
• Started work on user authentication #123 RTR
• Investigated a customer form-filling issue (thread)
    ◦ Root cause was a stale annotation cache; fix tracked separately
• Blocked on the licensing service rollout — waiting on infra to bump the replica count
```

Example rendered output (multi-project day — grouped):
```
Out for today:

Android
• Fixed a couple of eraser-tool issues #321
• Started removing the annotation editing toolbar #322 RTR

Web
• Added a file picker to the playground example #410
    ◦ Benchmarked picker latency — native input ~3x faster than the JS shim
```

Example Block Kit JSON structure (flat list with a finding sub-bullet and a blocker):
```json
{
  "channel": "<user_id>",
  "blocks": [
    {
      "type": "rich_text",
      "elements": [
        {
          "type": "rich_text_section",
          "elements": [
            {"type": "text", "text": "Out for today:", "style": {"bold": true}}
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 0,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {"type": "text", "text": "Fixed login redirect infinite loop when session expired "},
                {"type": "link", "url": "https://github.com/org/repo/pull/456", "text": "#456"}
              ]
            },
            {
              "type": "rich_text_section",
              "elements": [
                {"type": "text", "text": "Added defenses around "},
                {"type": "text", "text": "createBlob", "style": {"code": true}},
                {"type": "text", "text": " call sites "},
                {"type": "link", "url": "https://github.com/org/repo/pull/123", "text": "#123"},
                {"type": "text", "text": " "},
                {"type": "text", "text": "RTR", "style": {"bold": true}}
              ]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 1,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {"type": "text", "text": "Benchmark showed the cache miss was the hot path, not serialization"}
              ]
            }
          ]
        },
        {
          "type": "rich_text_list",
          "style": "bullet",
          "indent": 0,
          "elements": [
            {
              "type": "rich_text_section",
              "elements": [
                {"type": "text", "text": "Blocked on the licensing rollout — waiting on infra to bump the replica count"}
              ]
            }
          ]
        }
      ]
    }
  ],
  "text": "Out for today"
}
```

**For a grouped (multi-project) day**, precede each project's `rich_text_list` with a bold header section:
```json
{
  "type": "rich_text_section",
  "elements": [{"type": "text", "text": "Android", "style": {"bold": true}}]
}
```

**Key Block Kit patterns:**
- Top-level PR bullets: `rich_text_list` with `indent: 0`, one line each
- Sub-bullets (findings / blockers / discussion outcomes): a following `rich_text_list` with `indent: 1` — used sparingly, never for routine PRs
- No emoji prefixes for PRs
- PR link goes at the **end** of the line, formatted as `{"type": "link", "url": "...", "text": "#123"}` (just the number, no "PR" prefix)
- For non-draft PRs (ready to review), add `{"type": "text", "text": "RTR", "style": {"bold": true}}` after the PR link
- For Slack discussion links, use `{"type": "link", "url": "https://slack.com/...", "text": "thread"}`
- Project group headers (only when grouping): a bold `rich_text_section` immediately before that group's list
- **For code identifiers** (function names, class names, variable names, etc.), use `{"type": "text", "text": "functionName", "style": {"code": true}}`. Examples:
  - Function/method names: `createBlob`, `clearPageCache`, `invalidateMenu`
  - Class names: `RedactionProcessorFragment`, `ViewerActivity`, `PageLayout`
  - Variable names, constants, file paths with code extensions
  - API names, configuration keys

## Guidelines

### Date handling:
- **ALWAYS calculate the target date(s) first** using the `date` command
- **The header label must reflect the TARGET day(s)**, not today
- Use `today` / `yesterday` for those two cases; otherwise use the day-of-week name (e.g. `Friday`)
- For multi-day ranges, join day names with `&` (e.g. `Tuesday & Wednesday`); use commas + `&` for 3+ days (e.g. `Monday, Tuesday & Wednesday`)
- Do NOT include a date in parentheses in the header

### PR items:
- **Only include PRs where you authored commits that day** — skip PRs whose only activity was merging
- **Dedup against recent OFT posts** (Step 3.5) — skip a PR already reported unless it has substantial new work that day
- No emoji prefixes for PRs
- **Check draft status** — if `draft: false` (ready to review), add **RTR** in bold after the PR link
- PR number link goes at the **end** of the line, formatted as `#1234` (no "PR" prefix); NO repo name in brackets
- **Keep it high-level — one short outcome line per PR.** The PR link carries the specifics.
- **Phrase as a broad accomplishment, not the PR title or mechanism**, using commit messages + changes to understand what was done:
  - "Playground example file picker" → "Added a file picker to the playground example"
  - "Remove Annotation editing toolbar" → "Started removing the annotation editing toolbar"
  - "Fix eraser tool zoom detection and line smoothing in stroke buffer" → "Fixed a couple of eraser tool issues"
  - Verbs: Fixed, Added, Started, Continued, Finished, Implemented, Refactored
- **Do NOT include** on the main line: root-cause explanations, the fix mechanism, file/class/function names, repro steps, or "why" clauses — let the PR carry them
- **No sub-bullets for routine PRs.** Add a sub-bullet only when a session or thread surfaced a genuine finding worth recording.

### Session items (from Step 2.5):
- Enrich a matching PR with a one-line *finding* sub-bullet (root cause, benchmark result, decision) when it adds real signal
- Add a standalone high-level item only for substantial work (≥~30 min) with no PR yet
- Skip sessions that only did minor fixes, rebases, or already-reported work

### Slack discussion items:
- **Fetch ALL messages** (use `count=100`) and **group by thread**; read thread context for substantive discussions
- ONLY include substantive technical discussions:
  - Customer issue investigations (debugging, troubleshooting)
  - Technical decisions and architecture discussions
  - Code review discussions with technical insights
  - Feature/bug discussions where you contributed analysis
  - Cross-team technical coordination
- Ignore ALL of these:
  - Announcements ("FYI...", "merged...", "shipped...")
  - PR review requests ("can you review...", "RTR...")
  - Ticket assignments ("assigned you...", "cc @person")
  - Simple delegation or coordination
  - Meetings, social chat, greetings, acknowledgments
  - OFT posts (already covered by the PR section)
  - Single-word responses ("yeah", "ok", "thanks")
  - DMs unless they contain significant technical discussion
- Format as: brief summary of the discussion `(thread)` link
- **Summarize what YOU contributed and the outcome/decision** — not just that it happened — as the sub-bullet. Tell the story: what was proposed, what pushback/alternative was raised, what changed.

### Blockers / next steps:
- When work is genuinely blocked or has an obvious next step, surface it — as its own item or a
  sub-bullet — phrased plainly ("Blocked on …", "Next: …")
- Don't pad: omit entirely if there's nothing real to call out

### Posting:
- Resolve the token from `SLACK_API_TOKEN_OFT` (`~/.zprofile`) and the user id from `auth.test`
- Write the JSON to a temp file, then `curl --data @/tmp/file.json` to `chat.postMessage`
- Use `--header` instead of `-H` to avoid shell-parsing issues with the token
- Confirm to the user that the message was posted; if nothing to report, don't post

## Common Pitfalls (Avoid These!)

1. **DON'T use the `slack` CLI** — it is broken on this machine (`slack auth test` / `slack --help` fail). Use **curl + `SLACK_API_TOKEN_OFT`** and the `auth.test` endpoint instead.
2. **DON'T reference Node helper scripts** (`post-message.js`, `search-my-messages.js`, etc.) — they don't exist here. Post via curl + Block Kit `rich_text` JSON.
3. **DON'T include PRs whose only activity was merging** — only PRs with commits authored that day.
4. **DON'T re-report a PR already in a recent OFT** unless it has substantial new work (Step 3.5).
5. **DON'T be verbose on the main line** — "Fixed CVEs in AI Assistant", not the full root-cause paragraph.
6. **DON'T add sub-bullets to routine PRs** — reserve them for genuine findings, blockers, or discussion outcomes.
7. **DON'T always group** — flat single list by default; group by project only when the day spans several.
8. **DON'T log activity** — describe outcomes; drop vague "looked into / worked on" filler.
