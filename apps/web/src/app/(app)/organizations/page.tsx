"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Building2, Check, Loader2, Plus } from "lucide-react";

import { authClient, useListOrganizations, useActiveOrganization } from "@/lib/auth-client";
import { slugify } from "@/lib/slug";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

export default function OrganizationsPage() {
  const router = useRouter();
  const { data: organizations, isPending: listPending, refetch } = useListOrganizations();
  const { data: activeOrganization } = useActiveOrganization();

  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [switchingId, setSwitchingId] = useState<string | null>(null);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setCreating(true);

    const { data: org, error: createError } = await authClient.organization.create({
      name,
      slug: `${slugify(name)}-${Math.random().toString(36).slice(2, 7)}`,
    });

    if (createError || !org) {
      setCreating(false);
      setError(createError?.message ?? "Could not create organization.");
      return;
    }

    const { error: activateError } = await authClient.organization.setActive({
      organizationId: org.id,
    });
    setCreating(false);

    if (activateError) {
      setError(activateError.message ?? "Organization created, but could not activate it.");
      return;
    }

    router.push("/matches");
    router.refresh();
  }

  async function handleSelect(organizationId: string) {
    setError(null);
    setSwitchingId(organizationId);
    const { error: activateError } = await authClient.organization.setActive({ organizationId });
    setSwitchingId(null);

    if (activateError) {
      setError(activateError.message ?? "Could not switch organization.");
      return;
    }

    router.push("/matches");
    router.refresh();
  }

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6">
      <div>
        <h1 className="text-lg font-semibold text-foreground">Organization</h1>
        <p className="text-sm text-muted-foreground">
          Every match and statistic is scoped to an organization. Select one to continue, or
          create a new one.
        </p>
      </div>

      {error ? (
        <Alert variant="destructive" data-testid="org-error">
          <AlertCircle />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Your organizations</CardTitle>
        </CardHeader>
        <CardContent>
          {listPending ? (
            <div className="flex flex-col gap-2" data-testid="org-list-loading">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : !organizations || organizations.length === 0 ? (
            <p className="text-sm text-muted-foreground" data-testid="org-list-empty">
              You don&apos;t belong to any organization yet. Create one below.
            </p>
          ) : (
            <ul className="flex flex-col gap-2" data-testid="org-list">
              {organizations.map((org) => {
                const isActive = activeOrganization?.id === org.id;
                return (
                  <li key={org.id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(org.id)}
                      disabled={switchingId === org.id}
                      className="flex w-full items-center justify-between rounded-md border border-border-strong bg-surface-raised px-3 py-2 text-left text-sm hover:border-accent disabled:opacity-60"
                    >
                      <span className="flex items-center gap-2">
                        <Building2 className="size-4 text-muted-foreground" />
                        {org.name}
                      </span>
                      {switchingId === org.id ? (
                        <Loader2 className="size-4 animate-spin motion-reduce:hidden" />
                      ) : isActive ? (
                        <Check className="size-4 text-accent" />
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Create a new organization</CardTitle>
          <CardDescription>For your club, team, or coaching staff.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex items-end gap-3" onSubmit={handleCreate}>
            <div className="flex flex-1 flex-col gap-2">
              <Label htmlFor="org-name">Organization name</Label>
              <Input
                id="org-name"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Riverside Volleyball Club"
              />
            </div>
            <Button type="submit" disabled={creating || name.trim().length === 0}>
              {creating ? (
                <Loader2 className="animate-spin motion-reduce:hidden" />
              ) : (
                <Plus />
              )}
              Create
            </Button>
          </form>
        </CardContent>
      </Card>

      <button
        type="button"
        onClick={() => refetch()}
        className="self-start text-xs text-muted-foreground hover:text-foreground"
      >
        Refresh list
      </button>
    </div>
  );
}
