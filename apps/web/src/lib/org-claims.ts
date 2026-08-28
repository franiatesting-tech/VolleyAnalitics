/**
 * Pure derivation of the JWT's org_id/org_role custom claims from a looked
 * up membership row. Split out from src/lib/auth.ts (which does the actual
 * DB lookup via `pg`) so the "no org -> no claims, stale org -> no claims"
 * logic is unit-testable without a database.
 *
 * services/api rejects any /api/v1/* request whose JWT has no org_id claim
 * (see .env.example's AUTH_* vars and ADR-001 §Authentication) -- so this
 * function must never fabricate a claim it can't back with a real,
 * currently-valid membership row.
 */
export interface OrgClaims {
  org_id: string | undefined;
  org_role: string | undefined;
}

export function deriveOrgClaims(
  activeOrganizationId: string | null | undefined,
  memberRole: string | null | undefined,
): OrgClaims {
  if (!activeOrganizationId || !memberRole) {
    return { org_id: undefined, org_role: undefined };
  }
  return { org_id: activeOrganizationId, org_role: memberRole };
}
