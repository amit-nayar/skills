#!/usr/bin/env python3
"""Collect my open PRs, unfinished local branches and Linear state as JSON.

Read-only. Usage: gather.py [--stale-days N]
Needs `gh` auth and LINEAR_API_KEY (source ~/.zprofile first).
"""
import json, os, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "dev" / "nutrient"
EMAIL = "amit@nutrient.io"
NOW = datetime.now(timezone.utc)
# Repos whose branches/PRs are not "my work" for this report (e.g. retired).
SKIP_REPOS = {"PSPDFKit/PSPDFKit-Website"}


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def age_days(iso):
    if not iso:
        return None
    return (NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def pr_detail(pr):
    repo, n = pr["repository"]["nameWithOwner"], pr["number"]
    raw = run(["gh", "pr", "view", str(n), "-R", repo, "--json",
               "headRefName,baseRefName,reviewDecision,mergeable,mergeStateStatus,"
               "latestReviews,statusCheckRollup,comments,reviews"])
    d = json.loads(raw) if raw else {}
    checks = d.get("statusCheckRollup") or []
    failed = [c.get("name") or c.get("context") for c in checks
              if c.get("conclusion") == "FAILURE" or c.get("state") == "FAILURE"]
    pending = sum(1 for c in checks if c.get("status") in ("IN_PROGRESS", "QUEUED")
                  or c.get("state") == "PENDING")
    humans = [r["author"]["login"] for r in d.get("latestReviews", [])
              if r["author"]["login"] not in ("nutrient-code-reviewer", "copilot-pull-request-reviewer",
                                              "linear-code", "mergify")]
    return {
        "repo": repo, "number": n, "title": pr["title"], "url": pr["url"],
        "draft": pr["isDraft"], "branch": d.get("headRefName"), "base": d.get("baseRefName"),
        "review": d.get("reviewDecision") or "", "human_reviewers": humans,
        "mergeable": d.get("mergeable"), "merge_state": d.get("mergeStateStatus"),
        "failed_checks": failed, "pending_checks": pending,
        "idle_days": age_days(pr["updatedAt"]),
    }


def repo_dirs():
    return sorted(p for p in ROOT.iterdir() if (p / ".git").exists())


def local_branches(d):
    """Branches in one clone: name, checked-out, dirty, last commit, upstream state."""
    default = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], d).removeprefix("origin/") or "master"
    head = run(["git", "branch", "--show-current"], d)
    dirty = len(run(["git", "status", "--porcelain"], d).splitlines())
    out = []
    fmt = "%(refname:short)|%(upstream:track)|%(upstream)|%(authoremail)|%(committerdate:iso-strict)"
    for line in run(["git", "for-each-ref", f"--format={fmt}", "refs/heads"], d).splitlines():
        name, track, upstream, author, date = line.split("|", 4)
        if name in (default, "main", "master"):
            continue
        ahead = run(["git", "rev-list", "--count", f"origin/{default}..{name}"], d)
        out.append({"branch": name, "mine": EMAIL in author, "gone": "gone" in track,
                    "has_upstream": bool(upstream), "unpushed": "ahead" in track,
                    "ahead_of_default": int(ahead or 0), "idle_days": age_days(date),
                    "checked_out": name == head})
    return {"clone": d.name, "head": head or "(detached)", "dirty_files": dirty, "branches": out}


def linear():
    key = os.environ.get("LINEAR_API_KEY")
    if not key:
        return {"error": "LINEAR_API_KEY not set"}
    q = """{ viewer { assignedIssues(first:100, filter:{state:{type:{in:["started","unstarted"]}}}) {
      nodes { identifier title url updatedAt state{name type}
        attachments(first:10){nodes{url sourceType}} } } }
      projects(first:50, filter:{lead:{isMe:{eq:true}}}) { nodes { name url health
        status{type} projectUpdates(first:1){nodes{createdAt}} } } }"""
    req = urllib.request.Request("https://api.linear.app/graphql", json.dumps({"query": q}).encode(),
                                 {"Authorization": key, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=30))["data"]
    issues = []
    for i in d["viewer"]["assignedIssues"]["nodes"]:
        prs = sorted({a["url"] for a in i["attachments"]["nodes"]
                      if a["sourceType"] == "github" and "/pull/" in a["url"]})
        issues.append({"id": i["identifier"], "title": i["title"], "url": i["url"],
                       "state": i["state"]["name"], "type": i["state"]["type"],
                       "idle_days": age_days(i["updatedAt"]), "pr_urls": prs})
    projects = []
    for p in d["projects"]["nodes"]:
        if p["status"]["type"] in ("completed", "canceled"):
            continue
        last = p["projectUpdates"]["nodes"]
        projects.append({"name": p["name"], "url": p["url"], "health": p["health"],
                         "days_since_update": age_days(last[0]["createdAt"]) if last else None})
    return {"issues": issues, "projects": projects}


def main():
    prs_raw = run(["gh", "search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
                   "--json", "number,title,repository,isDraft,url,updatedAt"])
    prs_raw = [p for p in json.loads(prs_raw or "[]") if p["repository"]["nameWithOwner"] not in SKIP_REPOS]
    with ThreadPoolExecutor(8) as ex:
        prs = list(ex.map(pr_detail, prs_raw))
        clones = list(ex.map(local_branches, repo_dirs()))
    pr_branches = {p["branch"] for p in prs}
    # Branches with no open PR, mine, ahead of default, not obviously merged (upstream gone).
    orphans = [{"clone": c["clone"], **b} for c in clones for b in c["branches"]
               if b["mine"] and b["ahead_of_default"] > 0 and not b["gone"]
               and b["branch"] not in pr_branches]
    for p in prs:
        p["clones"] = [{"clone": c["clone"], "checked_out": b["checked_out"]}
                       for c in clones for b in c["branches"] if b["branch"] == p["branch"]]
    json.dump({"prs": prs,
               "clones": [{k: c[k] for k in ("clone", "head", "dirty_files")} for c in clones
                          if c["dirty_files"]],
               "branches_without_pr": orphans, "linear": linear()},
              sys.stdout, indent=1)


if __name__ == "__main__":
    main()
