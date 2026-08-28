#!/usr/bin/env python3
"""PreToolUse guard: blocks secrets-in-files, real .env edits, and destructive
commands. Advisory-safety-net only — see docs/licensing and CLAUDE.md for the
policies this enforces. Fails open (exit 0) on any internal error: a buggy
hook must never be the reason a legitimate action gets stuck.
"""
import json
import re
import sys

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # generic "sk-..." API key shape
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),  # Slack tokens
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),  # GitHub PAT
]

DESTRUCTIVE_BASH_PATTERNS = [
    (re.compile(r"\bgit\s+push\s+.*(--force(?!-with-lease)|(?<!--force-with-lease)\s-f\b)"), "force push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard"),
    (re.compile(r"\bgit\s+clean\s+.*-[a-zA-Z]*f"), "git clean -f"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r"), "rm -rf"),
    (re.compile(r"\brmdir\s+/s\s+/q", re.IGNORECASE), "rmdir /s /q"),
    (re.compile(r"\bdel\s+/f\s+/s\s+/q", re.IGNORECASE), "del /f /s /q"),
    (re.compile(r"\bDROP\s+(TABLE|DATABASE)\b", re.IGNORECASE), "DROP TABLE/DATABASE"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.IGNORECASE), "TRUNCATE TABLE"),
    (re.compile(r"\balembic\s+downgrade\b"), "alembic downgrade"),
]

ENV_FILE_PATTERN = re.compile(r"(^|[/\\])\.env(\.[^.]+)?$")
ENV_EXAMPLE_ALLOWED = re.compile(r"\.env\.example$")


def deny(reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "") or ""
        if ENV_FILE_PATTERN.search(file_path) and not ENV_EXAMPLE_ALLOWED.search(file_path):
            deny(
                f"Blocked: {file_path} looks like a real .env file. "
                "This project never commits real secrets — use .env.example with placeholder "
                "values, or ask the user to set the real value themselves."
            )
        content = "".join(
            str(tool_input.get(k, "")) for k in ("content", "new_string", "old_string")
        )
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                deny(
                    f"Blocked: content being written to {file_path or '(unknown file)'} "
                    "matches a known secret/credential pattern. If this is a false positive, "
                    "the user can override manually; do not retry with the same content."
                )

    if tool_name == "Bash":
        command = tool_input.get("command", "") or ""
        for pattern, label in DESTRUCTIVE_BASH_PATTERNS:
            if pattern.search(command):
                deny(
                    f"Blocked: command matches destructive pattern '{label}'. "
                    "Per CLAUDE.md, destructive/irreversible operations need explicit user "
                    "confirmation first — ask the user before retrying, don't route around this."
                )

    sys.exit(0)


if __name__ == "__main__":
    main()
