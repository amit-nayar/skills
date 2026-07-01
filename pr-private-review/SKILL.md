---
name: pr-private-review
description: Review a GitHub pull request privately without posting comments. Use for a specific PR or to take the next PR matching a filter, then produce a plain-language report for the user.
---

# Private PR Review

Use this skill when the user wants a private report that reviews a GitHub pull request.

## Rules

- This is a **private** review. Do not post anything to GitHub — no comments, reviews, approvals, or labels.
- Do not write the report to a file. Just reply to the user with it.
- Never stash, and never modify the working tree.
- Verify `gh` auth first with `gh auth status`.
- Abort immediately (before touching any branch) if:
  - not inside a git repo, or
  - the working tree is dirty, or
  - `gh` is not authenticated.
- If the user does not specify a PR, pick a random one matching the filter below.

## Repo safety checks

Abort unless all are true:

- Inside a git repo (`git rev-parse --is-inside-work-tree`).
- `git status --porcelain` is empty.

Before checking out the PR, record the current branch so it can be restored afterward:

```bash
git rev-parse --abbrev-ref HEAD
```

## Resolve the PR

If the user gave a PR number or URL, use that.

Otherwise list candidates and pick one at random:

```bash
gh pr list --search "is:open is:pr review-requested:@me" --limit 20 --json number,title,author,updatedAt,reviewDecision,url
```

Fetch the selected PR details:

```bash
gh pr view <number> --json number,title,body,author,baseRefName,headRefName,headRefOid,url,files,commits,reviewDecision
```

## Check out the PR locally

```bash
gh pr checkout <number>
```

After checkout, confirm the working tree is still clean.

## Read and understand the change

Read enough to understand the change and its motivation properly:

1. Read the PR description.
2. Read any linked Jira issues. Search the PR title, body, and branch name for Jira keys like `ABC-123`. For each unique key found, fetch the issue (see the Jira API section of the global `~/.claude/CLAUDE.md` — use the `api.atlassian.com` gateway with the cloud ID and `$JIRA_API_TOKEN`), and read its comments when they seem relevant.
   - If the PR references a Jira issue, reading that issue is **required**. Do not continue without it.
   - If a Jira fetch fails because of authentication, abort the review immediately and tell the user to fix Jira auth rather than continuing with a partial review.
   - If the PR references no Jira issue, skip this step — a missing Jira reference is not a reason to abort.
3. Read the diff:
   ```bash
   gh pr diff <number>
   ```
4. Do not stop at the diff alone when more context is needed. Read the changed files with the Read tool. Read nearby code, tests, READMEs, changelog entries, and docs as needed.

In general there is no need to run tests locally because CI will run them.

## Restore state

When the review is complete, return the checkout to the branch recorded earlier:

```bash
git checkout <original-branch>
```

## Review goals

The goal is for the user to understand the change and its potential risks.

Respond to the user with a report with these sections:

1. **Plain-language summary**
   - Explain what the PR does in simple terms.
   - Focus on the main points, not every file.
   - Avoid frontend/backend jargon. The user has a strong background as an iOS developer and knows Swift, Rust, C, Objective-C, and computer science fundamentals — but has very limited knowledge of frontend/web and backend/server development, including infrastructure.
2. **Motivation and business impact**
   - Why it matters or does not matter.
   - What customer, product, or team impact it has.
   - What prompted the work — e.g. customer report, internal QA.
3. **Matches the PR description?**
   - Say whether the implementation matches the description.
   - Call out promised things that do not seem implemented.
   - Do **not** mention extra implemented work that looks fine but was omitted from the description.
4. **Does it solve the real problem?**
   - Judge whether the approach fixes the underlying issue.
5. **Alternative approaches**
   - Propose 1 or 2 different ways to solve the underlying problem.
   - Think beyond the current implementation.
   - Give pros and cons relative to what was done.
6. **Maintenance burden**
   - Say whether this creates long-term complexity, special cases, or ongoing cost.
7. **User-facing text and branding**
   - If public text changed, inspect the exact wording carefully.
   - Check wording, product names, branding, and clarity.
   - If you're unsure on correct terms, highlight the terms used so the user can check them.
8. **Implementation flaws / risks**
   - Point out bugs, omissions, weak tests, risky assumptions, regressions, or confusing structure.

## Output style

- Be direct about uncertainty. This report will only be seen by the user, not the author of the PR, so there is no need to hold back on criticism.
- You're writing a technical report. It should have a neutral tone.
- Use simple language first, technical detail second.
- Distinguish clearly between facts from the PR and your own judgement.
