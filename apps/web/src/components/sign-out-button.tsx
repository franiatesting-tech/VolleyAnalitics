"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";

import { authClient } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";
import { invalidateApiAuthToken } from "@/lib/api-client";

export function SignOutButton() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);

  async function handleSignOut() {
    setLoading(true);
    await authClient.signOut();
    invalidateApiAuthToken();
    queryClient.clear();
    router.push("/sign-in");
    router.refresh();
  }

  return (
    <Button variant="ghost" size="sm" disabled={loading} onClick={handleSignOut}>
      <LogOut />
      Sign out
    </Button>
  );
}
