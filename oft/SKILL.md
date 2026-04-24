---
name: oft
description: Generate and post combined GitHub + Slack daily summary to your DM
user-invocable: true
---


# Out for Today - Combined Summary

Generate a combined summary of GitHub PR activity and Slack discussions, then post it to my personal Slack DM.

## Arguments

The user may provide an optional date argument: `$ARGUMENTS`

- If no argument provided, use **today**
- If argument provided, interpret it as a natural language date (e.g., "yesterday", "last friday", "2 days ago")

## Steps

### 1. Determine the target date FIRST

**CRITICAL: Calculate the target date before doing anything else.**

Use the `date` command to get both the ISO date (for API queries) and the formatted date (for the header):

```bash
# For "yesterday":
TARGET_ISO=$(date -v-1d +"%Y-%m-%d")                    # e.g., "2026-01-29"
TARGET_DISPLAY=$(LC_TIME=en_US.UTF-8 date -v-1d +"%a %b %-d")  # e.g., "Thu Jan 29"

# For "today" (default):
TARGET_ISO=$(date +"%Y-%m-%d")
TARGET_DISPLAY=$(LC_TIME=en_US.UTF-8 date +"%a %b %-d")

# For "last friday" or other dates, calculate accordingly
```

**The header "Out for today (Wed Jan 29):" must show the TARGET date, NOT the current date.**

### 2. Gather GitHub PR activity

- Use `gh api search/issues` to find PRs: `gh api search/issues -X GET -f q='author:@me is:pr updated:>=${TARGET_ISO}' --jq '.items[]'`
- Include ALL PRs updated on the target date (merged, opened, or updated)
- For each PR, check what work was actually done by examining:
  - `gh api repos/{owner}/{repo}/pulls/{number}/commits` to see commits made that day
  - `gh api repos/{owner}/{repo}/pulls/{number}` to check merged_at, state, title, **and draft status**
- **Skip PRs where the only activity that day was merging** (no commits authored that day). Only include PRs where you made actual changes.
- Check the PR's `draft` field - if `draft: false` (meaning ready to review), mark the PR with **RTR**
- Use commit messages and PR context to write accurate action-oriented summaries

### 3. Gather Slack activity

- Get username and user ID via `slack auth test`
- Get token from `slack --help` output (shown as default for -t flag)
- **Use Slack API directly** (the CLI only returns 20 results):
  ```bash
  curl --silent --request GET \
    "https://slack.com/api/search.messages?query=from%3A<username>+on%3A${TARGET_ISO}&count=100" \
    --header 'Authorization: Bearer <token>'
  ```
- For messages that are part of threads (have `thread_ts` in permalink), fetch thread context to understand the full discussion
- Group messages by thread to understand full discussion context
- Filter to technical/customer-related discussions only

### 4. Build Slack Block Kit JSON

- Use `rich_text` blocks with `rich_text_list` for proper native bullet formatting
- Use `indent: 0` for top-level bullets, `indent: 1` for nested bullets
- **Use TARGET_DISPLAY in the header**, e.g., "Out for today (Wed Jan 29):"
- See format section below

### 5. Post to personal DM using Slack API

- Get user ID from `slack auth test`
- Post using curl to `https://slack.com/api/chat.postMessage` with blocks JSON
- **IMPORTANT**: Use `--header` instead of `-H` to avoid shell parsing issues

## Output Format (Slack Block Kit)

Use a single unified bullet list (no separate GitHub/Slack sections). Each item is a top-level bullet with optional nested bullets for details.

Example rendered output:
```
Out for today (Thu Jan 29):

• Fixed login redirect infinite loop when session expired #456
• Added database connection pooling #789
• Started work on user authentication #123 RTR
    • Implementing OAuth2 login flow for the mobile app
• Continued refactoring `PaymentProcessor` class #101
    • Addressed review feedback
• Reviewed memory management approach (thread)
    • Suggested `clearPageCache` as interim solution
    • Questioned if memory budgets are too conservative
• Investigated customer form filling issue (thread)
    • Tested back to v10.7 - confirmed feature request, not regression
```

Note: Code identifiers like `clearPageCache` and `PaymentProcessor` should be rendered as inline code in Slack.

Example Block Kit JSON structure:
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
            {"type": "text", "text": "Out for today (Thu Jan 29):", "style": {"bold": true}}
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
        }
      ]
    }
  ],
  "text": "Out for today (Thu Jan 29)"
}
```

**Key Block Kit patterns:**
- Start new `rich_text_list` with `indent: 0` for top-level PR bullets
- Immediately follow with `rich_text_list` with `indent: 1` for nested detail bullets
- No emoji prefixes for PRs
- PR link goes at the **end** of the line, formatted as `{"type": "link", "url": "...", "text": "#123"}` (just the number, no "PR" prefix)
- For non-draft PRs (ready to review), add `{"type": "text", "text": "RTR", "style": {"bold": true}}` after the PR link
- For Slack discussion links, use `{"type": "link", "url": "https://slack.com/...", "text": "thread"}`
- **For code identifiers** (function names, class names, variable names, etc.), use `{"type": "text", "text": "functionName", "style": {"code": true}}`. Examples of what should be formatted as code:
  - Function/method names: `createBlob`, `clearPageCache`, `invalidateMenu`
  - Class names: `RedactionProcessorFragment`, `ViewerActivity`, `PageLayout`
  - Variable names, constants, file paths with code extensions
  - API names, configuration keys

## Guidelines

### Date handling:
- **ALWAYS calculate the target date first** using the `date` command
- **The header date must be the TARGET date**, not today's date
- If argument is "yesterday" and today is Thu Jan 30, the header should say "Wed Jan 29"
- Double-check the day of week matches the date

### PR items:
- **Only include PRs where you authored commits that day** - skip PRs where the only activity was merging (no new changes)
- No emoji prefixes for PRs
- **Check draft status** - if PR has `draft: false` (ready to review), add **RTR** in bold after the PR link
- PR number link goes at the **end** of the line, formatted as `#1234` (no "PR" prefix)
- NO repo name in brackets - keep it clean
- **Phrase as accomplishments, not PR titles.** Use commit messages and PR changes to describe what was actually done:
  - "Playground example file picker" → "Added file picker to the playground example"
  - "Remove Annotation editing toolbar" → "Started work on removing the annotation editing toolbar"
  - "Fix eraser tool issues" → "Fixed eraser tool zoom detection and line smoothing issues"
  - Use verbs like: Fixed, Added, Started, Continued, Finished, Implemented, Refactored
- **Check commits** to understand the actual work done that day, not just the PR title
- Action description on main bullet, with PR link at end of line
- Add nested bullets for details when useful (based on commits/changes)

### Slack discussion items:
- **Fetch ALL messages** (use count=100 in API call) - the CLI only returns 20
- **Group messages by thread** - messages with similar `thread_ts` are part of the same discussion
- **Read thread context** for substantive discussions to understand the full conversation
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
  - OFT posts (already covered by GitHub section)
  - Single-word responses ("yeah", "ok", "thanks")
  - DMs unless they contain significant technical discussion
- Format as: Brief summary of discussion (link to thread)
- Add nested bullets for key decisions/outcomes/actions taken
- **Summarize what YOU contributed** to the discussion, not just that it happened

### Posting:
- Write the JSON to a temp file first, then use `curl --data @/tmp/file.json`
- Use `--header` instead of `-H` to avoid shell parsing issues with the token
- Confirm to the user that the message was posted
- If nothing to report, don't post anything
