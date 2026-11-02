#!/usr/bin/env python3
"""Collect my open PRs, PRs awaiting my review, unfinished local branches and Linear state as JSON.

Read-only. Usage: gather.py [--all]   (--all: include PRs outside the Nutrient GitHub orgs)
Needs `gh` auth, LINEAR_API_KEY and BUILDKITE_API_TOKEN (source ~/.zprofile first). Any source that fails is listed
in `errors` and `complete` is false, so a failure never looks like a quiet week.
"""
import json, os, re, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "dev" / "nutrient"
# Commits are authored with the personal address in most clones; match both.
EMAILS = {"amit@nutrient.io", "amit.nyr@gmail.com"}
NOW = datetime.now(timezone.utc)
# Repos whose branches/PRs are not "my work" for this report (e.g. retired).
SKIP_REPOS = {"pspdfkit/pspdfkit-website"}
NUTRIENT_ORGS = {"pspdfkit", "pspdfkit-labs"}
WEBSITE = "pspdfkit/nutrient-website"
# Natalye: website copy review, requested with the "needs copy review" label after the content review.
COPY_REVIEWER = "deutschbitte"
BOTS = {"nutrient-code-reviewer", "copilot-pull-request-reviewer", "linear-code", "mergify"}
# CANCELLED is reported separately: a cancelled run didn't finish, it didn't fail.
FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE"}
# First path segment of branches named after a type rather than a person ("fix/…", "stack/…").
TYPE_PREFIXES = {"fix", "bugfix", "hotfix", "feature", "feat", "improvement", "cleanup", "chore",
                 "docs", "refactor", "test", "ci", "build", "perf", "stack", "release", "wip"}
MY_PREFIXES = {"amit", "amit-nayar"}
# Release branches carry cherry-picks, so they are always "ahead" but never unfinished work.
RELEASE = re.compile(r"(-stable$|^release[/-])")
ERRORS = []
# gh failures worth retrying: the Monday run regularly loses a few calls to these.
TRANSIENT = re.compile(r"connection reset|timeout|timed out|EOF|50[234]|TLS handshake", re.I)


def run(cmd, cwd=None, expect_fail=False):
    """stdout on success; on failure "" and, unless expected, an entry in ERRORS."""
    for attempt in range(3):
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.strip()
        if not TRANSIENT.search(r.stderr or ""):
            break
        time.sleep(2 * (attempt + 1))
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
               "headRefName,headRefOid,baseRefName,reviewDecision,mergeable,mergeStateStatus,"
               "latestReviews,statusCheckRollup,labels"])
    d = json.loads(raw) if raw else {}
    # Re-runs leave several entries per check; only the newest one counts.
    latest = {}
    for c in d.get("statusCheckRollup") or []:
        name = c.get("name") or c.get("context")
        when = c.get("startedAt") or c.get("createdAt") or ""
        if name not in latest or when >= latest[name][0]:
            latest[name] = (when, c)
    checks = [c for _, c in latest.values()]
    failed = [n for n, (_, c) in latest.items()
              if c.get("conclusion") in FAILED or c.get("state") in FAILED]
    failed_urls = [(n, c.get("targetUrl") or c.get("detailsUrl")) for n, (_, c) in latest.items()
                   if n in failed]
    cancelled = [n for n, (_, c) in latest.items() if c.get("conclusion") == "CANCELLED"]
    pending = sum(1 for c in checks if c.get("status") in ("IN_PROGRESS", "QUEUED", "PENDING")
                  or c.get("state") in ("PENDING", "EXPECTED"))
    humans = [r["author"]["login"] for r in d.get("latestReviews") or []
              if r["author"]["login"] not in BOTS]
    return {
        "repo": repo, "number": n, "title": pr["title"], "url": pr["url"],
        "draft": pr["isDraft"], "branch": d.get("headRefName"), "base": d.get("baseRefName"),
        "review": d.get("reviewDecision") or "", "human_reviewers": humans,
        "approved_by": [r["author"]["login"] for r in d.get("latestReviews") or [] if r["state"] == "APPROVED"],
        "labels": [l["name"] for l in d.get("labels") or []],
        "mergeable": d.get("mergeable"), "merge_state": d.get("mergeStateStatus"),
        "failed_checks": failed, "cancelled_checks": cancelled, "pending_checks": pending,
        # Each failed job: kind infra / real / unknown, its link and the deciding log line.
        "ci_failures": classify_failures(failed_urls) if failed else [],
        "dequeued": dequeue(repo, n) if d.get("reviewDecision") == "APPROVED" else None,
        "merge_queue": merge_queue(repo, d["headRefOid"])
        if d.get("reviewDecision") == "APPROVED" and "Mergify Merge Queue" in latest else None,
        "unsigned_commits": unsigned_commits(repo, n),
        "idle_days": age_days(pr["updatedAt"]),
        # Review/CI fields are blank when this is true; don't classify the PR from them.
        "detail_missing": not d,
    }


BK_API = "https://api.buildkite.com/v2/organizations/pspdfkit"
BK_JOB = re.compile(r"https://buildkite\.com/pspdfkit/([^/]+)/builds/(\d+)#([0-9a-f-]{36})")
BK_BUILD = re.compile(r"https://buildkite\.com/pspdfkit/([^/#?]+)/builds/(\d+)(?![#\d])")
# Failures that say nothing about the code: rate limits, network, lost agents, emulators that
# never booted (exit 201) or couldn't install the APK (exit 211).
INFRA = re.compile(r"status code 429|Too Many Requests|Could not (GET|HEAD) '|Connection reset|"
                   r"connect timed out|Read timed out|No space left on device|[Aa]gent (was )?lost|"
                   r"TLS handshake|502 Bad Gateway|503 Service Unavailable|"
                   r"Cannot connect to the Docker daemon|exited with status (201|211)\b")
# Failures the code caused: failing tests, compile errors, lint and formatting.
REAL = re.compile(r"tests completed, \d+ failed|There were failing tests|Lint found \d+ errors?|"
                  r"format violations|^e: |\.(kt|java|cpp|h|mm?|swift|ts|rb):\d+:(\d+:)? error|"
                  r"\d+ examples?, [1-9]\d* failures?|Compilation failed", re.M)
ANSI = re.compile(r"\x1b\[[0-9;]*m|_bk;t=\d+|\x1b_|\x07")


def bk_get(path, raw=False):
    token = os.environ.get("BUILDKITE_API_TOKEN")
    if not token:
        return None
    base, _, query = path.partition("?")
    # Query-parameter auth, token first; header auth is unreliable with this token.
    url = f"{BK_API}/{base}?access_token={token}" + (f"&{query}" if query else "")
    try:
        body = urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")
    except Exception as e:
        ERRORS.append(f"buildkite {base}: {e}")
        return None
    body = re.sub(r"[\x00-\x08\x0b-\x1f]", "", body)
    return body if raw else json.loads(body)


def classify_job(pipeline, build, job, name):
    """One failed Buildkite job: infra (rate limit, network, lost agent), real (tests, compile,
    lint) or unknown, with the line that decided it."""
    url = f"https://buildkite.com/pspdfkit/{pipeline}/builds/{build}#{job}"
    log = bk_get(f"pipelines/{pipeline}/builds/{build}/jobs/{job}/log.txt", raw=True)
    if log is None:
        return {"check": name, "url": url, "kind": "unknown", "evidence": "log not available"}
    lines = [ANSI.sub("", l).strip() for l in log.splitlines()]
    real = next((l for l in lines if REAL.search(l)), None)
    infra = next((l for l in lines if INFRA.search(l)), None)
    kind = "real" if real else "infra" if infra else "unknown"
    return {"check": name, "url": url, "kind": kind, "evidence": (real or infra or "")[:160]}


def classify_build(pipeline, build, name):
    """Failed command jobs of a build whose check had no job link. Trigger steps are skipped:
    their child builds report as checks of their own."""
    b = bk_get(f"pipelines/{pipeline}/builds/{build}")
    if not b:
        return [{"check": name, "url": f"https://buildkite.com/pspdfkit/{pipeline}/builds/{build}",
                 "kind": "unknown", "evidence": "build not available"}]
    return [classify_job(pipeline, build, j["id"], j.get("name") or name)
            for j in b.get("jobs") or []
            if j.get("type") == "script" and j.get("state") == "failed"][:4]


def classify_failures(urls):
    """[(check name, url)] of failed checks -> classified failures, one per failed job."""
    jobs = {(m.group(1), m.group(2), m.group(3)): n for n, u in urls if (m := BK_JOB.match(u or ""))}
    covered = {(p, b) for p, b, _ in jobs}
    builds = {(m.group(1), m.group(2)): n for n, u in urls
              if not BK_JOB.match(u or "") and (m := BK_BUILD.match(u or "")) and (m.group(1), m.group(2)) not in covered}
    out = [classify_job(p, b, j, n) for (p, b, j), n in jobs.items()]
    for (p, b), n in builds.items():
        out += classify_build(p, b, n)
    out += [{"check": n, "url": u, "kind": "unknown", "evidence": ""} for n, u in urls
            if u and not BK_BUILD.match(u) and not BK_JOB.match(u)]
    return out


def dequeue(repo, n):
    """Set when Mergify's latest state for the PR is "dequeued": the failed merge-queue build's
    jobs, classified. None when the PR was never dequeued or is queued again."""
    raw = run(["gh", "api", f"repos/{repo}/issues/{n}/comments?per_page=100",
               "-q", '[.[] | {user: .user.login, body, html_url, created_at, updated_at}]'])
    if not raw:
        return None
    comments = json.loads(raw)
    payloads = []
    for c in comments:
        if c["user"] == "mergify[bot]" and (m := re.search(r"-\*- Mergify Payload -\*-\s*(\{.*?\})\s*-\*- Mergify Payload End", c["body"], re.S)):
            payloads.append((c["updated_at"], json.loads(m.group(1))))
    if not payloads or max(payloads, key=lambda p: p[0])[1].get("state") != "dequeued":
        return None
    summaries = [c for c in comments if "nutrient-mergify-failed-builds" in c["body"]]
    if not summaries:
        return {"summary_url": None, "failures": []}
    last = summaries[-1]
    # Mergify leaves its comment at "dequeued" after a re-queue, so a queue command or checkbox
    # tick newer than the failure summary means it's queued again.
    requeued = [c for c in comments if c["created_at"] > last["created_at"]
                and (re.match(r"\s*@mergifyio (re)?queue", c["body"]) or "[x] Queue this pull request" in c["body"])]
    if requeued:
        return None
    urls = [("merge queue", u) for u in re.findall(r"https://buildkite\.com/pspdfkit/[^\s)\]|]+", last["body"])
            if not u.startswith("https://buildkite.com/pspdfkit/pspdfkit/")]
    return {"summary_url": last["html_url"], "failures": classify_failures(urls)}


def unsigned_commits(repo, n):
    """Short SHAs of PR commits GitHub doesn't show as verified; the merge queue rejects them.

    None when the lookup failed (unknown, not clean). Covers the last 100 commits.
    """
    owner, name = repo.split("/")
    q = (f'{{repository(owner:"{owner}",name:"{name}"){{pullRequest(number:{n}){{'
         'commits(last:100){nodes{commit{abbreviatedOid signature{isValid}}}}}}}')
    raw = run(["gh", "api", "graphql", "-f", f"query={q}",
               "-q", ".data.repository.pullRequest.commits.nodes"])
    if not raw:
        return None
    return [c["commit"]["abbreviatedOid"] for c in json.loads(raw)
            if not (c["commit"]["signature"] or {}).get("isValid")]


def merge_queue(repo, sha):
    """Title of the Mergify queue check: "Merge queue is ready" means approved but not queued."""
    return run(["gh", "api", f"repos/{repo}/commits/{sha}/check-runs?check_name=Mergify%20Merge%20Queue",
                "-q", ".check_runs[0].output.title"]) or None


def is_mine(d, name, base, tip_author, emails):
    """Branches named for someone else ("akshay/…") aren't mine even if I committed to them.
    Otherwise go by the oldest commit on the branch: whoever started it owns it."""
    first = name.split("/", 1)[0] if "/" in name else ""
    if first in MY_PREFIXES:
        return True
    if first and first not in TYPE_PREFIXES:
        return False
    oldest = run(["git", "log", "--reverse", "--format=%ae", f"{base}..{name}"], d,
                 expect_fail=True).split("\n", 1)[0] if base else ""
    return (oldest or tip_author) in emails


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


def review_requests(include_all):
    """Open PRs waiting on my review. `direct` is False when only a team I'm in was asked."""
    q = """query($q: String!) { search(query: $q, type: ISSUE, first: 100) { nodes {
      ... on PullRequest { number title url isDraft createdAt updatedAt author { login }
        repository { nameWithOwner } } } } }"""
    found = {}
    for direct, qualifier in ((False, "review-requested:@me"), (True, "user-review-requested:@me")):
        raw = run(["gh", "api", "graphql", "-f", f"query={q}",
                   "-f", f"q=is:pr is:open archived:false {qualifier}"])
        for p in (json.loads(raw)["data"]["search"]["nodes"] if raw else []):
            repo = p["repository"]["nameWithOwner"]
            if repo.lower() in SKIP_REPOS or not (include_all or repo.split("/")[0].lower() in NUTRIENT_ORGS):
                continue
            found.setdefault(p["url"], {
                "repo": repo, "number": p["number"], "title": p["title"], "url": p["url"],
                "author": (p["author"] or {}).get("login"), "draft": p["isDraft"],
                "age_days": age_days(p["createdAt"]), "idle_days": age_days(p["updatedAt"]),
                "direct": False})["direct"] |= direct
    return sorted(found.values(), key=lambda p: (not p["direct"], -(p["age_days"] or 0)))


def pr_info(url):
    raw = run(["gh", "pr", "view", url, "--json", "state,title,headRefName"])
    return json.loads(raw) if raw else None


def tip_merged(d, repo, branch, tip, pr_head):
    """Whether the merged PR's head covers the local tip: True, False, or None if unverifiable.

    A clone that hasn't fetched the PR's final commits can't answer locally (git exits 128, not 1),
    so ask GitHub instead; only a definite "no" means there is newer work.
    """
    if not pr_head:
        return None
    if tip == pr_head:
        return True
    rc = subprocess.run(["git", "merge-base", "--is-ancestor", tip, pr_head], cwd=d,
                        capture_output=True).returncode
    if rc in (0, 1):
        return rc == 0
    # compare/base...head: "ahead"/"identical" means pr_head contains tip.
    status = run(["gh", "api", f"repos/{repo}/compare/{tip}...{pr_head}", "-q", ".status"],
                 expect_fail=True)
    if status:
        return status in ("ahead", "identical")
    ERRORS.append(f"merge coverage unknown for {branch} (in {d.name}): {pr_head[:9]} not local, "
                  "GitHub compare failed")
    return None


def website_copy_state(prs):
    """Website PRs: where they are in copy review, and the open release they ship with, if any.

    `copy`: "approved" (Natalye approved), "requested" (has "needs copy review"), "skipped" (has
    "skip copy review"), or "not requested". `release`: the open website release PR whose platform
    and major.minor version the PR's branch or title names; such PRs wait for that release.
    """
    raw = run(["gh", "pr", "list", "-R", WEBSITE, "--state", "open", "--limit", "50",
               "--json", "number,url,headRefName"])
    releases = []
    for r in json.loads(raw or "[]"):
        if m := re.match(r"release/([a-z-]+?)-(\d+\.\d+)", r["headRefName"]):
            releases.append({"platform": m.group(1), "version": m.group(2), "url": r["url"], "number": r["number"]})
    for p in prs:
        if p["repo"].lower() != WEBSITE or (p["branch"] or "").startswith("release/"):
            continue  # release PRs ship the release; they don't wait on it or on copy review
        labels = set(p.get("labels") or [])
        p["copy"] = ("approved" if COPY_REVIEWER in (p.get("approved_by") or [])
                     else "requested" if "needs copy review" in labels
                     else "skipped" if "skip copy review" in labels else "not requested")
        text = f"{p['branch'] or ''} {p['title']}".lower()
        p["release"] = next(({"version": r["version"], "url": r["url"]} for r in releases
                             if r["url"] != p["url"] and r["platform"] in text
                             and re.search(rf"(?<![\d.]){re.escape(r['version'])}(?![\d])", text)), None)


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
        out.append({"branch": name, "mine": is_mine(d, name, default and f"origin/{default}", author.strip("<>"), emails), "push_state": push,
                    "ahead_of_default": int(ahead) if ahead else None, "idle_days": age_days(date),
                    "checked_out": name == head, "tip": tip})
    # Worktrees share refs with their main clone; the common dir tells them apart.
    common = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], d, expect_fail=True)
    return {"clone": d.name, "path": d, "repo": origin_repo(d), "head": head or "(detached)", "common": common or str(d),
            "dirty_files": dirty, "branches": out}


def linear():
    key_ = os.environ.get("LINEAR_API_KEY")
    if not key_:
        ERRORS.append("linear: LINEAR_API_KEY not set")
        return None
    q = """{ viewer { assignedIssues(first:100, filter:{state:{type:{in:["started","unstarted"]}}}) {
      nodes { id identifier title url updatedAt state{name type} team{id}
        attachments(first:50, filter:{url:{contains:"/pull/"}}){nodes{url}} } } }
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
        issues.append({"id": i["identifier"], "uuid": i["id"], "team_id": i["team"]["id"],
                       "title": i["title"], "url": i["url"],
                       "state": i["state"]["name"], "type": i["state"]["type"],
                       "idle_days": age_days(i["updatedAt"]), "prs": [{"url": u} for u in prs]})
    projects = []
    for p in d["projects"]["nodes"]:
        if p["status"]["type"] in ("backlog", "completed", "canceled"):
            continue
        last = p["projectUpdates"]["nodes"]
        projects.append({"name": p["name"], "url": p["url"], "health": p["health"],
                         "days_since_update": age_days(last[0]["createdAt"]) if last else None})
    return {"issues": issues, "projects": projects}


def main():
    include_all = "--all" in sys.argv[1:]
    login = run(["gh", "api", "user", "-q", ".login"])
    raw = run(["gh", "search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
               "--json", "number,title,repository,isDraft,url,updatedAt"])
    prs_raw = [p for p in json.loads(raw or "[]")
               if p["repository"]["nameWithOwner"].lower() not in SKIP_REPOS
               and (include_all or p["repository"]["nameWithOwner"].split("/")[0].lower() in NUTRIENT_ORGS)]
    with ThreadPoolExecutor(8) as ex:
        f_closed = ex.submit(closed_prs, login) if login else None
        f_linear = ex.submit(linear)
        f_requests = ex.submit(review_requests, include_all)
        prs = list(ex.map(pr_detail, prs_raw))
        # Release PRs into a stable branch merge without review as part of the release; nothing to report.
        prs = [p for p in prs if not ((p["branch"] or "").startswith("release/") and (p["base"] or "").endswith("-stable"))]
        clones = list(ex.map(local_branches, repo_dirs()))
        closed = f_closed.result() if f_closed else {}
        lin = f_linear.result()
        requests = f_requests.result()

    open_by_branch = {key(p["repo"], p["branch"]) for p in prs if p["branch"]}
    website_copy_state(prs)
    for p in prs:
        p["clones"] = [{"clone": c["clone"], "checked_out": b["checked_out"]}
                       for c in clones if (c["repo"] or "").lower() == p["repo"].lower()
                       for b in c["branches"] if b["branch"] == p["branch"]]

    # My branches with commits not on the default branch and no open PR in the same repo.
    candidates = [(c, b) for c in clones for b in c["branches"]
                  if b["mine"] and b["ahead_of_default"] != 0
                  and c["repo"] and c["repo"].lower() not in SKIP_REPOS
                  and key(c["repo"], b["branch"]) not in open_by_branch]
    # A branch shows up in every worktree of its clone: keep one entry, preferring the checkout
    # that has it checked out, then the main clone.
    best = {}
    for c, b in candidates:
        k = (c["common"], b["branch"])
        rank = (b["checked_out"], Path(c["common"]).parent == c["path"])
        if k not in best or rank > best[k][0]:
            best[k] = (rank, c, b)
    candidates = [(c, b) for _, c, b in best.values()]
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
        covered = None
        if last and last["state"] == "MERGED":
            covered = tip_merged(c["path"], c["repo"], b["branch"], b["tip"], last["head"])
            if covered:
                continue  # finished; cleanup-branches deletes these
        orphans.append({"clone": c["clone"], "repo": c["repo"],
                        **{k: v for k, v in b.items() if k != "tip"},
                        "last_pr": ({k: last[k] for k in ("url", "state")}
                                    # MERGED only: False = commits added after the merge,
                                    # None = couldn't tell.
                                    | ({"tip_covered": covered} if last["state"] == "MERGED" else {})
                                    if last else None)})

    # Linear-linked PR states, so a status mismatch can be flagged without guessing. `for_issue`
    # is whether the PR names the issue in its title or branch; a merged PR that doesn't (say, a
    # prerequisite from another issue) says nothing about this issue's state.
    if lin:
        urls = sorted({pr["url"] for i in lin["issues"] for pr in i["prs"]})
        with ThreadPoolExecutor(8) as ex:
            info = dict(zip(urls, ex.map(pr_info, urls)))
        for i in lin["issues"]:
            for pr in i["prs"]:
                d = info.get(pr["url"])
                pr["state"] = d and d["state"]
                pr["for_issue"] = d and i["id"].lower() in f'{d["title"]} {d["headRefName"]}'.lower()

    json.dump({"complete": not ERRORS, "errors": ERRORS, "prs": prs, "review_requests": requests,
               "clones": [{k: c[k] for k in ("clone", "repo", "head", "dirty_files")} for c in clones
                          if c["dirty_files"]],
               "branches_without_pr": orphans, "linear": lin},
              sys.stdout, indent=1)


if __name__ == "__main__":
    main()
