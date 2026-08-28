"use client";

import { createAuthClient } from "better-auth/react";
import { organizationClient, jwtClient } from "better-auth/client/plugins";

// No explicit baseURL: Better Auth's client resolves relative to the
// current origin, which is correct both in dev and in any deployed
// environment without another env var to keep in sync.
export const authClient = createAuthClient({
  plugins: [organizationClient(), jwtClient()],
});

export const { useSession, useListOrganizations, useActiveOrganization, signIn, signUp, signOut } =
  authClient;
