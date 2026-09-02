import { headers } from "next/headers";
import { redirect } from "next/navigation";
import Link from "next/link";
import { Activity, Film, Swords } from "lucide-react";

import { auth } from "@/lib/auth";
import { OrgSwitcherBadge } from "@/components/org-switcher-badge";
import { SignOutButton } from "@/components/sign-out-button";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  // Authoritative session check (defense in depth behind src/proxy.ts's
  // optimistic cookie check) -- every page under this layout requires a
  // real, DB-verified session. Active-organization enforcement happens one
  // layer down, in src/app/(app)/matches/layout.tsx, since /organizations
  // itself must be reachable by a signed-in user with no org yet.
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    redirect("/sign-in");
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="sticky top-0 z-50 flex h-16 shrink-0 items-center justify-between border-b border-border bg-background/88 px-4 backdrop-blur-xl md:px-6">
        <div className="flex items-center gap-6">
        <Link href="/matches" className="flex items-center gap-2 text-sm font-semibold">
          <Activity className="size-4 text-accent" />
          Volley <span className="text-accent">Intelligence</span>
        </Link>
        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary navigation">
          <Link href="/matches" className="flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-surface hover:text-foreground"><Swords className="size-3.5" /> Matches</Link>
          <Link href="/videos" className="flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-surface hover:text-foreground"><Film className="size-3.5" /> Video ingest</Link>
        </nav>
        </div>
        <div className="flex items-center gap-4">
          <OrgSwitcherBadge />
          <span className="hidden text-sm text-muted-foreground lg:inline">{session.user.email}</span>
          <SignOutButton />
        </div>
      </header>
      <main className="flex-1 px-6 py-8">{children}</main>
    </div>
  );
}
