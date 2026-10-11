#!/usr/bin/env python3
"""List review feedback on my open PRs (drafts included) that I haven't answered yet, as JSON.

Read-only. Usage: gather.py [--all]   (--all: include PRs outside the Nutrient GitHub orgs)

An item is pending when someone else spoke last:
- an unresolved review thread whose last comment isn't mine
- a review body (human, or a bot review that isn't just the PR summary) with no later comment of mine
- a top-level PR comment from a person or the code-review bot with no later comment of mine

Each item has a `key` that changes when the reviewer adds to it. `state.json` (next to the
routine's other state) records what earlier runs decided per key, so a point already judged
"needs Amit" is not re-investigated every night; a new reply from the reviewer makes a new key.
"""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

NUTRIENT_ORGS = {"pspdfkit", "pspdfkit-labs"}
STATE = Path.home() / "Library/Application Support/claude-routines/review-sweep-state.json"
REVIEW_BOT = "nutrient-code-reviewer"
# Bots whose comments are status noise, never review feedback.
NOISE = {"linear-code", "mergify", "pspdfkit-ci", "github-actions", "codecov", "dependabot",
         "pspdfkit-bot"}
NOW = datetime.now(timezone.utc)
ERRORS = []

PR_QUERY = """query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) {
  pullRequest(number: $n) {
    number title url isDraft isCrossRepository headRefName headRefOid baseRefName
    reviewThreads(first: 100) { nodes { id isResolved isOutdated path line
      comments(first: 50) { nodes { databaseId author { login } body createdAt url } } } }
    reviews(last: 50) { nodes { databaseId state body author { login } submittedAt url } }
    comments(last: 100) { nodes { databaseId author { login } body createdAt url } } } } }"""


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        ERRORS.append(f"{' '.join(cmd[:3])}: {(r.stderr or r.stdout).strip()[:200]}")
        return ""
    return r.stdout.strip()


def login_of(node):
    return ((node.get("author") or {}).get("login") or "ghost").removesuffix("[bot]")


def age_days(iso):
    return (NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days if iso else None


def pending_items(pr, me):
    items = []
    # Latest time I said anything top-level; a review body or comment before it counts as answered.
    my_last = max([c["createdAt"] for c in pr["comments"]["nodes"] if login_of(c) == me]
                  + [r["submittedAt"] for r in pr["reviews"]["nodes"]
                     if login_of(r) == me and r["body"].strip()] or [""])

    for t in pr["reviewThreads"]["nodes"]:
        cs = t["comments"]["nodes"]
        if t["isResolved"] or not cs or login_of(cs[-1]) == me:
            continue
        items.append({
            "kind": "thread", "key": f"thread:{cs[-1]['databaseId']}",
            "reply_to": cs[0]["databaseId"],  # replies go to the thread's top comment
            "path": t["path"], "line": t["line"], "outdated": t["isOutdated"],
            "reviewer": login_of(cs[0]), "url": cs[-1]["url"],
            "comments": [{"author": login_of(c), "body": c["body"]} for c in cs]})

    for r in pr["reviews"]["nodes"]:
        who, body = login_of(r), r["body"].strip()
        if who == me or who in NOISE or not body or (r["submittedAt"] or "") <= my_last:
            continue
        # The review bot's summary review restates the PR; its findings arrive as threads.
        if who == REVIEW_BOT and "PR Summary" in body.split("\n", 1)[0]:
            continue
        # Copilot's overview review only summarises; its findings arrive as threads.
        if who == "copilot-pull-request-reviewer" and ("ccr-overview" in body or "Pull Request Overview" in body):
            continue
        items.append({"kind": "review", "key": f"review:{r['databaseId']}", "state": r["state"],
                      "reviewer": who, "url": r["url"], "body": body})

    for c in pr["comments"]["nodes"]:
        who = login_of(c)
        if who == me or who in NOISE or c["createdAt"] <= my_last:
            continue
        items.append({"kind": "comment", "key": f"comment:{c['databaseId']}", "reviewer": who,
                      "url": c["url"], "body": c["body"]})
    return items


def pr_feedback(p, me, state):
    owner, name = p["repository"]["nameWithOwner"].split("/")
    raw = run(["gh", "api", "graphql", "-f", f"query={PR_QUERY}", "-F", f"owner={owner}",
               "-F", f"name={name}", "-F", f"n={p['number']}"])
    if not raw:
        return None
    pr = json.loads(raw)["data"]["repository"]["pullRequest"]
    repo = f"{owner}/{name}"
    items = pending_items(pr, me)
    for i in items:
        i["key"] = f"{repo}#{pr['number']}:{i['key']}"
        i["previous"] = state.get(i["key"])  # {"decision", "note", "date"} from an earlier run
    return {"repo": repo, "number": pr["number"], "title": pr["title"], "url": pr["url"],
            "draft": pr["isDraft"], "fork": pr["isCrossRepository"], "branch": pr["headRefName"],
            "head": pr["headRefOid"], "base": pr["baseRefName"], "items": items}


def main():
    include_all = "--all" in sys.argv[1:]
    me = run(["gh", "api", "user", "-q", ".login"])
    raw = run(["gh", "search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
               "--json", "number,repository"])
    prs = [p for p in json.loads(raw or "[]")
           if include_all or p["repository"]["nameWithOwner"].split("/")[0].lower() in NUTRIENT_ORGS]
    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        state = {}
    with ThreadPoolExecutor(8) as ex:
        results = [r for r in ex.map(lambda p: pr_feedback(p, me, state), prs) if r]
    # Open PRs stacked on each PR: pushing a fix to a lower PR leaves these needing a restack.
    for r in results:
        r["upstack"] = [o["url"] for o in results if o["repo"] == r["repo"] and o["base"] == r["branch"]]
    json.dump({"complete": not ERRORS and bool(me), "errors": ERRORS, "me": me,
               "prs_checked": len(results),
               "prs": [r for r in results if r["items"]]}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
