# @volley/contracts

TypeScript types and a typed fetch client, generated directly from `services/api`'s OpenAPI schema. This package has no hand-written request/response types -- if you find yourself writing an interface that mirrors an API shape, it belongs here instead, generated.

## Regenerating

```bash
pnpm gen:contracts
```

Runs `services/api`'s FastAPI app through `openapi-typescript` and writes `openapi.json` plus `src/schema.d.ts`. Both generated files are committed build inputs: never hand-edit them. CI regenerates them and fails on drift, so a fresh checkout and Docker build have the exact same typed contract without relying on hidden local state. Run this whenever a route or Pydantic schema changes.

## Usage

```ts
import { createApiClient } from "@volley/contracts";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL!, async () => {
  // return the current Better Auth session's JWT, or null
});

const { data, error } = await api.GET("/api/v1/matches");
```
