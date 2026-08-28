import { betterAuth } from "better-auth";
import { organization, jwt } from "better-auth/plugins";
import { Pool } from "pg";

import { deriveOrgClaims } from "@/lib/org-claims";

/**
 * Better Auth owns its own Postgres tables in the same database as
 * services/api's Alembic-owned tables -- two migration systems, one
 * database, neither touches the other's tables (see CLAUDE.md's auth
 * ownership rule and ADR-001 §Authentication).
 *
 * Schema is managed via Better Auth's own CLI, never Alembic:
 *   pnpm --filter web auth:migrate
 */
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

/**
 * services/api verifies the JWT's `org_id` / `org_role` custom claims (see
 * services/api's auth settings + .env.example) against a server-resolved
 * organization -- it never trusts a client-supplied org id. Those claims
 * are looked up here, at token-issuance time, straight from the
 * organization plugin's `member` table, rather than trusting anything
 * embedded in the request. `activeOrganizationId` lives on the session row
 * that the organization plugin adds; if the user has no active org we
 * return org_id/org_role as `undefined` so they're omitted from the JWT
 * payload entirely (JSON.stringify drops `undefined` keys) -- the API
 * correctly 403s on a token with no org_id, and the frontend independently
 * forces organization selection before ever calling /api/v1/*.
 */
async function resolveOrgClaims(activeOrganizationId: string | null | undefined, userId: string) {
  if (!activeOrganizationId) {
    return deriveOrgClaims(undefined, undefined);
  }
  const { rows } = await pool.query<{ role: string }>(
    `select "role" from "member" where "organizationId" = $1 and "userId" = $2 limit 1`,
    [activeOrganizationId, userId],
  );
  return deriveOrgClaims(activeOrganizationId, rows[0]?.role);
}

export const auth = betterAuth({
  database: pool,
  baseURL: process.env.BETTER_AUTH_URL,
  secret: process.env.BETTER_AUTH_SECRET,
  trustedOrigins: [process.env.BETTER_AUTH_URL ?? "http://localhost:3000"],
  emailAndPassword: {
    enabled: true,
    // No SMTP provider wired up for local dev / Phase 1 -- Better Auth does
    // not require email verification unless requireEmailVerification is
    // explicitly turned on, so sign-up/sign-in work immediately.
  },
  plugins: [
    organization({
      // A brand-new user has no organization yet; the app itself (see
      // src/app/(app)/organizations/page.tsx) forces org creation/selection
      // before any /api/v1/* call, so we don't need automatic org creation
      // on sign-up here.
      allowUserToCreateOrganization: true,
    }),
    jwt({
      jwt: {
        issuer: process.env.AUTH_ISSUER,
        audience: process.env.AUTH_AUDIENCE,
        expirationTime: "15m",
        definePayload: async (session) => {
          const { org_id, org_role } = await resolveOrgClaims(
            session.session.activeOrganizationId,
            session.user.id,
          );
          return { org_id, org_role };
        },
      },
    }),
  ],
});

export type Session = typeof auth.$Infer.Session;
