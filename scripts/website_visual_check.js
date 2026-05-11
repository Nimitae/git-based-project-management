const fs = require("fs");
const { chromium } = require("playwright");

async function main() {
  const url = process.argv[2] || "http://127.0.0.1:8787/";
  const output = process.argv[3] || "project-hub-website.png";
  let browser;
  const attempts = [
    { headless: true },
    { channel: "msedge", headless: true },
    { channel: "chrome", headless: true },
    { executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", headless: true },
    { executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", headless: true }
  ];
  let lastError;
  for (const options of attempts) {
    if (options.executablePath && !fs.existsSync(options.executablePath)) continue;
    try {
      browser = await chromium.launch(options);
      break;
    } catch (error) {
      lastError = error;
    }
  }
  if (!browser) throw lastError;
  const page = await browser.newPage({ viewport: { width: 1440, height: 920 } });
  await page.goto(url, { waitUntil: "networkidle" });
  await page.screenshot({ path: output, fullPage: true });
  const heading = await page.locator("h1").innerText();
  const metrics = await page.locator(".metric").count();
  if (!heading.includes("Project Workspace")) {
    throw new Error(`Unexpected heading: ${heading}`);
  }
  if (metrics < 4) {
    throw new Error(`Expected 4 metrics, found ${metrics}`);
  }
  await browser.close();
  console.log(JSON.stringify({ ok: true, url, output, metrics }, null, 2));
}

main().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
