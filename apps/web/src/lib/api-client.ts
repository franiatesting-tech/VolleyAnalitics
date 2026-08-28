"use client";

import { createApiClient } from "@volley/contracts";

import { authClient } from "@/lib/auth-client";

/**
 * Every /api/v1/* call is authenticated with a short-lived JWT minted by
 * Better Auth's JWT plugin (org_id/org_role custom claims baked in at
 * issuance time -- see src/lib/auth.ts). services/api verifies it via JWKS
 * and scopes the request server-side to that org id; the frontend never
 * sends an org id of its own.
 */
async function getAuthToken(): Promise<string | null> {
  const { data } = await authClient.token();
  return data?.token ?? null;
}

export const apiClient = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  getAuthToken,
);
