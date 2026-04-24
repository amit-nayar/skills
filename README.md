# skills

Personal agent skills and command wrappers.

## Layout

- Each skill lives in its own top-level folder (e.g. `analyze/SKILL.md`) — this is the source of truth.
- `.agents/skills/<name>` are symlinks into the top-level folders, so Codex and other agent tooling that expect this path keep working.
- `.claude/commands/`: optional Claude command wrappers that point at the skills as the source of truth.

## Current skills

- `analyze`
- `grill-me`
- `handoff`
- `oft`
- `retrace`
- `session-report`
- `share`
