import { describe, expect, it } from "vitest";

import { slugify } from "@/lib/slug";

describe("slugify", () => {
  it("lowercases and hyphenates", () => {
    expect(slugify("Riverside Volleyball Club")).toBe("riverside-volleyball-club");
  });

  it("collapses consecutive non-alphanumeric characters", () => {
    expect(slugify("Team!!  A -- B")).toBe("team-a-b");
  });

  it("trims leading and trailing hyphens", () => {
    expect(slugify("  -Ready Set-  ")).toBe("ready-set");
  });

  it("handles an already-clean slug", () => {
    expect(slugify("club-42")).toBe("club-42");
  });
});
