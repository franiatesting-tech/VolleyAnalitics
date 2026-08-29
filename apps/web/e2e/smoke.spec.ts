import { test, expect } from "@playwright/test";

/**
 * End-to-end golden path, tagged @smoke so `playwright test --grep @smoke`
 * (what CI runs) picks it up. Exercises real Better Auth email+password
 * sign-up, real organization creation/activation, and the real JWT/JWKS
 * path against services/api -- no dev-auth-bypass on the frontend side.
 */
test.describe("golden path @smoke", () => {
  test("sign up, create org, create match, run demo processing, see result @smoke", async ({
    page,
  }) => {
    const unique = Date.now();
    const email = `smoke-${unique}@example.com`;
    const password = "correct-horse-battery-staple";
    const orgName = `Smoke Test Club ${unique}`;
    const homeTeam = `Home ${unique}`;
    const awayTeam = `Away ${unique}`;

    // 1. Sign up a brand-new user.
    await page.goto("/sign-up");
    await page.getByLabel("Name").fill("Smoke Test Coach");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    // 2. No org yet -> forced to organization selection.
    await expect(page).toHaveURL(/\/organizations/);

    // 3. Create an organization, which activates it and redirects to /matches.
    await page.getByLabel("Organization name").fill(orgName);
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page).toHaveURL(/\/matches$/, { timeout: 15_000 });

    // 4. Create a match.
    await page.getByLabel("Home team").fill(homeTeam);
    await page.getByLabel("Away team").fill(awayTeam);
    await page.getByRole("button", { name: "New match" }).click();

    const matchRow = page.getByTestId("match-row").filter({ hasText: homeTeam });
    await expect(matchRow).toBeVisible({ timeout: 15_000 });
    await matchRow.click();

    // 5. Trigger demo processing and poll until it completes.
    await expect(page).toHaveURL(/\/matches\/.+/);
    await page.getByTestId("run-demo-process").click();

    await expect(page.getByTestId("job-status")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("job-status").getByText("Completed")).toBeVisible({
      timeout: 60_000,
    });

    // 6. Match Analysis renders against the real ontology endpoints: the
    // Overview tab shows at least one scored set.
    await expect(page.getByTestId("match-analysis-tabs")).toBeVisible();
    const setRows = page.getByTestId("set-score-list").locator("li");
    await expect(setRows.first()).toBeVisible({ timeout: 15_000 });

    // 7. The headline capability of this phase: a stat tile click resolves
    // to its real source events (Statistic -> Events -> Rallies), per the
    // sports-dataviz click-through mandate -- not just that the tab renders.
    await page.getByRole("tab", { name: "Statistics" }).click();
    await page.getByTestId("stat-serve-total").first().click();
    await expect(page.getByTestId("stat-events-panel")).toBeVisible();
    // StatEventsPanel fans out one request per rally (~200+ on a full 5-set
    // match) to locate matching events -- slower than the default 5s
    // assertion timeout under CI load, unlike every other step here which
    // already has an explicit one. Caught by independent re-review.
    await expect(page.getByTestId("stat-events-list").locator("li").first()).toBeVisible({
      timeout: 30_000,
    });
  });
});
