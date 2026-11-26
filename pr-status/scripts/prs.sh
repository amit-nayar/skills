#!/bin/bash
# One TSV line per open PR I authored in the Nutrient orgs (drafts included), newest repo/number first.
# Columns: repo, number, url, DRAFT|OPEN, review decision, merge state, failed checks, pending count,
#          updated, queued (1 if I entered it in the Mergify queue), title.
# Read-only. gh lives in /opt/homebrew/bin, which the Bash tool's PATH lacks.
# Source the profile before strict mode: it reads unset variables.
set -a; . ~/.zprofile >/dev/null 2>&1 || true; set +a
set -euo pipefail
export PATH=/opt/homebrew/bin:$PATH
command -v gh >/dev/null || { echo "gh not found" >&2; exit 1; }

gh search prs --author @me --state open --owner PSPDFKit --owner PSPDFKit-labs --limit 100 \
    --json number,repository -q '.[]|"\(.repository.nameWithOwner) \(.number)"' |
xargs -P 8 -L 1 bash -c 'gh pr view "$1" -R "$0" --json number,url,isDraft,reviewDecision,mergeStateStatus,statusCheckRollup,updatedAt,title,comments -q \
  "[\"$0\", (.number|tostring), .url, (if .isDraft then \"DRAFT\" else \"OPEN\" end), (.reviewDecision // \"\"), .mergeStateStatus,
    ([.statusCheckRollup[]?|select(.conclusion==\"FAILURE\")|.name]|join(\"|\")),
    ([.statusCheckRollup[]?|select(.status!=\"COMPLETED\" and .conclusion==null)]|length|tostring),
    .updatedAt[:16],
    (if ([.comments[]|select(.author.login==\"mergify\")|.body|select(contains(\"Entered the queue\"))]|length) > 0 then \"1\" else \"0\" end),
    .title[:90]]|@tsv"' |
sort -t$'\t' -k1,1 -k2,2nr
