import { NextRequest, NextResponse } from "next/server";
import { getSessionCookie } from "better-auth/cookies";

/**
 * Fast, optimistic gate: redirect requests with no session cookie at all
 * before they even render. This is a UX optimization, not the security
 * boundary -- cookie *presence* doesn't prove validity. The authoritative
 * check (valid session + active organization, per ADR-001's "server-verified
 * organization_id, never a client-supplied one") happens in
 * src/app/(app)/layout.tsx and src/app/(app)/matches/layout.tsx via
 * auth.api.getSession, and ultimately in services/api's own JWT/JWKS
 * verification of every /api/v1/* call.
 */
export async function proxy(request: NextRequest) {
  const sessionCookie = getSessionCookie(request);

  if (!sessionCookie) {
    const signInUrl = new URL("/sign-in", request.url);
    signInUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(signInUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/matches/:path*", "/organizations/:path*"],
};
