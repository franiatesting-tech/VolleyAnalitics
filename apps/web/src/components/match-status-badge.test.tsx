import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MatchStatusBadge, JobStatusBadge } from "@/components/match-status-badge";

describe("MatchStatusBadge", () => {
  it("renders a human-readable label for each match status", () => {
    render(<MatchStatusBadge status="demo_ready" />);
    expect(screen.getByText("Demo ready")).toBeInTheDocument();
  });

  it("renders the failed state distinctly", () => {
    render(<MatchStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});

describe("JobStatusBadge", () => {
  it("renders a human-readable label for each job status", () => {
    render(<JobStatusBadge status="running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });
});
