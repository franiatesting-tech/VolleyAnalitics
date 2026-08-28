import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

export default async function MatchesLayout({ children }: { children: React.ReactNode }) {
  // Every /api/v1/* call needs a JWT with an org_id claim (see src/lib/auth.ts);
  // if there's no active organization, force selection before rendering
  // anything that would call the API.
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    redirect("/sign-in");
  }
  if (!session.session.activeOrganizationId) {
    redirect("/organizations");
  }

  return <>{children}</>;
}
