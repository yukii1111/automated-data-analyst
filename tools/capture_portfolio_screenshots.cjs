const path = require("path");

const { chromium } = require("playwright");

const EDGE_PATH = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const APP_URL = "http://localhost:8510";
const OUTPUT_DIR = path.resolve(__dirname, "..", "assets", "readme");

async function settle(page) {
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(900);
}

async function captureViewport(page, filename) {
  await page.screenshot({
    path: path.join(OUTPUT_DIR, filename),
    animations: "disabled",
  });
}

async function main() {
  const browser = await chromium.launch({
    executablePath: EDGE_PATH,
    headless: true,
  });
  const context = await browser.newContext({
    deviceScaleFactor: 1,
    viewport: { width: 1500, height: 1000 },
  });
  const page = await context.newPage();

  try {
    await page.goto(APP_URL, { waitUntil: "domcontentloaded" });
    await page.addStyleTag({
      content: `
        [data-testid="stHeader"],
        [data-testid="stSidebarCollapsedControl"] {
          display: none !important;
        }
      `,
    });
    await page.getByRole("radio", { name: "Try a sample dataset" }).click();
    await page.getByText("Customer Orders · sample", { exact: true }).waitFor();

    await page.getByRole("tab", { name: "Customer segments" }).click();
    const customerHeading = page.getByRole("heading", {
      name: "Turn transactions into customer segments",
    });
    await page.getByText("330", { exact: true }).first().waitFor();
    await customerHeading.scrollIntoViewIfNeeded();
    await customerHeading.evaluate((element) =>
      element.scrollIntoView({ behavior: "instant", block: "start" }),
    );
    await settle(page);
    await captureViewport(page, "customer-segments.png");

    const customerMap = page.getByText("Recency × frequency customer map", { exact: true });
    await customerMap.scrollIntoViewIfNeeded();
    await customerMap.evaluate((element) =>
      element.scrollIntoView({ behavior: "instant", block: "start" }),
    );
    await settle(page);
    await captureViewport(page, "customer-map.png");

    await page.getByRole("tab", { name: "Retention cohorts" }).click();
    const retentionHeading = page.getByRole("heading", {
      name: "See whether customers come back",
    });
    await retentionHeading.scrollIntoViewIfNeeded();
    await retentionHeading.evaluate((element) =>
      element.scrollIntoView({ behavior: "instant", block: "start" }),
    );
    await settle(page);
    await captureViewport(page, "cohort-retention.png");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
