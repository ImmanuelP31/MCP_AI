import { expect, test } from "@playwright/test";

test("operator can navigate core enterprise dashboard routes", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to the operations console" })).toBeVisible();

  await page.getByRole("button", { name: /Operator/i }).click();
  await page.getByRole("button", { name: /Continue/i }).click();

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Fleet status")).toBeVisible();

  await page.getByRole("button", { name: "Devices" }).click();
  await expect(page.getByRole("heading", { name: "Devices" })).toBeVisible();
  await page.goto("/devices/SIM-014");
  await expect(page.getByRole("heading", { name: "SIM-014" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Telemetry" })).toBeVisible();

  await page.getByRole("button", { name: "Approvals" }).click();
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
  await expect(page.getByText("Approval center")).toBeVisible();

  await page.getByRole("button", { name: "Tools" }).click();
  await expect(page.getByRole("heading", { name: "Tools" })).toBeVisible();
  await expect(page.getByText("Tool registry")).toBeVisible();

  await page.getByRole("button", { name: "Capabilities" }).click();
  await expect(page.getByRole("heading", { name: "Capabilities" })).toBeVisible();
  await expect(page.getByText("Capability graph")).toBeVisible();

  await page.getByRole("button", { name: "Security" }).click();
  await expect(page.getByRole("heading", { name: "Security" })).toBeVisible();
  await expect(page.getByText("Control-plane security")).toBeVisible();

  await page.getByRole("button", { name: "System" }).click();
  await expect(page.getByRole("heading", { name: "System", exact: true })).toBeVisible();
  await expect(page.getByText("System health")).toBeVisible();
});
