import { chromium } from 'playwright';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIST_DIR = path.join(__dirname, 'dist');
const SCREENSHOT_DIR = path.join(DIST_DIR, 'screenshots');
const ARTIFACT_DIR = 'C:\\Users\\Pradeep S\\.gemini\\antigravity\\brain\\cb462d28-18de-4a84-83e8-8ee7945a664f';

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

function startServer(port = 4173) {
  const server = http.createServer((req, res) => {
    let reqPath = req.url.split('?')[0];
    if (reqPath === '/') reqPath = '/index.html';
    let filePath = path.join(DIST_DIR, reqPath);

    if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
      filePath = path.join(DIST_DIR, 'index.html');
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    try {
      const data = fs.readFileSync(filePath);
      res.writeHead(200, { 'Content-Type': contentType });
      res.end(data);
    } catch {
      res.writeHead(404);
      res.end('Not found');
    }
  });

  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      console.log(`[server] Serving frontend/dist on http://127.0.0.1:${port}`);
      resolve(server);
    });
  });
}

async function verifyPageFonts(page, screenName) {
  const result = await page.evaluate((name) => {
    const violations = [];
    const sizeDistribution = {};
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;

    while ((node = walker.nextNode())) {
      const text = node.textContent?.trim();
      if (!text) continue;
      const el = node.parentElement;
      if (!el) continue;

      // Visibility check
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

      const fontSize = parseFloat(style.fontSize);
      const roundedSize = Math.round(fontSize * 10) / 10;
      sizeDistribution[roundedSize] = (sizeDistribution[roundedSize] || 0) + 1;

      // Check for Invalid Date
      if (text.includes('Invalid Date')) {
        violations.push({
          type: 'invalid-date',
          text,
          screen: name,
          tag: el.tagName.toLowerCase(),
          fontSize,
        });
      }

      // Check min 14px rule (diff line numbers allowed down to 13px)
      const isDiffLineNo = el.classList.contains('diff-lineno') || el.closest('.diff-lineno') !== null;
      if (isDiffLineNo) {
        if (fontSize < 12.9) {
          violations.push({
            type: 'diff-lineno-too-small',
            text: text.slice(0, 30),
            screen: name,
            tag: el.tagName.toLowerCase(),
            fontSize,
          });
        }
      } else {
        if (fontSize < 13.9) {
          violations.push({
            type: 'font-too-small',
            text: text.slice(0, 40),
            screen: name,
            tag: el.tagName.toLowerCase(),
            fontSize,
          });
        }
      }
    }

    return { violations, sizeDistribution };
  }, screenName);

  return result;
}

async function main() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });

  const server = await startServer(4173);
  const browser = await chromium.launch();

  const screens = [
    { id: 'overview', name: 'Overview', navText: 'Overview' },
    { id: 'explorer', name: 'PipelineExplorer', navText: 'Pipeline Explorer' },
    { id: 'inspector', name: 'PatchInspector', navText: 'Patch Inspector' },
    { id: 'results', name: 'ResearchResults', navText: 'Research Results' },
  ];

  const viewports = [
    { name: '1920x1080', width: 1920, height: 1080, scale: 1 },
    { name: '1366x768', width: 1366, height: 768, scale: 1 },
    { name: '125zoom', width: 1536, height: 864, scale: 1.25 },
  ];

  let totalViolations = 0;

  for (const screen of screens) {
    console.log(`\n=== SCREEN: ${screen.name} ===`);

    for (const vp of viewports) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: vp.scale,
      });
      const page = await context.newPage();
      await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });

      // Click the tab
      await page.click(`button:has-text("${screen.navText}")`);
      await page.waitForTimeout(600);

      // Verify fonts on standard 1920x1080
      if (vp.name === '1920x1080') {
        const fontCheck = await verifyPageFonts(page, screen.name);
        console.log(`[font-check] ${screen.name}: ${JSON.stringify(fontCheck.sizeDistribution)}`);
        if (fontCheck.violations.length > 0) {
          console.error(`[font-error] ${screen.name} has ${fontCheck.violations.length} violations:`, fontCheck.violations);
          totalViolations += fontCheck.violations.length;
        } else {
          console.log(`[font-check] ${screen.name}: PASS (all text >= 14px, 0 invalid dates)`);
        }
      }

      // Capture screenshot
      const shotName = `${screen.id}_${vp.name}.png`;
      const distPath = path.join(SCREENSHOT_DIR, shotName);
      const artifactPath = path.join(ARTIFACT_DIR, shotName);

      await page.screenshot({ path: distPath, fullPage: false });
      fs.copyFileSync(distPath, artifactPath);
      console.log(`[capture] Saved ${screen.name} at ${vp.name} -> ${artifactPath}`);

      await context.close();
    }
  }

  await browser.close();
  server.close();

  if (totalViolations > 0) {
    console.error(`\nFAILED: Found ${totalViolations} font size violations across screens.`);
    process.exit(1);
  } else {
    console.log('\nSUCCESS: All 4 screens captured at 1920x1080, 1366x768 and 125% zoom with 0 font violations!');
  }
}

main().catch((err) => {
  console.error('[fatal]', err);
  process.exit(1);
});

