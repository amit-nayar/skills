---
name: analyze
description: Generate a browser-friendly retrospective of the previous session, focusing on wrong turns, root causes, and concrete repo improvements that would help future agents reach the solution faster and more reliably.
user-invocable: true
---

# Session Analysis Report

Generate a browser-friendly analysis of the previous session, with special focus on places where the agent took the wrong path before later converging on the right one.

Before proceeding, read `.agents/skills/session-report/SKILL.md` and use it as the shared foundation for HTML generation, temp-file handling, and browser opening. This skill adds the `analyze`-specific content requirements below.

## Instructions

Analyze the immediately previous session, not the current one.

Preferred source selection:
1. If Codex session files are available, identify the previous session from `~/.codex/session_index.jsonl` or `~/.codex/sessions/` by timestamp and load that transcript.
2. If Codex session files are unavailable, use the closest available prior session artifact.
3. State which source you used.

Your job is not to produce a generic summary. Instead, reconstruct the path the agent took and identify:
- where it explored too broadly
- where it made an incorrect assumption
- where it used a costly or low-signal investigation step
- where it duplicated effort before finding the simpler path
- where missing repo guidance, tooling, structure, or naming made the mistake more likely

The final goal is to recommend concrete improvements that make the codebase and repo tooling more agent-friendly, so future sessions can reach the correct result with less effort, fewer tokens, and lower reliability risk.

The report must cover:

### 1. SESSION TARGET
What the previous session was trying to achieve.

### 2. FINAL RESULT
What was actually delivered and whether the session succeeded.

### 3. WRONG TURNS
List the meaningful wrong turns or inefficient detours.

For each one, explain:
- what the agent did
- why that direction was suboptimal or wrong
- what later evidence revealed the better path
- what the wasted cost was, such as extra commands, extra search surface, or avoidable uncertainty

### 4. ROOT CAUSES
Summarize the underlying reasons those wrong turns happened.

Focus on repo and codebase causes such as:
- missing or buried documentation
- unclear file ownership or conventions
- poor naming
- absent helper scripts
- repeated patterns that are not codified
- discoverability problems
- lack of high-signal examples

### 5. AGENT-FRIENDLY IMPROVEMENTS
Recommend a concrete set of improvements to the codebase or repo.

Each recommendation must include:
- the improvement
- why it prevents a specific wrong turn
- the expected impact on effort, token usage, or reliability
- the most relevant file or location to change, when you can identify one

Prefer changes like:
- clarifying `AGENTS.md` guidance
- adding command conventions docs
- introducing reusable templates or generators
- adding focused helper scripts
- reducing ambiguous structure
- documenting common workflows next to the files they affect

### 6. EVIDENCE TRAIL
Show the key commands, transcript moments, and file changes that support your analysis.

Do not dump the entire transcript. Curate only the evidence that matters.

### 7. RECOMMENDED NEXT STEPS
End with an ordered action plan for making the repo more agent-friendly.

## Output Instructions

1. Generate the report as HTML
2. Write it to `/tmp/claude-analyze-{timestamp}.html` using the current Unix timestamp
3. In the conversation, do not dump the full HTML unless asked
4. Instead, provide:
   - a short summary of what the report found
   - the file path
   - a brief explanation of the HTML structure and how to read it

Be concrete. The report should help someone improve the repo itself, not just critique the prior agent.
