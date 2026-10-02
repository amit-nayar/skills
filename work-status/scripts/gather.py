#!/usr/bin/env python3
"""Collect my open PRs, unfinished local branches and Linear state as JSON.

Read-only. Usage: gather.py
Needs `gh` auth and LINEAR_API_KEY (source ~/.zprofile first). Any source that fails is listed
in `errors` and `complete` is false, so a failure never looks like a quiet week.
"""
import json, os, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "dev" / "nutrient"
# Commits are authored with the personal address in most clones; match both.
EMAILS = {"amit@nutrient.io", "amit.nyr@gmail.com"}
NOW = datetime.now(timezone.utc)
# Repos whose branches/PRs are not "my work" for this report (e.g. retired).
SKIP_REPOS = {"pspdfkit/pspdfkit-website"}
BOTS = {"nutrient-code-reviewer", "copilot-pull-request-reviewer", "linear-code", "mergify"}
FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
# Release branches carry cherry-picks, so they are always "ahead" but never unfinished work.
RELEASE = re.compile(r"(-stable$|^release[/-])")
ERRORS = []


def run(cmd, cwd=None, expect_fail=False):
    """stdout on success; on failure "" and, unless expected, an entry in ERRORS."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode == 0:
        return r.stdout.strip()
    if not expect_fail:
        where = f" (in {Path(cwd).name})" if cwd else ""
        ERRORS.append(f"{' '.join(cmd[:3])}{where}: {(r.stderr or r.stdout).strip()[:200]}")
    return ""


def age_days(iso):
    if not iso:
        return None
    return (NOW - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days


def key(repo, branch):
    return (repo.lower(), branch)


def pr_detail(pr):
    repo, n = pr["repository"]["nameWithOwner"], pr["number"]
    raw = run(["gh", "pr", "view", str(n), "-R", repo, "--json",
               "headRefName,baseRefName,reviewDecision,mergeable,mergeStateStatus,"
               "latestReviews,statusCheckRollup"])
    d = json.loads(raw) if raw else {}
    checks = d.get("statusCheckRollup") or []
    failed = [c.get("name") or c.get("context") for c in checks
              if c.get("conclusion") in FAILED or c.get("state") in FAILED]
    pending = sum(1 for c in checks if c.get("status") in ("IN_PROGRESS", "QUEUED", "PENDING")
                  or c.get("state") in ("PENDING", "EXPECTED"))
    humans = [r["author"]["login"] for r in d.get("latestReviews") or []
              if r["author"]["login"] not in BOTS]
    return {
        "repo": repo, "number": n, "title": pr["title"], "url": pr["url"],
        "draft": pr["isDraft"], "branch": d.get("headRefName"), "base": d.get("baseRefName"),
        "review": d.get("reviewDecision") or "", "human_reviewers": humans,
        "mergeable": d.get("mergeable"), "merge_state": d.get("mergeStateStatus"),
        "failed_checks": failed, "pending_checks": pending,
        "idle_days": age_days(pr["updatedAt"]),
        # Review/CI fields are blank when this is true; don't classify the PR from them.
        "detail_missing": not d,
    }


def closed_prs(login):
    """My recently closed/merged PRs keyed by (repo, branch) -> newest {url, state}."""
    q = """query($q: String!) { search(query: $q, type: ISSUE, first: 100) { nodes {
      ... on PullRequest { url state headRefName headRefOid closedAt repository { nameWithOwner } } } } }"""
    raw = run(["gh", "api", "graphql", "-f", f"query={q}",
               "-f", f"q=is:pr author:{login} is:closed sort:updated-desc"])
    out = {}
    for p in (json.loads(raw)["data"]["search"]["nodes"] if raw else []):
        k = key(p["repository"]["nameWithOwner"], p["headRefName"])
        if k not in out or (p["closedAt"] or "") > (out[k]["closed_at"] or ""):
            out[k] = {"url": p["url"], "state": p["state"], "closed_at": p["closedAt"],
                      "head": p["headRefOid"]}
    return out


def pr_for_branch(repo, branch):
    """Newest PR (any state) for a head branch, for branches the closed-PR search missed."""
    raw = run(["gh", "pr", "list", "-R", repo, "--head", branch, "--state", "all", "--limit", "1",
               "--json", "url,state,closedAt,headRefOid"])
    prs = json.loads(raw) if raw else []
    return ({"url": prs[0]["url"], "state": prs[0]["state"], "closed_at": prs[0]["closedAt"],
             "head": prs[0]["headRefOid"]} if prs else None)


def pr_state(url):
    raw = run(["gh", "pr", "view", url, "--json", "state"])
    return json.loads(raw)["state"] if raw else None


def tip_merged(d, tip, pr_head):
    """True if the local tip is the merged PR's head or an ancestor of it (nothing newer)."""
    if not pr_head:
        return False
    return tip == pr_head or subprocess.run(
        ["git", "merge-base", "--is-ancestor", tip, pr_head], cwd=d, capture_output=True).returncode == 0


def repo_dirs():
    return sorted(p for p in ROOT.iterdir() if (p / ".git").exists())


def origin_repo(d):
    url = run(["git", "remote", "get-url", "origin"], d, expect_fail=True)
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?/?$", url)
    return m.group(1) if m else None


def local_branches(d):
    """Branches in one clone: name, checked-out, dirty, last commit, push state."""
    default = run(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], d,
                  expect_fail=True).removeprefix("origin/")
    if not default:  # origin/HEAD unset: use whichever of main/master the remote has
        default = next((b for b in ("main", "master") if run(
            ["git", "rev-parse", "--verify", "-q", f"refs/remotes/origin/{b}"], d, expect_fail=True)), None)
    if not default:
        ERRORS.append(f"git (in {d.name}): no origin/HEAD, origin/main or origin/master")
    head = run(["git", "branch", "--show-current"], d, expect_fail=True)
    dirty = len(run(["git", "status", "--porcelain"], d).splitlines())
    emails = EMAILS | {run(["git", "config", "user.email"], d, expect_fail=True)} - {""}
    out = []
    fmt = ("%(refname:short)|%(objectname)|%(upstream:track)|%(upstream)|%(authoremail)|"
           "%(committerdate:iso-strict)")
    for line in run(["git", "for-each-ref", f"--format={fmt}", "refs/heads"], d).splitlines():
        name, tip, track, upstream, author, date = line.split("|", 5)
        if name in (default, "main", "master") or RELEASE.search(name):
            continue
        # None = comparison failed (logged): keep the branch rather than call it 0 ahead.
        ahead = run(["git", "rev-list", "--count", f"origin/{default}..{name}"], d) if default else ""
        push = ("never" if not upstream else "gone" if "gone" in track
                else "ahead" if "ahead" in track else "pushed")
        out.append({"branch": name, "mine": author.strip("<>") in emails, "push_state": push,
                    "ahead_of_default": int(ahead) if ahead else None, "idle_days": age_days(date),
                    "checked_out": name == head, "tip": tip})
    return {"clone": d.name, "path": d, "repo": origin_repo(d), "head": head or "(detached)",
            "dirty_files": dirty, "branches": out}


def linear():
    key_ = os.environ.get("LINEAR_API_KEY")
    if not key_:
        ERRORS.append("linear: LINEAR_API_KEY not set")
        return None
    q = """{ viewer { assignedIssues(first:100, filter:{state:{type:{in:["started","unstarted"]}}}) {
      nodes { identifier title url updatedAt state{name type}
        attachments(first:10){nodes{url}} } } }
      projects(first:50, filter:{lead:{isMe:{eq:true}}}) { nodes { name url health
        status{type} projectUpdates(first:1){nodes{createdAt}} } } }"""
    req = urllib.request.Request("https://api.linear.app/graphql", json.dumps({"query": q}).encode(),
                                 {"Authorization": key_, "Content-Type": "application/json"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:  # network, auth, bad JSON
        ERRORS.append(f"linear: {e}")
        return None
    if resp.get("errors") or not resp.get("data"):
        ERRORS.append(f"linear: {json.dumps(resp.get('errors'))[:200]}")
        return None
    d = resp["data"]
    issues = []
    for i in d["viewer"]["assignedIssues"]["nodes"]:
        # Strip "#pullrequestreview-…" and "/files" so each PR appears once.
        prs = sorted({m.group(0) for a in i["attachments"]["nodes"]
                      if (m := re.match(r"https://github\.com/[^/]+/[^/]+/pull/\d+", a["url"]))})
        issues.append({"id": i["identifier"], "title": i["title"], "url": i["url"],
                       "state": i["state"]["name"], "type": i["state"]["type"],
                       "idle_days": age_days(i["updatedAt"]), "prs": [{"url": u} for u in prs]})
    projects = []
    for p in d["projects"]["nodes"]:
        if p["status"]["type"] in ("completed", "canceled"):
            continue
        last = p["projectUpdates"]["nodes"]
        projects.append({"name": p["name"], "url": p["url"], "health": p["health"],
                         "days_since_update": age_days(last[0]["createdAt"]) if last else None})
    return {"issues": issues, "projects": projects}


def main():
    login = run(["gh", "api", "user", "-q", ".login"])
    raw = run(["gh", "search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
               "--json", "number,title,repository,isDraft,url,updatedAt"])
    prs_raw = [p for p in json.loads(raw or "[]")
               if p["repository"]["nameWithOwner"].lower() not in SKIP_REPOS]
    with ThreadPoolExecutor(8) as ex:
        f_closed = ex.submit(closed_prs, login) if login else None
        f_linear = ex.submit(linear)
        prs = list(ex.map(pr_detail, prs_raw))
        clones = list(ex.map(local_branches, repo_dirs()))
        closed = f_closed.result() if f_closed else {}
        lin = f_linear.result()

    open_by_branch = {key(p["repo"], p["branch"]) for p in prs if p["branch"]}
    for p in prs:
        p["clones"] = [{"clone": c["clone"], "checked_out": b["checked_out"]}
                       for c in clones if (c["repo"] or "").lower() == p["repo"].lower()
                       for b in c["branches"] if b["branch"] == p["branch"]]

    # My branches with commits not on the default branch and no open PR in the same repo.
    candidates = [(c, b) for c in clones for b in c["branches"]
                  if b["mine"] and b["ahead_of_default"] != 0
                  and c["repo"] and c["repo"].lower() not in SKIP_REPOS
                  and key(c["repo"], b["branch"]) not in open_by_branch]
    # Look up a PR for gone branches the closed search didn't cover: a deleted remote is not
    # proof of a merge (a closed, unmerged PR can still leave work behind).
    missing = {key(c["repo"], b["branch"]): (c["repo"], b["branch"]) for c, b in candidates
               if b["push_state"] == "gone" and key(c["repo"], b["branch"]) not in closed}
    with ThreadPoolExecutor(8) as ex:
        for k, found in zip(missing, ex.map(lambda rb: pr_for_branch(*rb), missing.values())):
            if found:
                closed[k] = found
    orphans = []
    for c, b in candidates:
        last = closed.get(key(c["repo"], b["branch"]))
        if last and last["state"] == "MERGED" and tip_merged(c["path"], b["tip"], last["head"]):
            continue  # finished; cleanup-branches deletes these
        # A MERGED last_pr that survives here means commits were added after the merge.
        orphans.append({"clone": c["clone"], "repo": c["repo"],
                        **{k: v for k, v in b.items() if k != "tip"},
                        "last_pr": {k: last[k] for k in ("url", "state")} if last else None})

    # Linear-linked PR states, so a status mismatch can be flagged without guessing.
    if lin:
        known = {p["url"]: "OPEN" for p in prs} | {v["url"]: v["state"] for v in closed.values()}
        unknown = sorted({pr["url"] for i in lin["issues"] for pr in i["prs"]} - known.keys())
        with ThreadPoolExecutor(8) as ex:
            known |= dict(zip(unknown, ex.map(pr_state, unknown)))
        for i in lin["issues"]:
            for pr in i["prs"]:
                pr["state"] = known.get(pr["url"])

    json.dump({"complete": not ERRORS, "errors": ERRORS, "prs": prs,
               "clones": [{k: c[k] for k in ("clone", "repo", "head", "dirty_files")} for c in clones
                          if c["dirty_files"]],
               "branches_without_pr": orphans, "linear": lin},
              sys.stdout, indent=1)


if __name__ == "__main__":
    main()
