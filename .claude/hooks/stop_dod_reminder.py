#!/usr/bin/env python3
"""Stop/SubagentStop: advisory-only reminder (never blocks -- always exits 0)
to check definition-of-done and update PROJECT_STATUS.md, shown only when
there are meaningful uncommitted changes. Fails open on any internal error.
"""
import json
import subprocess
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cwd = payload.get("cwd") or "."

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd, capture_output=True, text=True, timeout=15, check=False,
        )
        changed = [l for l in result.stdout.splitlines() if l.strip()]
    except Exception:
        sys.exit(0)

    # Ignore trivial/no-op cases: nothing changed, or only PROJECT_STATUS.md itself.
    substantive = [l for l in changed if "PROJECT_STATUS.md" not in l]
    if len(substantive) < 3:
        sys.exit(0)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                f"{len(substantive)} files changed this session. Before wrapping up: "
                "check .claude/skills/definition-of-done for the relevant checklist, "
                "and update PROJECT_STATUS.md if this represents a meaningful state change."
            ),
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
