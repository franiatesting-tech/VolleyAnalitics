#!/usr/bin/env python3
"""SessionStart: loads a condensed view of PROJECT_STATUS.md + the current
ROADMAP.md phase + open LICENSE_DECISIONS.md items into context, so every
session starts with current project state instead of stale assumptions.
Fails open (prints nothing, exits 0) on any internal error.
"""

import json
import re
import sys
from pathlib import Path


def read(path: Path, max_chars=3000):
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except Exception:
        return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd = payload.get("cwd") or "."
    root = Path(cwd)

    status = read(root / "PROJECT_STATUS.md")
    roadmap = read(root / "ROADMAP.md", max_chars=1500)
    decisions = read(root / "docs" / "licensing" / "LICENSE_DECISIONS.md", max_chars=8000)

    status_open_re = re.compile(r"status[:\*\s]*open", re.IGNORECASE)
    open_items = (
        "\n".join(line for line in decisions.splitlines() if status_open_re.search(line))
        or "(none currently open)"
    )

    phase_match = re.search(r"^##\s+(Phase[^\n]*)", roadmap, re.MULTILINE)
    current_phase = phase_match.group(1) if phase_match else "(see ROADMAP.md)"

    if not status and not roadmap:
        sys.exit(0)

    context = (
        "## Project context (auto-loaded from PROJECT_STATUS.md / ROADMAP.md)\n\n"
        f"{status}\n\n"
        f"Next roadmap phase: {current_phase}\n\n"
        f"Open licensing decisions:\n{open_items}\n"
    )

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
