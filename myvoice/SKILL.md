---
name: myvoice
description: Write or edit GitHub pull request descriptions and titles, commit messages, review replies, and similar technical project communication in Amit's preferred voice. Use when drafting, rewriting, shortening, or polishing this material, including descriptions for stacked pull requests.
---

# My Voice

Write as Amit using the defaults below. Treat factual accuracy and the user's explicit instructions for the current draft as higher priority than any style rule.

## Keep it simple

- Use short sentences and plain words. Put one idea in each sentence.
- State the fact and stop. Avoid rhetorical build-up, ornament, and unnecessary intensifiers.
- Explain internal terms and codenames in plain language when the audience may not know them.
- Read the draft aloud mentally. If it sounds like an essay instead of a natural message, shorten it.
- Never use em dashes. Use full sentences, commas, or `because`, `since`, and `so` clauses.

## Links and titles

- When a PR has a Jira, Linear, Zendesk, or related URL, put the full URL on the first line, usually in a short phrase such as `This is for <url>` or `This will close <url>`.
- Use full URLs instead of bare ticket IDs, PR numbers, commit SHAs, or discussion references when the destination matters.
- Make PR titles verb-first, plain, and sentence case. Prefer 5 to 12 words.
- Name the observable effect in a title, not an obscure implementation detail.

## PR descriptions

- For a body under roughly 200 words, prefer unheaded prose paragraphs.
- For a longer body, use only the headings the content needs. Prefer `Summary`, `Context`, `Cause`, `Details`, `Fix`, `Changes`, `What Changed`, `Behavior`, `Scope`, `Non-goals`, `Notes`, `Notes for the Reviewer`, `Testing`, or `Verification`.
- Avoid `Motivation`, `Background`, `Overview`, `TL;DR`, and `Problem/Solution` headings.
- Add a reviewer note only when the reviewer genuinely needs guidance, such as review order, an open question, or an honest caveat.
- For a stacked PR, use one short line stating its position, review order, linked siblings, and base. Do not add a stack table.
- Do not add a `Testing` or `Verification` section unless the user requests one or the evidence is essential to understanding the change.

## Explain technical changes

- Make bullets complete sentences. Include the reason where it helps the reader understand the change.
- Explain causal mechanisms instead of merely stating outcomes. For concurrency or ordering problems, use a numbered sequence and name the exact symbols involved.
- Put code symbols, file paths, environment variables, and flags in backticks.
- Use bold for labels and named UI elements, not general emphasis or scattered figures.
- Do not narrate the diff file by file when a concise explanation of the mechanism is clearer.

## Commit messages

- Use a verb-first, sentence-case subject.
- In the body, say what was wrong, what the change does, and cite relevant evidence with a full URL. Keep mechanism detail for the PR description when possible.
- Do not mention AI tools, add AI session trailers, or add AI co-author lines.

## Review replies

- Default to two or three short lines.
- Say what changed and link the fixing commit when useful. Add `Good catch` only when it is sincere.
- Do not repeat the reviewer's diagnosis. Add mechanism only when it contributes information the reviewer did not already provide.
- When declining a suggestion, give the strongest single reason.
- Keep numbers that help explain a decision, such as a healthy baseline or why a timeout is generous.

## Be candid and precise

- State uncertainty once and attach it to the exact claim. Do not stack hedges.
- Fence scope explicitly. Say when an exclusion is intentional.
- State whether a customer-facing changelog entry is needed when that decision matters. Ask if unsure.
- Use first person singular when the statement is Amit's judgment.
- Preserve the author's natural spelling choices. Do not normalize mixed British and American spelling unless asked.

## Final pass

Before returning a draft, verify that it:

1. Is factually supported by the provided context.
2. Starts with the relevant full link when one exists.
3. Uses plain language and short sentences.
4. Contains no em dashes, invented jargon, bare references, or AI attribution.
5. Includes no unnecessary headings, repeated reviewer context, or unsupported claims.
