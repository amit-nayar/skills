---
name: address-review
description: Address PR review feedback end to end from a GitHub PR, review, or comment URL. Finds where the PR branch lives locally (any monorepo/website clone or worktree under ~/dev), saves the current state of that checkout, makes the fixes, commits, pushes, replies to the comments, then restores the checkout exactly as it was. Use when the user says "address review", "fix review comments", "address this comment" with a github.com pull request link.
---

# Address PR Review

The user gives a URL like:

- `https://github.com/OWNER/REPO/pull/N#pullrequestreview-ID` — one review (its body + inline comments)
- `https://github.com/OWNER/REPO/pull/N#discussion_rID` — one inline comment thread
- `https://github.com/OWNER/REPO/pull/N#issuecomment-ID` — one top-level comment
- `https://github.com/OWNER/REPO/pull/N` — all **unresolved** review threads

They don't know which local clone has the branch. Find it, do the work there, and leave
that checkout exactly as you found it.

## 1. Read the PR and the feedback

```bash
gh pr view N -R OWNER/REPO --json headRefName,headRefOid,isCrossRepository,state,title,url
```

Stop if the PR is merged/closed or `isCrossRepository` is true (fork — can't push).

Fetch only the feedback the URL points to:

| URL fragment | Fetch |
| --- | --- |
| `pullrequestreview-ID` | `gh api repos/O/R/pulls/N/reviews/ID` (body) and `gh api repos/O/R/pulls/N/reviews/ID/comments --paginate` |
| `discussion_rID` | Fetch the comment with `gh api repos/O/R/pulls/comments/ID`. If it has `in_reply_to_id`, use that value as the thread's top-level comment ID; otherwise use `ID`. Fetch the full comments list with `gh api repos/O/R/pulls/N/comments --paginate` and collect the top-level comment plus comments whose `in_reply_to_id` equals that top-level ID. |
| `issuecomment-ID` | `gh api repos/O/R/issues/comments/ID` |
| none | GraphQL `reviewThreads(first:100){nodes{isResolved comments(first:50){nodes{databaseId path line body author{login}}}}}`, keep `isResolved == false` |

For a review, also check whether any of its comments are replies in an existing thread
(`in_reply_to_id`) and read that thread for context. Skip comments that are already
resolved or already answered by the PR author.

## 2. Find the local checkout

```bash
~/.claude/skills/address-review/find-pr-checkout.sh OWNER/REPO <headRefName>
```

(For Codex the same script is under `~/.agents/skills/address-review/`.) It scans
`~/dev/nutrient`, `~/dev/me`, `~/dev/others` — every clone whose `origin` is that repo, and
all their worktrees — and prints TSV, best candidate first:

```
<rank> <path> <state> <current-branch> <dirty|clean>
1  …/monorepo2           checked-out  <branch>  dirty   # branch is checked out here
2  …/monorepo            local        other     clean   # branch exists locally
3  …/monorepo3           clone        master    dirty   # repo only; branch from origin
```

Pick the first line. Within the same rank, clean checkouts sort before dirty ones. If
nothing matches, say so and ask where the repo lives rather than cloning it.

Pass extra roots as further args if the user mentions another location.

## 3. Save the current state

All git commands from here use `git -C <path>`. Record before touching anything:

```bash
ORIG_REF=$(git -C "$P" symbolic-ref --quiet --short HEAD || git -C "$P" rev-parse HEAD)
```

If the checkout is dirty, stash including untracked files, with a recognisable message:

```bash
git -C "$P" stash push -u -m "address-review: PR #N autostash from $ORIG_REF"
STASH=$(git -C "$P" rev-parse stash@{0})
```

Write `ORIG_REF`, `STASH` (sha) and the path into a note
(`$(git -C "$P" rev-parse --git-dir)/address-review-state`) so a crashed session can still
be recovered by hand. Tell the user in one line what you saved.

Rank 1 + dirty: the dirty changes are on the PR branch itself. Still stash them — they are
the user's unfinished work, not part of this fix — and restore them on the branch afterwards.

## 4. Get the branch up to date

```bash
git -C "$P" fetch origin <branch>
git -C "$P" checkout <branch>                 # rank 3: git checkout -b <branch> --track origin/<branch>
git -C "$P" merge --ff-only origin/<branch>
```

If the local branch has commits not on origin, or `--ff-only` fails (diverged), **stop**:
restore state (step 7) and ask the user. Never force-push, never reset someone's commits.

## 5. Make the fixes

- Read each comment and the code around `path:line` at the PR head. Fix what is asked;
  don't widen scope.
- If a comment is a question, a disagreement, or ambiguous, don't guess a code change —
  draft a reply instead and flag it to the user.
- Follow the repo's CLAUDE.md/AGENTS.md. Run the narrowest relevant check (formatter,
  the affected module's lint/unit test) when it is cheap; if it's not practical, say so.
- Commit message style: match `git log --oneline -10` on the branch. One commit per
  review is fine; split only if the fixes are unrelated. Attempt signing for each commit
  first, including amendments. If that attempt fails,
  commit unsigned with a command-scoped override and report it. Retry signing for each later
  commit. Leave repository and global signing defaults unchanged.

## 6. Push and reply

```bash
git -C "$P" push origin <branch>
```

Then reply to each comment you addressed, in the user's voice (use the `myvoice` skill
if available): short, says what changed, references the commit SHA. Questions you
couldn't answer with code get a proposed reply shown to the user first, not posted.

- Inline comment: `gh api repos/O/R/pulls/N/comments/<top-level-comment-id>/replies -f body=...`
  (reply to the thread's **top** comment id, found by following `in_reply_to_id` from a
  clicked reply).
- Review body / top-level comment: `gh pr comment N -R O/R --body ...`, quoting the
  point being answered.

Do not resolve threads — the reviewer does that.

## 7. Restore the previous state

Always run this, including after failures in steps 4–6:

```bash
git -C "$P" checkout "$ORIG_REF"
IDX=$(git -C "$P" stash list --format='%gd %H' | awk -v s="$STASH" '$2==s {print $1}')
[ -n "$IDX" ] && git -C "$P" stash pop "$IDX"
rm -f "$(git -C "$P" rev-parse --git-dir)/address-review-state"
```

(Pop by matching the saved sha, not blindly `stash@{0}` — something else may have
stashed meanwhile.) If the pop conflicts, leave the stash in place, don't drop it, and
tell the user exactly which stash entry holds their work.

Rank 1 case: `ORIG_REF` is the PR branch, now with the new commit on top; popping the
stash puts the user's in-progress edits back on it.

## 8. Report

A few lines: which checkout was used, commit SHA(s), which comments were replied to,
anything left for the user (unanswered questions, checks not run), and confirmation that
the checkout is back on `ORIG_REF` with its changes restored.
