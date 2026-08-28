#!/usr/bin/env python3
"""PostToolUse: runs a targeted, fast formatter/lint check on the single file
just written/edited -- never the whole suite (see CLAUDE.md hooks guidance).
No-ops quietly if the relevant tool/config isn't set up yet (e.g. Phase 0,
before any real code exists). Fails open on any internal error.
"""

import contextlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd):
    with contextlib.suppress(Exception):
        subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=30, check=False)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "") or ""
    project_dir = payload.get("cwd") or "."
    if not file_path:
        sys.exit(0)

    path = Path(file_path)
    root = Path(project_dir)

    try:
        if path.suffix == ".py" and shutil.which("ruff") and (root / "pyproject.toml").exists():
            run(["ruff", "check", "--fix", "--quiet", str(path)], cwd=project_dir)
            run(["ruff", "format", "--quiet", str(path)], cwd=project_dir)
        elif (
            path.suffix in (".ts", ".tsx", ".js", ".jsx")
            and shutil.which("pnpm")
            and (root / "apps" / "web" / "package.json").exists()
        ):
            run(["pnpm", "--filter", "web", "exec", "eslint", "--fix", str(path)], cwd=project_dir)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
