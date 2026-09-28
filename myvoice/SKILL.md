---
name: myvoice
description: Write or edit GitHub pull request descriptions and titles, commit messages, review comments and replies, Slack messages, and similar technical project communication in Amit's preferred style. Use when drafting, rewriting, shortening, or polishing this material, including descriptions for stacked pull requests.
---

# My Voice

Write clear, plain technical text using the defaults below. Treat factual accuracy and the user's explicit instructions for the current draft as higher priority than any style rule.

Do not imitate Amit's personal habits, such as abbreviations, emoji, lowercase starts, catchphrases or jokes. The goal is text that is simple and easy to read, not text that pretends to be typed by him.

## Keep it simple

- Use short sentences and plain, common words. Put one idea in each sentence.
- Avoid complex sentence structure: no stacked clauses, no semicolons, no parenthetical asides inside a sentence.
- State the fact and stop. Avoid rhetorical build-up, ornament, and intensifiers such as "significantly", "robust" or "seamless".
- Explain internal terms and codenames in plain language when the audience may not know them.
- Read the draft aloud mentally. If it sounds like an essay or a press release instead of a message to a colleague, shorten it.
- Never use em dashes or en dashes. Use a full stop, a comma, or a `because`, `since` or `so` clause instead.
- Use normal capitalisation and punctuation everywhere, including Slack.
- Do not change the spelling in text the user wrote.

## Be direct and honest

- Say what was wrong, what the change does, and what is not done yet.
- Keep honest caveats, such as "I haven't been able to reproduce this" or "This is a workaround until we find the cause". Put the caveat next to the claim it qualifies, once. Don't sprinkle "might", "potentially" or "could" through every sentence.
- Fence scope explicitly. Say when an exclusion is intentional or when something is left for a follow-up PR.
- State whether a customer-facing changelog entry is needed when that decision matters. Ask if unsure.
- Use "I" for Amit's own actions and judgments, and "we" for the team, the SDK and shared plans.

## Links and titles

- When a PR has a Linear, Zendesk, or related URL, put the full URL on the first line, usually in a short phrase such as `This is for <url>` or `Fixes <url>`.
- Use full URLs instead of bare ticket IDs, PR numbers, commit SHAs, or discussion references when the destination matters.
- Make PR titles plain and sentence case, usually verb-first. Prefer 3 to 10 words. Keep any team prefix the repo already uses, such as `[AND]`.
- Name the observable effect in a title, not an obscure implementation detail.

## PR descriptions

- Default to one to three short paragraphs with no headings.
- Answer, in this order: what was wrong or why the change is needed, what the change does, and anything the reviewer should know (caveats, follow-ups, what isn't done yet).
- Use a short bullet list when the PR does several separate things. Use a `- [x]` checklist for release-style PRs that track changelog, docs and migration guide steps.
- Only add headings for a long body that really needs them. Use `Context`, `Cause`, `Fix`, `Changes`, `Notes`, or `Notes for the Reviewer`. Never use `Summary`, `Motivation`, `Background`, `Overview`, `TL;DR`, or `Problem/Solution`.
- For a stacked PR, use one short line stating its position, review order, linked siblings, and base. Do not add a stack table.
- Do not add a `Testing`, `Test plan` or `Verification` section unless the user requests one. When testing status matters, say it in one sentence in the body.

## Explain technical changes

- Explain causal mechanisms instead of merely stating outcomes. For concurrency or ordering problems, use a numbered sequence and name the exact symbols involved.
- Put code symbols, file paths, environment variables, and flags in backticks.
- Use bold sparingly, for labels and named UI elements, not for emphasis.
- Do not narrate the diff file by file when a concise explanation of the mechanism is clearer. Avoid "Before / After" code blocks unless the snippet is the clearest explanation.

## Commit messages

- Use a short, sentence-case subject, usually verb-first.
- In the body, say what was wrong, what the change does, and cite relevant evidence with a full URL. Keep mechanism detail for the PR description when possible.
- Do not mention AI tools, add AI session trailers, or add AI co-author lines.

## Review comments on other people's PRs

- Be brief. One or two sentences per comment.
- A question often works better than a directive: "Is this meant to be cleaned up later?" Directives are fine for clear rules: "This needs API docs if it's public."
- Prefix optional style points with `Nit:`. Use a GitHub ```` ```suggestion ```` block when the fix is a one-line change.
- For new public API, ask how a customer would actually use it.
- If a point needs more than a few sentences, suggest a call instead of writing a long comment.

## Replies to review comments

- Default to one to three short lines.
- Say what changed and link the fixing commit when useful. "Done" or "Fixed in <link>" is enough.
- Do not repeat the reviewer's diagnosis. Add mechanism only when it contributes information the reviewer did not already provide.
- When declining a suggestion, give the strongest single reason.
- Keep numbers that help explain a decision, such as a healthy baseline or why a timeout is generous.

## Slack

Only apply this when the user asks for a Slack message.

- Start with the point. No greeting unless it's an announcement.
- Keep it to a few short sentences. Put a request in a clear question: "Can you take a look when you have time?"
- For cross-team or planning messages, include dates or versions and end with a check-in question such as "Does that work for you?".
- No emoji or abbreviations unless the user includes them.

## Final pass

Before returning a draft, verify that it:

1. Is factually supported by the provided context.
2. Starts with the relevant full link when one exists.
3. Uses short sentences and plain words, with no complex sentence structure.
4. Contains no em or en dashes, invented jargon, bare references, or AI attribution.
5. Includes no unnecessary headings, `Summary` or test sections, repeated reviewer context, or unsupported claims.
6. Does not imitate personal quirks such as abbreviations, emoji, lowercase starts or jokes.
