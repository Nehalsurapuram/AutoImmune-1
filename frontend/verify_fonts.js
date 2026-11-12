import { chromium } from 'playwright';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DIST_DIR = path.join(__dirname, 'dist');

const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
};

function startServer(port = 4174) {
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
      resolve(server);
    });
  });
}

async function verify() {
  const server = await startServer(4174);
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('http://127.0.0.1:4174', { waitUntil: 'networkidle' });

  // Wait for historical runs to render
  await page.waitForSelector('text=Historical Runs', { timeout: 10000 });
  await page.waitForTimeout(500);

  const result = await page.evaluate(() => {
    const violations = [];
    const sizeDistribution = {};
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;

    while ((node = walker.nextNode())) {
      const text = node.textContent?.trim();
      if (!text) continue;
      const el = node.parentElement;
      if (!el) continue;

      // Check visibility
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) continue;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

      const fontSize = parseFloat(style.fontSize);
      const roundedSize = Math.round(fontSize * 10) / 10;
      sizeDistribution[roundedSize] = (sizeDistribution[roundedSize] || 0) + 1;

      // Check for Invalid Date bug
      if (text.includes('Invalid Date')) {
        violations.push({
          type: 'invalid-date',
          text,
          tag: el.tagName.toLowerCase(),
          className: el.className,
          fontSize,
        });
      }

      // Check font size rule:
      // Minimum is 14px everywhere. Diff line numbers are permitted at 13px.
      const isDiffLineNo = el.classList.contains('diff-lineno') || el.closest('.diff-lineno') !== null;
      if (isDiffLineNo) {
        if (fontSize < 12.9) {
          violations.push({
            type: 'diff-lineno-too-small',
            text: text.slice(0, 30),
            tag: el.tagName.toLowerCase(),
            className: el.className,
            fontSize,
          });
        }
      } else {
        if (fontSize < 13.9) {
          violations.push({
            type: 'font-too-small',
            text: text.slice(0, 40),
            tag: el.tagName.toLowerCase(),
            className: el.className,
            fontSize,
          });
        }
      }
    }

    return { violations, sizeDistribution };
  });

  await browser.close();
  server.close();

  console.log('=== FONT SIZE DISTRIBUTION (Computed px) ===');
  const sortedSizes = Object.keys(result.sizeDistribution)
    .map(Number)
    .sort((a, b) => a - b);
  for (const size of sortedSizes) {
    console.log(`  ${size}px: ${result.sizeDistribution[size]} text nodes`);
  }

  console.log('\n=== VIOLATIONS CHECK (< 14px or Invalid Date) ===');
  if (result.violations.length === 0) {
    console.log('SUCCESS: 0 font size violations detected! All text nodes are >= 14px (diff line numbers >= 13px).');
    console.log('SUCCESS: 0 "Invalid Date" strings detected.');
    process.exit(0);
  } else {
    console.error(`FAILED: ${result.violations.length} violations found:`);
    for (const v of result.violations) {
      console.error(`  - [${v.type}] (${v.fontSize}px) <${v.tag} class="${v.className}">: "${v.text}"`);
    }
    process.exit(1);
  }
}

verify().catch((err) => {
  console.error('Verifier error:', err);
  process.exit(1);
});

