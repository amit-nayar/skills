#!/usr/bin/env python3
"""Record what this run decided for a feedback item, so later runs don't redo it.

Usage: record.py <key> <decision> [note]
decision: fixed | replied | needs-amit | skipped
"""
import json, sys
from datetime import date
from pathlib import Path

STATE = Path.home() / "Library/Application Support/claude-routines/review-sweep-state.json"
DECISIONS = {"fixed", "replied", "needs-amit", "skipped"}

key, decision, note = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
if decision not in DECISIONS:
    sys.exit(f"decision must be one of {sorted(DECISIONS)}")
try:
    state = json.loads(STATE.read_text())
except (OSError, ValueError):
    state = {}
state[key] = {"decision": decision, "note": note, "date": date.today().isoformat()}
STATE.parent.mkdir(parents=True, exist_ok=True)
STATE.write_text(json.dumps(state, indent=1, sort_keys=True))
