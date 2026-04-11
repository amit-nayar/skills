---
name: handoff
description: Generate a concise markdown handoff document that preserves the full working context of the current session for the next agent session. Use when the user asks for a handoff, continuation summary, or ready-to-paste restart prompt.
user-invocable: true
---

# Session Handoff Summary

Generate a comprehensive handoff document that can be used to continue this work in a new agent session with fresh context.

## Instructions

Analyze the entire conversation and create a structured summary with the following sections:

### 1. OBJECTIVE
What was the original goal or task? Be specific.

### 2. COMPLETED WORK
List everything that has been accomplished:
- Files created or modified, with paths
- Key decisions made and why
- Problems solved

### 3. CURRENT STATE
Where are we right now?
- What's working
- What's partially implemented
- Any failing tests or known issues

### 4. NEXT STEPS
What remains to be done to complete the objective?
- Ordered list of remaining tasks
- Any blockers or dependencies

### 5. KEY CONTEXT
Important information the next session needs to know:
- Relevant file paths
- Architecture decisions
- Gotchas or things that did not work
- Commands that were useful

### 6. CONTINUATION PROMPT
Write a ready-to-paste prompt that can be used to start a new session. It should be self-contained and include enough context to continue seamlessly.

## Output Instructions

1. Generate the handoff document as markdown
2. Display the full output in the conversation
3. Also write the handoff to a temp file at `/tmp/claude-handoff-{timestamp}.md` using the current Unix timestamp
4. Tell the user the file path after writing

Make it concise but complete. The goal is to lose zero important context while staying efficient with tokens.
