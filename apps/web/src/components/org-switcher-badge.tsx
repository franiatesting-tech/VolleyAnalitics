"use client";

import Link from "next/link";
import { Building2 } from "lucide-react";

import { useActiveOrganization } from "@/lib/auth-client";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export function OrgSwitcherBadge() {
  const { data: activeOrganization, isPending } = useActiveOrganization();

  if (isPending) {
    return <Skeleton className="h-5 w-24" />;
  }

  if (!activeOrganization) {
    return (
      <Link href="/organizations">
        <Badge variant="outline">Select organization</Badge>
      </Link>
    );
  }

  return (
    <Link href="/organizations" title="Switch organization">
      <Badge variant="default" className="gap-1.5">
        <Building2 className="size-3" />
        {activeOrganization.name}
      </Badge>
    </Link>
  );
}
