#!/usr/bin/env python3
"""Turn a small text outline into a Slack Block Kit rich_text payload for an OFT post.

Usage:
    build_message.py OUTLINE.md CHANNEL_ID > payload.json
    build_message.py OUTLINE.md CHANNEL_ID --preview      # print the rendered text instead

Outline format (Markdown subset):

    Out for yesterday:

    ## Release 11.7.0
    - Backported the five queued fixes onto the release branch [#58726](https://github.com/PSPDFKit/PSPDFKit/pull/58726) [thread](https://pspdfkit.slack.com/archives/C.../p...)
      - Sub-bullet: a finding, decision, blocker or next step

    ## Sepia page appearance
    - Reworked the tone to match iOS [#58678](https://github.com/PSPDFKit/PSPDFKit/pull/58678) **RTR**

Rules:
- First non-empty line is the header label (rendered bold).
- `## Name` starts a section (bold header with a blank line before it). Omit sections for a flat list.
- `- ` starts a bullet; two leading spaces (`  - `) make it a sub-bullet.
- Inline: `[label](url)` link, `` `code` `` code style, `**text**` bold.
"""
import json
import re
import sys

INLINE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|`([^`]+)`|\*\*([^*]+)\*\*")


def inline(text):
    els, pos = [], 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            els.append({"type": "text", "text": text[pos:m.start()]})
        if m.group(1):
            els.append({"type": "link", "url": m.group(2), "text": m.group(1)})
        elif m.group(3):
            els.append({"type": "text", "text": m.group(3), "style": {"code": True}})
        else:
            els.append({"type": "text", "text": m.group(4), "style": {"bold": True}})
        pos = m.end()
    if pos < len(text):
        els.append({"type": "text", "text": text[pos:]})
    return els


def section(*els):
    return {"type": "rich_text_section", "elements": list(els)}


def bold(text):
    return {"type": "text", "text": text, "style": {"bold": True}}


def plain(text):
    return {"type": "text", "text": text}


def build(outline):
    lines = [l.rstrip() for l in outline.splitlines()]
    lines = [l for l in lines if l.strip()]
    header, body = lines[0].strip(), lines[1:]

    elements = []
    pending_header = [bold(header)]          # first section carries the label and maybe the first header
    current = None                            # current rich_text_list (indent 0 or 1)

    def flush_header():
        nonlocal pending_header
        if pending_header:
            elements.append(section(*pending_header))
            pending_header = None

    def add_item(indent, text):
        nonlocal current
        flush_header()
        if current is None or current["indent"] != indent:
            current = {"type": "rich_text_list", "style": "bullet", "indent": indent, "elements": []}
            elements.append(current)
        current["elements"].append(section(*inline(text)))

    for raw in body:
        if raw.startswith("## "):
            name = raw[3:].strip()
            current = None
            if pending_header is not None:      # header label + first section share one block
                pending_header += [plain("\n\n"), bold(name), plain("\n")]
            else:
                elements.append(section(plain("\n"), bold(name), plain("\n")))
        elif raw.lstrip().startswith("- "):
            indent = 1 if raw.startswith("  ") else 0
            add_item(indent, raw.lstrip()[2:].strip())
        else:
            raise SystemExit(f"unrecognised line: {raw!r}")
    flush_header()
    return elements, header


def preview(elements):
    def render(sec):
        return "".join(e["text"] if e["type"] != "link" else f"<{e['text']}>" for e in sec["elements"])
    out = []
    for e in elements:
        if e["type"] == "rich_text_section":
            out.append(render(e))
        else:
            for item in e["elements"]:
                out.append(("    ◦ " if e["indent"] else "• ") + render(item) + "\n")
    return "".join(out)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    outline = open(sys.argv[1]).read()
    elements, header = build(outline)
    if "--preview" in sys.argv:
        print(preview(elements))
        return
    payload = {
        "channel": sys.argv[2],
        "text": header.rstrip(":"),
        "blocks": [{"type": "rich_text", "elements": elements}],
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
