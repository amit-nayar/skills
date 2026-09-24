#!/usr/bin/env python3
"""Condense Claude Code session transcripts for one day into a short, readable digest.

Usage:
    extract_sessions.py YYYY-MM-DD [--tz Europe/Vienna] [--max-chars 400] [--per-file 60]

Finds every main-session JSONL under ~/.claude/projects modified on or after the target
day (subagent transcripts excluded), keeps only user and assistant text whose timestamp
falls on the target day in the given timezone, and prints a digest per session:
project directory, first user messages (the goal), a sample of the conversation, and the
tail (where outcomes live). Tool calls are reduced to the tool name and, for Bash, the
start of the command. Files are streamed line by line; nothing is loaded whole.
"""
import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
import zoneinfo

PR_RE = re.compile(r"#\d{4,6}|\b(?:AND|IOS|WEBL|COREL|SERL|HYB|AI)-\d+\b")


def text_of(msg):
    """Return (role_text, tools) for a message content payload."""
    content = msg.get("content")
    parts, tools = [], []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            t = block.get("type")
            if t == "text":
                parts.append(block.get("text", ""))
            elif t == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input") or {}
                if name == "Bash":
                    tools.append("Bash: " + str(inp.get("command", ""))[:120].replace("\n", " "))
                elif name in ("Edit", "Write", "Read"):
                    tools.append(f"{name}: {inp.get('file_path', '')}")
                else:
                    tools.append(name)
            elif t == "tool_result":
                pass  # results are noise for a summary
    text = "\n".join(p for p in parts if p).strip()
    text = re.sub(r"\n{2,}", "\n", text)
    return text, tools


def digest_file(path, day, tz, max_chars, per_file):
    entries, refs = [], set()
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            ts = rec.get("timestamp")
            if not ts:
                continue
            try:
                when = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
            except ValueError:
                continue
            if when.date() != day:
                continue
            msg = rec.get("message") or {}
            text, tools = text_of(msg)
            if rec.get("type") == "user" and (rec.get("isMeta") or text.startswith("<")):
                # hook output, command wrappers, tool results echoed as user turns
                if not tools:
                    continue
            if not text and not tools:
                continue
            for m in PR_RE.findall(text):
                refs.add(m)
            if len(text) > max_chars:
                text = text[:max_chars] + " …"
            entries.append((when, rec["type"], text, tools))
    return entries, refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date")
    ap.add_argument("--tz", default="Europe/Vienna")
    ap.add_argument("--max-chars", type=int, default=400)
    ap.add_argument("--per-file", type=int, default=60,
                    help="max entries printed per session (head + tail)")
    ap.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    args = ap.parse_args()

    day = dt.date.fromisoformat(args.date)
    tz = zoneinfo.ZoneInfo(args.tz)
    since = dt.datetime.combine(day, dt.time.min, tz).timestamp()

    files = [p for p in glob.glob(os.path.join(args.root, "*", "*.jsonl"))
             if "/subagents/" not in p and os.path.getmtime(p) >= since]
    files.sort(key=os.path.getmtime)

    for path in files:
        entries, refs = digest_file(path, day, tz, args.max_chars, args.per_file)
        if not entries:
            continue
        project = os.path.basename(os.path.dirname(path)).replace("-Users-amit-dev-", "")
        first, last = entries[0][0], entries[-1][0]
        users = [e for e in entries if e[1] == "user" and e[2]]
        print("=" * 100)
        print(f"SESSION {project} {os.path.basename(path)[:8]}  "
              f"{first:%H:%M}–{last:%H:%M}  {len(entries)} msgs on {day}  "
              f"refs: {' '.join(sorted(refs)) or '-'}")
        print("-" * 100)
        print("GOAL (first user messages):")
        for when, _, text, _ in users[:3]:
            print(f"  [{when:%H:%M}] {text}")
        print("-" * 100)
        head_n = args.per_file // 2
        tail_n = args.per_file - head_n
        shown = entries if len(entries) <= args.per_file else entries[:head_n] + [None] + entries[-tail_n:]
        for e in shown:
            if e is None:
                print(f"  … {len(entries) - args.per_file} entries skipped …")
                continue
            when, role, text, tools = e
            tag = "U" if role == "user" else "A"
            if text:
                print(f"  [{when:%H:%M}] {tag}: {text}")
            for t in tools[:3]:
                print(f"           · {t}")
        print()


if __name__ == "__main__":
    main()
