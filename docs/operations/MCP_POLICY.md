# MCP Policy

Keep the MCP tool surface small. Before adding any MCP server, record: purpose, permissions it requires, trust assessment, secrets it needs, and the real benefit over not having it. Never connect an MCP server with direct write access to production.

## Priority order (per project constitution)

1. GitHub
2. Official documentation servers
3. shadcn MCP (component generation)
4. Browser/Playwright (visual/frontend testing)
5. Better Auth docs, when useful

Do not install large collections of community MCPs for convenience — each one is a trust decision and a maintenance surface.

## Current status

No project-specific MCP servers configured yet (Phase 0). The Claude Code environment this project runs in already provides browser automation and web research tooling; evaluate against the list above before adding anything new, and record the decision here when something is added.
