---
name: session-report
description: Create a polished standalone HTML report from an agent session. Use when the user wants a session exported to a browser-friendly page, or when another skill needs a shared workflow for rendering session history, commands, findings, and outcomes as HTML.
user-invocable: true
---

# Session Report

Create a standalone HTML report for a session. This is the shared workflow for browser-friendly session reporting.

Use this skill directly when the request is generic, and use it as the common foundation for more specific reporting skills such as `share` or `analyze`.

## Workflow

1. Identify the session source
   - Prefer the current session unless the request explicitly asks for a previous one
   - If session files are available, state which source was used

2. Extract the high-signal session trail
   - Objective
   - Key steps taken
   - Material commands
   - Important outputs or outcomes
   - Files and artifacts changed
   - Current state
   - Next steps, if any

3. Curate rather than dump
   - Include the commands and evidence that matter
   - Collapse repetitive or low-signal activity
   - Preserve technical accuracy while improving readability

4. Render as a self-contained HTML document
   - Inline CSS and inline JS only
   - No external assets or dependencies
   - Escape commands, snippets, and output correctly

## HTML Requirements

The page should:

1. Be readable on desktop and mobile
2. Have strong visual hierarchy and spacing
3. Use a more user-friendly layout than the terminal
4. Prefer cards, tables, timelines, badges, callouts, and disclosure widgets where they improve scanning
5. Keep the content concise and high-signal

Recommended shared layout:
- Header with title, timestamp, and session source
- Summary cards
- Main narrative or timeline section
- Commands and evidence section
- Files changed section
- Current state and next steps

## Output Instructions

1. Generate a complete standalone HTML document
2. Write it to a temp file under `/tmp` using a task-appropriate filename and the current Unix timestamp
3. Open that file in the default browser
   - On macOS, use `open`
   - On Linux, use `xdg-open`
4. In the conversation, do not dump the full HTML unless asked
5. Instead, provide:
   - A short summary of what the report contains
   - The file path
   - Confirmation that the browser open command was attempted

## Notes For Specialized Skills

Specialized report skills should reuse this workflow and add only their task-specific sections:
- `share`: human-friendly session recap and route-to-solution report
- `analyze`: retrospective focused on wrong turns, root causes, and repo improvements

Avoid duplicating generic HTML, artifact, and browser-open instructions when this skill already covers them.
