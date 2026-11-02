#!/usr/bin/env python3
"""Make the routine fixes work-status would otherwise list, and report what was done as JSON.

Usage: act.py status.json [--dry-run]   (status.json is gather.py's output)

- Link an open PR to an assigned Linear issue that has no PR, when the PR's title or branch names
  the issue.
- Move an assigned issue to its team's Done state when every PR that names it is merged or closed,
  at least one merged, and none is open.
- Re-queue an approved PR that Mergify dequeued after a failed merge-queue build, when none of that
  build's failures look real (tests, compile, lint). Real failures are left for me.

Never queues a PR that wasn't queued before, never re-runs CI. Needs `gh` auth and LINEAR_API_KEY.
"""
import json, os, re, subprocess, sys, urllib.request

DRY = "--dry-run" in sys.argv[1:]
DONE, ERRORS = [], []


def linear(query, variables=None):
    req = urllib.request.Request(
        "https://api.linear.app/graphql", json.dumps({"query": query, "variables": variables or {}}).encode(),
        {"Authorization": os.environ["LINEAR_API_KEY"], "Content-Type": "application/json"})
    resp = json.load(urllib.request.urlopen(req, timeout=30))
    if resp.get("errors"):
        raise RuntimeError(json.dumps(resp["errors"])[:200])
    return resp["data"]


def record(action, target, url, detail):
    DONE.append({"action": action, "target": target, "url": url, "detail": detail, "dry_run": DRY})


def names(issue_id, title, branch):
    return issue_id.lower() in f"{title} {branch or ''}".lower()


def link_prs(issues, prs):
    for i in issues:
        if i["prs"]:
            continue
        for p in prs:
            if names(i["id"], p["title"], p["branch"]):
                try:
                    if not DRY:
                        linear("mutation($i:String!,$u:String!){attachmentLinkURL(issueId:$i,url:$u){success}}",
                               {"i": i["uuid"], "u": p["url"]})
                    i["prs"].append({"url": p["url"], "state": "OPEN", "for_issue": True})
                    record("linked", i["id"], i["url"], f"#{p['number']} {p['url']}")
                except Exception as e:
                    ERRORS.append(f"link {i['id']}: {e}")


def close_finished(issues):
    done_states = {}
    for i in issues:
        own = [p for p in i["prs"] if p.get("for_issue")]
        if (not own or any(p["state"] not in ("MERGED", "CLOSED") for p in own)
                or not any(p["state"] == "MERGED" for p in own)):
            continue
        try:
            if i["team_id"] not in done_states:
                nodes = linear('query($t:String!){team(id:$t){states(filter:{type:{eq:"completed"}}){nodes{id name position}}}}',
                               {"t": i["team_id"]})["team"]["states"]["nodes"]
                done_states[i["team_id"]] = min(nodes, key=lambda s: s["position"])
            state = done_states[i["team_id"]]
            if not DRY:
                linear("mutation($i:String!,$s:String!){issueUpdate(id:$i,input:{stateId:$s}){success}}",
                       {"i": i["uuid"], "s": state["id"]})
            merged = " ".join(p["url"] for p in own if p["state"] == "MERGED")
            record("moved", i["id"], i["url"], f"{i['state']} → {state['name']} ({merged} merged)")
        except Exception as e:
            ERRORS.append(f"state {i['id']}: {e}")


def requeue(prs):
    for p in prs:
        dq = p.get("dequeued")
        if (not dq or not dq["failures"] or p["review"] != "APPROVED" or p["draft"]
                or p["mergeable"] == "CONFLICTING" or p.get("unsigned_commits")):
            continue
        if any(f["kind"] == "real" for f in dq["failures"]):
            continue
        cmd = ["gh", "pr", "comment", str(p["number"]), "-R", p["repo"], "--body", "@mergifyio queue"]
        r = subprocess.run(cmd, capture_output=True, text=True) if not DRY else None
        if r and r.returncode:
            ERRORS.append(f"requeue #{p['number']}: {r.stderr.strip()[:200]}")
            continue
        kinds = ", ".join(sorted({f["kind"] for f in dq["failures"]}))
        record("requeued", f"#{p['number']}", p["url"], f"dequeued on {kinds} failures: {dq['summary_url']}")


def main():
    status = json.load(open(sys.argv[1]))
    prs = [p for p in status["prs"] if not p.get("detail_missing")]
    if status.get("linear"):
        issues = status["linear"]["issues"]
        link_prs(issues, prs)
        close_finished(issues)
    requeue(prs)
    json.dump({"done": DONE, "errors": ERRORS}, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
