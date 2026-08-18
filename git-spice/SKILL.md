---
name: git-spice
description: Manage stacked branches with the `gs` (git-spice) CLI. Use whenever the user mentions a "stack", asks to branch off the current branch, push/submit a branch, sync with master, or rebase/restack a stack. Distinct from Mergify's `stack` command. Auto-trigger on the words "stack", "submit", "restack", "branch off", "sync" when the current repo is a git-spice repo.
user-invocable: true
---

# git-spice (`gs`) workflow

`gs` is the git-spice CLI (https://abhinav.github.io/git-spice/cli/reference/) used to manage stacked branches and stacked PRs. The user has `gs` aliased to `git spice`, and uses the short compound aliases heavily.

> Not to be confused with the `mergify stack` command — that is unrelated. When the user says "stack" inside this repo's workflow, they mean git-spice.

## When this skill applies

Trigger this skill whenever any of these are true:

- The user says "stack", "stacked PR", "submit the stack", "restack", "the stack is broken", "sync the stack", etc.
- The user asks for a new branch *off the current branch* (a new branch on top of the current one is almost always a stack continuation).
- The user asks to "push" or "submit" a branch while the current branch is tracked by git-spice.
- The user asks to rebase a branch on master / trunk and the branch is tracked by git-spice.

Before doing anything: run `gs ls` (alias for `gs log short`) to see the current stack. If the command errors with "not a git-spice repository", this skill does not apply — fall back to plain git.

## Command cheat sheet

The user's most-used aliases (and the long forms they expand to):

| Alias  | Long form                       | Purpose |
|--------|---------------------------------|---------|
| `gs ss`    | `gs stack submit`           | Push + create/update CRs for every branch in the stack |
| `gs uss`   | `gs upstack submit`         | Submit current branch + everything above it |
| `gs rs`    | `gs repo sync`              | Pull trunk, delete merged branches |
| `gs sr`    | `gs stack restack`          | Rebase the whole stack onto its bases |
| `gs usr`   | `gs upstack restack`        | Rebase current branch + upstack |
| `gs br`    | `gs branch restack`         | Rebase just the current branch onto its base |
| `gs uso`   | `gs upstack onto <target>`  | Move current branch + upstack onto a different base |
| `gs bon`   | `gs branch onto <target>`   | Move just the current branch onto a different base (leaves upstack on the old base) |
| `gs btr`   | `gs branch track`           | Start tracking a branch in the stack |
| `gs buntr` | `gs branch untrack`         | Stop tracking a branch |
| `gs bfo`   | `gs branch fold`            | Merge the current branch into its base (collapse one level) |
| `gs bco`   | `gs branch checkout`        | Pick a branch in the stack |
| `gs bc`    | `gs branch create <name>`   | Create a new branch on top of the current one (stack continuation) |
| `gs ls`    | `gs log short`              | Show the current stack |
| `gs ll`    | `gs log long`               | Show stack with commits |
| `gs u` / `gs d` / `gs U` / `gs D` | navigation | up / down / top / bottom of stack |
| `gs rbc`   | `gs rebase continue`        | Continue a git-spice-orchestrated rebase/restack after resolving a conflict |
| `gs rba`   | `gs rebase abort`           | Abort a git-spice-orchestrated rebase/restack |

**Aliases are derived, not arbitrary** — `gs --help` states the rule directly: combine the first letter of each word in the command path (`gs bc` = `branch create`, `gs cc` = `commit create`, `gs rbc` = `rebase continue`). If an alias shows up that isn't in the table above, don't guess or ask the user what it means — run `gs --help` (lists every command group with its own short letter, e.g. `rebase (rb) continue (c)`) and decode it from there.

Always pass `--no-prompt` to anything that might prompt unless an interactive editor is genuinely needed. The user does NOT want to be dropped into an editor mid-task.

## Standard workflows

### 1. Detect stack context

When the user mentions stacks, or you are about to push/branch/rebase, first inspect state:

```bash
gs ls 2>&1                            # current stack with current branch marked
git branch --show-current             # current branch
gs ll 2>&1 | head -40                 # commits per branch if more detail needed
```

From `gs ls` you can tell:
- Whether the current branch is tracked. (If it isn't, `gs ls` shows some *other* branch's stack, not yours — a tracked branch off `master` won't appear until you `gs btr --base=<base>` it.)
- Which branch is the base of the current one.
- Whether the stack is out of date with trunk (look for the `(needs restack)` marker).

Also read the repo's git-spice config once — it changes `gs` behaviour and what you must NOT re-specify:

```bash
git config --get-regexp '^spice\.' 2>&1   # prefix, draft default, assignees, PR template
```

Keys that matter: `spice.branchCreate.prefix` (auto-prepended to new branch names — see §2), `spice.submit.draft` (PRs default to draft), `spice.submit.assignees`, `spice.submit.template` (PR body template).

### 2. Create a new branch on top of the stack

When the user asks for "a new branch off this one" or "a branch on top of X", they want a stack continuation, **not** `git checkout -b`. Use:

```bash
gs bc <branch-name>                    # creates branch on top of current, commits staged changes
gs bc -m "WIP: ..." <branch-name>      # with a commit message
gs bc --no-commit <branch-name>        # no commit (will create empty commit if nothing staged)
```

If the user wants the new branch *below* or *inserted into* the stack, use `--below` or `--insert`. If unsure which, ask once.

**Caveat — branch-name prefix.** If `spice.branchCreate.prefix` is set (this repo uses `amit/`), `gs bc` *prepends it automatically*. Pass only the suffix: `gs bc 2026-05-26-foo` → `amit/2026-05-26-foo`. Passing the full `amit/2026-05-26-foo` produces a doubled `amit/amit/...`. If you double it by accident, fix with `gs branch rename <correct-suffix>` (also takes just the suffix).

### 3. Submitting / pushing the stack

**Never use `git push` for a stack-tracked branch.** Use git-spice instead.

**Prefer `gs ss` (stack submit) over `gs branch submit` whenever the whole stack is yours and clean.** Only `gs ss`/`gs uss` (stack-aware submits) post and keep updated the **stack-navigation comment** on every PR in the stack — a checklist linking all the PRs with `◀` marking which one you're looking at, e.g.:

> This change is part of the following stack:
> - #56924
>     - #57216 ◀

`gs branch submit` submits in isolation and never writes this comment, even if the branch is part of a tracked stack — reviewers landing on a mid-stack PR lose the links to the rest. See https://github.com/PSPDFKit/PSPDFKit/pull/57216#issuecomment-5314014804 for a real example.

**That said, pick the scope deliberately — this bit me on first use:**

- `gs branch submit` — submit **only the current branch**, no navigation comment. Use this when the branches *below* already have their own PRs (especially PRs created outside git-spice), or when any lower branch shows `(needs restack)` (which would make `gs ss` refuse outright).
- `gs ss` (`gs stack submit`) — submit the **whole stack** and write/refresh the navigation comment on each PR. Two sharp edges:
  - It **refuses entirely** if *any* branch in the stack shows `(needs restack)` — `FTL gs: refusing to submit outdated branch`. It will not just submit the clean branches; you'd have to restack the offending lower branch first (which force-pushes that branch's PR).
  - For lower branches it **adopts** any existing PR — including ones created outside git-spice — and may modify it (add/refresh the navigation comment, change base, force-push if restacked). Run `gh pr list` first so you know what you'd be disturbing.

  **Do not blindly default to `gs ss`** when the ask is "make a PR for this new top branch" and the branches below are someone else's / not-restacked — use `gs branch submit` there and say so.

**Workflow for a new branch on top of your own already-submitted stack:** `gs branch submit` to create the PR quickly is fine, but follow up with one `gs ss` (or `gs uss` if a lower branch isn't yours to touch) afterward so the navigation comment gets added across the stack — don't leave it on `gs branch submit` alone as the final step.

```bash
gs branch submit --fill --no-prompt   # create/update PR for just this branch, non-interactive
gs branch submit --dry-run            # preview (prints "WOULD create a CR for ...")
gs ss --dry-run                        # preview whole-stack submit (also surfaces needs-restack refusals)
gs ss -u                               # update existing CRs only, don't create new ones
gs uss                                 # current branch + above only (useful when bottom is already merged)
```

**Always set a meaningful PR title and body — git-spice does NOT write a description.** `--fill` just copies the commit: first line → title, rest → body. That is rarely a good PR description. After submitting, edit it:

```bash
gh pr edit <num> --title "..." --body "$(cat <<'EOF'
## What
<one-paragraph summary of the user-visible change>
## Why / root cause
<the actual cause, not the symptom>
## Testing
<how it was verified — tests added, manual repro, etc.>
EOF
)"
```

If `spice.submit.template` is configured, fill *that* template's sections rather than dumping the raw commit message. git-spice applies `spice.submit.draft` and `spice.submit.assignees` from config automatically, but it never adds **labels** or other repo-required metadata — add those yourself (`gh pr edit --add-label ...`) and check the repo's own AGENTS/CLAUDE.md for PR conventions (title prefix, draft, labels).

### 4. Sync with trunk

`gs rs` pulls trunk, prunes merged branches, and (with `--restack`) restacks the current stack.

```bash
gs rs                # safe baseline
gs rs --restack      # follow with a restack — only run if you're sure no interactive rebase is needed
```

After `gs rs`, if the stack still has branches whose base was merged, those branches will have been re-pointed onto trunk automatically. Run `gs ls` to confirm.

### 5. Restacking (rebasing the stack onto its updated base)

`gs sr` / `gs usr` / `gs br` invoke `git rebase` under the hood. When the rebase conflicts, gs drops the user into an interactive resolution flow — which means **`gs sr` can pause and wait for human input**. The user does not want this in agent flows.

**Default approach (auto-rebase via raw git):**

1. Read the stack: `gs ls`
2. For each branch from the bottom up:
   - Identify its tracked base via `gs ll` (the line below the branch in the stack) or by checking `git config --get branch.<name>.gs-spice-base` if needed.
   - Compute the *old* base SHA. The tracked base name is known; the old SHA is the merge-base between the branch and the current base: `git merge-base <branch> <base>`.
   - If the base has moved (its tip is not the merge-base), rebase:
     ```bash
     git checkout <branch>
     git rebase --onto <base> <old-base-sha> <branch>
     ```
     This replays only the branch's own commits onto the new base, dropping any merge commits from the old base.
3. After each branch succeeds, the next branch up will have a new "old base" (this branch's new tip). Repeat.
4. When all branches are clean, run `gs sr --no-prompt` once to let git-spice confirm everything is in sync (this should be a no-op on a clean tree). If gs still wants a rebase, fall back to `gs br --no-prompt` per branch.

**If a `git rebase` step conflicts**, stop and tell the user — do not try to resolve conflicts blindly. They can resolve, then you continue with `git rebase --continue` and the rest of the walk — plain git is correct here because *you* started this as a plain git rebase, not git-spice.

**This is a different situation from a conflict raised by `gs sr`/`gs br`/`gs usr` themselves.** Those commands can orchestrate a rebase across *multiple* branches in one call; if one of them stops on a conflict, resolve it and continue with `gs rbc` (`gs rebase continue`), not `git rebase --continue` — the plain-git form only finishes the current branch's rebase and leaves git-spice's multi-branch sequence stalled. `gs rba` (`gs rebase abort`) bails out of the whole sequence. `git status` will say "no rebase in progress" once the underlying git rebase is done even if git-spice's orchestration isn't — don't take that as confirmation the restack fully completed; run `gs ls` to check for lingering `(needs restack)` markers instead.

**Why this works for the "base updated with master via a merge commit, not a rebase" case:** `git rebase --onto <new-base> <old-base-sha>` only takes commits *after* `<old-base-sha>` on the current branch, so the merge commit from master is dropped naturally — only the branch's actual work is replayed.

**Why this works for the "stack not rebased, `gs sr` refuses" case:** by walking the stack bottom-up with explicit `--onto` rebases, every branch is realigned without git-spice needing to figure out the topology first. Once branches are clean, `gs sr` becomes a no-op and won't refuse.

### 6. Moving a branch in the stack

When the user wants to reparent the current branch (e.g., the branch below got merged or split):

```bash
gs bon <new-base>     # move just this branch onto <new-base>, leave upstack where it was
gs uso <new-base>     # move this branch and everything above it onto <new-base>
```

These both call `git rebase --onto` internally. Same conflict caveat as restack — if it stops on a conflict, surface it to the user.

### 7. Folding / squashing within the stack

- `gs bfo` (`branch fold`): merge current branch *into its base*, collapsing one level. Useful when the user says "this branch should just be part of the one below".
- `gs branch squash`: squash all commits in the current branch into one.

### 8. Tracking / untracking

If the user has a branch that git-spice doesn't know about (e.g., created with `git checkout -b`):

```bash
gs btr                            # track current branch (will prompt for base — supply with --base)
gs btr --base=<branch>            # track with explicit base, no prompt
gs ds tr                          # track everything in the chain below
gs buntr                          # stop tracking
```

## Rules / Guardrails

- **Never `git push` a tracked branch** — always go through `gs ss` / `gs uss` / `gs branch submit`.
- **Never start an interactive rebase via `gs sr` / `gs usr` / `gs br` when conflicts are possible.** Walk the stack manually with `git rebase --onto` as described above. Only run `gs sr --no-prompt` once the tree is already clean (as a confirmation pass).
- **Never disable hooks or signing** (per global CLAUDE.md). `gs ss` respects `--no-verify`, do not pass it unless the user asks.
- If the current repo is not git-spice initialized (`gs ls` errors), do not try to "fix" it — just use plain git and let the user know.
- Do not confuse with `mergify stack` — that's a different tool. If the user invokes via `/mergify-stack`, defer to the mergify-stack skill.
- When something fails because the stack is in a weird state, run `gs ls` and `git status` and show the user, rather than guessing.

## Common one-liners the user runs

```bash
gs ls                                 # show stack
gs rs                                 # sync with trunk
gs ss --fill                          # submit stack, fill from commit messages
gs bc -a -m "msg" feature/foo         # new stacked branch with all changes
gs uss --update-only                  # update existing CRs above current
gs bon master                         # reparent current branch onto master
```
