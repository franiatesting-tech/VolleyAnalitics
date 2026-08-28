# Third-Party Notices

This file will be auto-assembled (from `package.json`/`pnpm-lock.yaml` and `pyproject.toml`/`uv.lock`) once real dependencies are added in Phase 1 — see `ROADMAP.md`. It is the legally-required attribution/notice file shipped with the product (per MIT/BSD/Apache-2.0 attribution clauses, and LGPL notice requirements for FFmpeg — see `LICENSE_DECISIONS.md` D-006).

Do not hand-maintain this list once tooling exists for it; generate it as part of the release process (see `.claude/skills/release-gate`) so it can never silently drift from the actual dependency tree.

## Until automated generation exists

Any dependency added before the generator exists must have its license text + copyright notice appended below manually, in this format:

```
## <package name> <version>
License: <SPDX identifier>
<copyright notice, verbatim>
<link to full license text>
```

_(No dependencies added yet — repository is at Phase 0.)_
