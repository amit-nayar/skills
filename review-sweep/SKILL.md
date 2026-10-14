---
name: review-sweep
description: Sweep all my open and draft PRs for review feedback I haven't answered, check each point is actually correct, fix and push the ones that are, reply on GitHub, and post a summary of every change to my Slack DM. Works in throwaway worktrees so no clone I'm using is touched. Runs every evening at 20:00 via launchd; run /review-sweep any time.
---

# Review sweep

Unattended version of `address-review`, across every open PR of mine at once. The reviewer is
not always right, the code-review bot least of all: **verify each point before changing code.**

**Do not end the turn until the Slack post has gone out** (or there was nothing to post, see
step 6). No background agents: a routine run that ends with one still running is killed and
reports success with nothing done. Work one PR at a time, inline.

## 1. Gather

```bash
set -a && . ~/.zprofile >/dev/null 2>&1; set +a
export PATH=/opt/homebrew/bin:$PATH   # gh lives here; without it gh "finds nothing"
python3 ~/dev/me/skills/review-sweep/scripts/gather.py > "$SCRATCH/sweep.json"   # --all for `all`
```

`SCRATCH` is the session scratchpad. The JSON lists only PRs with pending `items`, each one:
`kind` (`thread` / `review` / `comment`), `key`, `reviewer`, `url`, the text, and for threads
`path`, `line`, `outdated`, `reply_to` (the top comment id) and the whole conversation.
`previous` is what an earlier run decided for the same key (it only matches if nobody has
spoken since). `upstack` lists open PRs based on this PR's branch. If `complete` is false, say
so at the top of the post.

## 2. Triage each item

Skip without investigating: items whose `previous.decision` is `needs-amit` (list them in the
post's last line as still waiting), and PRs with `fork: true`.

For everything else, read the comment, then read the code it refers to **at the PR head**
(`git show <head>:<path>`), and decide:

| Decision | When | Action |
| --- | --- | --- |
| `fixed` | the point is right and the fix is clear, mechanical or within the PR's intent | fix, push, reply |
| `replied` | the point is wrong, already handled, or out of scope — and you can show why | reply with the evidence, no code change |
| `needs-amit` | a design choice, a question only I can answer, a fix that widens the PR's scope, or you can't establish who's right | no reply; draft one into the post |
| `skipped` | nothing to act on ("LGTM", "thanks, all addressed", an approval with no requests) | nothing |

Verification means evidence, not a reread. Trace the call path the comment claims, check the
API it says is misused, write a small throwaway test or run the script on the case it says
breaks. Bot findings are often plausible and wrong; human ones are usually right but may be
based on an older revision (`outdated: true` — check whether a later commit already did it).

Pushback (`replied`) goes on GitHub only for **bot** reviewers (`nutrient-code-reviewer`,
`copilot-pull-request-reviewer`). When a **person** is wrong, use `needs-amit` with a drafted
reply — I answer people myself.

Never push to a release branch (`release/*`, `*-stable`, the website's release-version
branches): their feedback is always `needs-amit`.

## 3. Set up a worktree (once per PR that gets a fix)

Never check out, stash or reset any clone I work in. Use a detached worktree outside `~/dev`
(so `work-status` and `cleanup-branches` never see it):

```bash
~/dev/me/skills/address-review/find-pr-checkout.sh OWNER/REPO <branch>   # first line's path = $CLONE
git -C "$CLONE" fetch origin <branch>
```

If the branch exists locally in **any** listed checkout with commits whose changes aren't on
`origin/<branch>`, I have unpushed work there: don't fix, mark the PR's items `needs-amit`
("unpushed local commits"). Use `git -C <path> cherry origin/<branch> <branch>` and count `+`
lines. A plain `rev-list origin/<branch>..<branch>` also counts the stale pre-rebase copies a
clone keeps after the branch was rebased and force-pushed elsewhere; `cherry` marks those `-`.

```bash
WT="$HOME/Library/Caches/review-sweep/<repo-name>-<number>"
git -C "$CLONE" worktree add --detach "$WT" "origin/<branch>"
```

## 4. Fix, check, commit, push

- Fix only what the comment asks. Follow the repo's AGENTS.md/CLAUDE.md files for the touched area.
- Run the narrowest cheap check that covers the change: a formatter, the touched script, one
  unit test class. A fresh worktree has no build outputs, so skip anything that needs a full
  native/SDK build and say so in the reply and the post. Never claim a check you didn't run.
- Android unit tests: run with `SKIP_NDK_BUILD=true` (as CI does). Tests that load documents
  then fail with `UnsatisfiedLinkError`, which says nothing about the change. Copy
  `android/sdk-nutrient/build/intermediates/jniTestLibs/lib/libpspdfkit.dylib` from a clone
  whose `core/` and `android/sdk-nutrient/src/main/java/com/pspdfkit/internal/jni` match the
  PR head (`git diff --stat HEAD origin/<branch> -- core/ <jni dir>` is empty). Copy it into
  the worktree; never build or change anything in that clone. If no clone matches, report
  which tests couldn't run. When a fix changes what a test asserts, also confirm the test fails
  without the fix.
- In zsh, quote `"${REF}:path"`: an unquoted `$REF:a…` is read as a history modifier.
- Commits: match `git log --oneline -10` on the branch; one commit per PR is fine, split only
  unrelated fixes. Sign first with a time limit, since the 1Password prompt may get no answer:

  ```bash
  timeout 60 git -C "$WT" commit -m "..." || git -C "$WT" -c commit.gpgsign=false commit -m "..."
  ```

  Never change the repository's or global signing config; note every unsigned commit in the post.
- Push without force: `git -C "$WT" push origin HEAD:refs/heads/<branch>`. If it's rejected
  (someone pushed meanwhile), don't rebase or force: mark the items `needs-amit` ("branch moved").
- Then remove the worktree, always, also after a failure:
  `git -C "$CLONE" worktree remove --force "$WT"`.

My local copy of the branch is now behind origin; that's expected, the next pull fast-forwards.
Don't restack `upstack` PRs either (that force-pushes): list them in the post as needing
`gs upstack restack`.

## 5. Reply on GitHub

In my voice (`myvoice` skill): short, says what changed and why, names the commit SHA. For
`replied`, give the evidence in a sentence or two. Never promise future work on my behalf
("I'll add…"); state what's missing instead. Don't resolve threads.

- Thread: `gh api repos/O/R/pulls/N/comments/<reply_to>/replies -f body=...`
- Review body or top-level comment: `gh pr comment N -R O/R --body ...`, quoting the point.

Record every decision as you go, so a crash halfway doesn't redo work tomorrow:

```bash
python3 ~/dev/me/skills/review-sweep/scripts/record.py "<key>" <fixed|replied|needs-amit|skipped> "<short note>"
```

## 6. Post the summary to my DM

Nothing to report (no `fixed`, `replied` or new `needs-amit`, `complete` true): don't post,
just print "Review sweep: nothing new on N PRs" so the routine log shows it ran.

Otherwise build the outline with the OFT builder, `## Name` sections, `- ` bullets, PR links
labelled with the number only, one line per point:

```bash
cat > "$SCRATCH/outline.md" <<'OUTLINE'
Review sweep:

## Fixed and pushed
- [#59998](https://github.com/PSPDFKit/PSPDFKit/pull/59998) blank className now filtered like the other selectors (`abc1234`, unit test run)

## Pushed back
- [#59289](…) bot said the render owner can stick in RENDERING; cancellation path resets it (`PageRenderOwner.kt:88`)

## Needs you
- [#59760](…) Michael wants the supertype list re-sorted; that changes every dump. Draft: "…"

## Follow-ups
- Restack upstack of [#59583](…): [#59971](…)
- Unsigned commits: `abc1234` on [#59998](…)
OUTLINE
USER_ID=$(curl -s https://slack.com/api/auth.test --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["user_id"])')
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" --preview
python3 ~/dev/me/skills/oft/scripts/build_message.py "$SCRATCH/outline.md" "$USER_ID" > "$SCRATCH/sweep-msg.json"
curl -s https://slack.com/api/chat.postMessage --header "Authorization: Bearer $SLACK_API_TOKEN_OFT" --header "Content-Type: application/json; charset=utf-8" --data @"$SCRATCH/sweep-msg.json"
```

`Fixed and pushed` says what changed and which check ran. `Pushed back` gives the evidence in a
few words. `Needs you` includes the drafted reply. End with one line for older `needs-amit`
items still waiting ("Still waiting on you: [#…](…) [#…](…)"). Check `"ok": true` and include
the `--preview` text in the final reply.
