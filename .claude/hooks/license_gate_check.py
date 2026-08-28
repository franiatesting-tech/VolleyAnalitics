#!/usr/bin/env python3
"""PreToolUse guard: blocks adding a known-blocked-license dependency without
an explicit decision recorded in docs/licensing/LICENSE_DECISIONS.md. This is
a safety net for the known-worst offenders, not a substitute for the full
oss-license-gate skill procedure. Fails open on any internal error.
"""

import json
import re
import sys

# Packages/imports known to carry a license that's blocked-by-default
# (GPL/AGPL) per docs/licensing/OSS_MANIFEST.md. Keep in sync with that file.
BLOCKED = {
    "ultralytics": "AGPL-3.0 — see docs/licensing/LICENSE_DECISIONS.md D-003. "
    "Benchmark-only, in an isolated environment, never a product import.",
    "sportslabkit": "GPL-3.0 — see docs/licensing/LICENSE_DECISIONS.md D-004. "
    "Reference/study only, never vendored or imported.",
    "rfdetr[plus]": "PML-1.0 (custom, non-open) — see docs/licensing/LICENSE_DECISIONS.md D-002. "
    "Requires explicit legal review before use; stay on Base/Large.",
}

INSTALL_COMMAND_PATTERN = re.compile(
    r"\b(pip install|uv add|uv pip install|pnpm add|npm install|npm i|yarn add)\b",
    re.IGNORECASE,
)


def deny(pkg: str, reason: str):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Blocked: '{pkg}' is on the license blocklist ({reason}). "
                        "Run the oss-license-gate skill and record a decision in "
                        "docs/licensing/LICENSE_DECISIONS.md before adding this dependency."
                    ),
                }
            }
        )
    )
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    haystacks = []

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        if INSTALL_COMMAND_PATTERN.search(command):
            haystacks.append(command.lower())
    elif tool_name in ("Write", "Edit"):
        file_path = (tool_input.get("file_path", "") or "").lower()
        if file_path.endswith(
            ("pyproject.toml", "requirements.txt", "package.json", "pnpm-lock.yaml")
        ):
            content = "".join(str(tool_input.get(k, "")) for k in ("content", "new_string")).lower()
            haystacks.append(content)

    for haystack in haystacks:
        for pkg, reason in BLOCKED.items():
            if pkg.lower() in haystack:
                deny(pkg, reason)

    sys.exit(0)


if __name__ == "__main__":
    main()
