import { chromium } from 'playwright';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');
const DIST_DIR = path.join(REPO_ROOT, 'frontend', 'dist');
const SCREENSHOT_DIR = path.join(DIST_DIR, 'screenshots');
const ARTIFACT_DIR = 'C:\\Users\\Pradeep S\\.gemini\\antigravity\\brain\\cb462d28-18de-4a84-83e8-8ee7945a664f';

// Simple static server
const MIME_TYPES = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
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
    } catch (e) {
      res.writeHead(404);
      res.end('Not found');
    }
  });

  return new Promise((resolve) => {
    server.listen(port, '127.0.0.1', () => {
      console.log(`Server listening on http://127.0.0.1:${port}`);
      resolve(server);
    });
  });
}

async function capture() {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });

  const server = await startServer(4173);
  const browser = await chromium.launch();

  const viewports = [
    { name: '1920x1080', width: 1920, height: 1080 },
    { name: '1366x768', width: 1366, height: 768 },
    { name: '1440x900', width: 1440, height: 900 },
  ];

  for (const vp of viewports) {
    const page = await browser.newPage();
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });
    
    // Wait for the app and data to render
    await page.waitForSelector('text=Historical Runs', { timeout: 10000 });
    await page.waitForTimeout(500);

    const shotName = `pipeline_explorer_${vp.name}.png`;
    const distPath = path.join(SCREENSHOT_DIR, shotName);
    const artifactPath = path.join(ARTIFACT_DIR, shotName);

    await page.screenshot({ path: distPath, fullPage: false });
    fs.copyFileSync(distPath, artifactPath);
    console.log(`Captured ${vp.name} screenshot: ${distPath}`);

    await page.close();
  }

  await browser.close();
  server.close();
  console.log('Finished capturing all screenshots.');
}

capture().catch((err) => {
  console.error('Capture error:', err);
  process.exit(1);
});

