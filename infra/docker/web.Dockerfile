# syntax=docker/dockerfile:1
FROM node:22-slim AS deps

RUN corepack enable
WORKDIR /workspace

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml* ./
COPY apps/web/package.json apps/web/package.json
COPY packages/ui/package.json packages/ui/package.json
COPY packages/contracts/package.json packages/contracts/package.json

RUN pnpm install --frozen-lockfile

# -----------------------------------------------------------------------
FROM deps AS dev

COPY . .
WORKDIR /workspace/apps/web
EXPOSE 3000
CMD ["pnpm", "dev"]

# -----------------------------------------------------------------------
FROM deps AS build

COPY . .
RUN pnpm --filter web build

# -----------------------------------------------------------------------
FROM node:22-slim AS production

RUN corepack enable
WORKDIR /workspace/apps/web
COPY --from=build /workspace/apps/web/.next ./.next
COPY --from=build /workspace/apps/web/public ./public
COPY --from=build /workspace/apps/web/package.json ./package.json
COPY --from=build /workspace/node_modules /workspace/node_modules

EXPOSE 3000
CMD ["pnpm", "start"]
