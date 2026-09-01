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
let cachedToken: string | null = null;
let cachedUntil = 0;
let tokenRequest: Promise<string | null> | null = null;

function tokenExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const decoded = JSON.parse(globalThis.atob(padded)) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

async function getAuthToken(): Promise<string | null> {
  if (cachedToken && Date.now() < cachedUntil) return cachedToken;
  if (tokenRequest) return tokenRequest;

  tokenRequest = authClient.token().then(({ data }) => {
    cachedToken = data?.token ?? null;
    if (!cachedToken) {
      cachedUntil = 0;
      return null;
    }
    const expiresAt = tokenExpiry(cachedToken);
    cachedUntil = expiresAt ? Math.max(Date.now(), expiresAt - 30_000) : Date.now() + 15_000;
    return cachedToken;
  }).finally(() => {
    tokenRequest = null;
  });
  return tokenRequest;
}

export function invalidateApiAuthToken() {
  cachedToken = null;
  cachedUntil = 0;
  tokenRequest = null;
}

export const apiClient = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  getAuthToken,
);
