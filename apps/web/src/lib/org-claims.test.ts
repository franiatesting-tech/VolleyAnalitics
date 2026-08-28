import { describe, expect, it } from "vitest";

import { deriveOrgClaims } from "@/lib/org-claims";

describe("deriveOrgClaims", () => {
  it("returns org_id/org_role when there is an active org and a matching membership", () => {
    expect(deriveOrgClaims("org_123", "owner")).toEqual({
      org_id: "org_123",
      org_role: "owner",
    });
  });

  it("omits both claims when there is no active organization", () => {
    expect(deriveOrgClaims(null, undefined)).toEqual({
      org_id: undefined,
      org_role: undefined,
    });
    expect(deriveOrgClaims(undefined, undefined)).toEqual({
      org_id: undefined,
      org_role: undefined,
    });
  });

  it("omits both claims when the active org has no matching membership row (stale pointer)", () => {
    // e.g. the user was removed from the org in another tab/session --
    // never issue org_id without a role we can actually back up.
    expect(deriveOrgClaims("org_123", undefined)).toEqual({
      org_id: undefined,
      org_role: undefined,
    });
    expect(deriveOrgClaims("org_123", null)).toEqual({
      org_id: undefined,
      org_role: undefined,
    });
  });
});
