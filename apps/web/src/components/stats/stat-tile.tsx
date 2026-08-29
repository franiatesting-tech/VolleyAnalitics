"use client";

import { cn } from "@/lib/utils";

export function StatTile({
  label,
  value,
  sublabel,
  tone = "neutral",
  onClick,
  active,
  "data-testid": testId,
}: {
  label: string;
  value: string;
  sublabel?: string;
  tone?: "neutral" | "success" | "destructive" | "accent";
  onClick?: () => void;
  active?: boolean;
  "data-testid"?: string;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      data-testid={testId}
      className={cn(
        "flex flex-col gap-0.5 rounded-md border px-3 py-2.5 text-left transition-colors",
        active ? "border-accent bg-accent/10" : "border-border bg-surface",
        onClick && "cursor-pointer hover:border-border-strong",
      )}
    >
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span
        className={cn(
          "font-mono text-xl font-semibold tabular-nums",
          tone === "success" && "text-success",
          tone === "destructive" && "text-destructive",
          tone === "accent" && "text-accent",
          tone === "neutral" && "text-foreground",
        )}
      >
        {value}
      </span>
      {sublabel ? <span className="text-xs text-muted-foreground">{sublabel}</span> : null}
    </Comp>
  );
}
