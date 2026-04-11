---
name: share
description: Generate a browser-friendly HTML session report that explains the route to the solution, key commands used, files changed, and current state. Use when the user asks to share a session, export the session trail, or present terminal work in a more readable webpage.
user-invocable: true
---

# Session Share Report

Generate a browser-friendly session report that captures the work in a format that is easier to read and share than the terminal transcript.

Before proceeding, read `.agents/skills/session-report/SKILL.md` and use it as the shared foundation for HTML generation, temp-file handling, and browser opening. This skill adds the `share`-specific content requirements below.

## Instructions

Analyze the full session and produce a polished, self-contained HTML page that summarizes the work in a user-friendly layout.

The report should cover:

### 1. OBJECTIVE
What was the original goal or task?

### 2. OUTCOME
What was delivered, what changed, and whether the objective is complete.

### 3. ROUTE TO SOLUTION
Show the path taken through the problem:
- Key investigation steps
- Important discoveries
- Decisions made and why
- Dead ends, reversals, or alternatives considered

### 4. COMMANDS USED
Show the terminal commands used during the session in a readable format.
- Include all materially relevant commands
- For each command, include a concise summary of the result
- Group related commands when that improves readability
- Collapse repetitive or low-signal commands into a summarized section instead of dumping noise

### 5. FILES AND ARTIFACTS
List files created or modified, with a brief explanation of each change.

### 6. CURRENT STATE
Summarize:
- What's working
- What is partially done
- Any known issues, caveats, or unverified areas

### 7. NEXT STEPS
If anything remains, show the recommended next actions in order.

## Output Instructions

1. Generate the report as HTML
2. Write it to `/tmp/claude-share-{timestamp}.html` using the current Unix timestamp
3. In the conversation, do not dump the full HTML unless asked
4. Instead, provide:
   - A short summary of what the report contains
   - The file path

Keep the report concise, complete, and pleasant to scan. The goal is to preserve the session trail, commands, and reasoning, but present it like a clean project report instead of a raw terminal log.
