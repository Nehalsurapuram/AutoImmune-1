import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';
import { chromium } from 'playwright';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');
const DIST_DIR = path.join(REPO_ROOT, 'frontend', 'dist');
const ARTIFACT_DIR = 'C:\\Users\\Pradeep S\\.gemini\\antigravity\\brain\\cb462d28-18de-4a84-83e8-8ee7945a664f';

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

function runCommand(cmd, args, env) {
  return new Promise((resolve, reject) => {
    console.log(`[exec] ${cmd} ${args.join(' ')}`);
    const proc = spawn(cmd, args, { env, stdio: 'inherit' });
    proc.on('close', (code) => {
      if (code === 0) resolve(code);
      else reject(new Error(`Process exited with code ${code}`));
    });
  });
}

async function captureScreenshots() {
  console.log('[capture] Capturing high-resolution actual-size screenshots...');
  const browser = await chromium.launch();

  const viewports = [
    { name: '1920x1080', width: 1920, height: 1080 },
    { name: '1366x768', width: 1366, height: 768 },
  ];

  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });

  for (const vp of viewports) {
    const page = await browser.newPage();
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle' });
    await page.waitForSelector('text=Historical Runs', { timeout: 10000 });
    await page.waitForTimeout(600);

    const artifactPath = path.join(ARTIFACT_DIR, `pipeline_explorer_${vp.name}.png`);
    await page.screenshot({ path: artifactPath, fullPage: false });
    console.log(`[capture] Saved ${vp.name} to ${artifactPath}`);
    await page.close();
  }

  await browser.close();
}

async function main() {
  const server = await startServer(4173);
  const shootPath = path.join(REPO_ROOT, '.agents', 'skills', 'oxfords', 'skills', 'oxfords', 'scripts', 'shoot.mjs');
  const auditPath = path.join(REPO_ROOT, '.agents', 'skills', 'oxfords', 'skills', 'oxfords', 'scripts', 'audit.mjs');
  const env = {
    ...process.env,
    OXFORDS_PLAYWRIGHT: path.join(REPO_ROOT, 'frontend', 'node_modules', 'playwright'),
  };

  try {
    // 1. Capture exact 1920x1080 and 1366x768 screenshots
    await captureScreenshots();

    // 2. Run shoot.mjs at 1366 and 1920
    console.log('\n--- RUNNING OXFORDS shoot.mjs at 1366 and 1920 ---');
    await runCommand('node', [
      shootPath,
      'http://127.0.0.1:4173',
      '--widths', '1366,1920',
      '--schemes', 'light',
      '--out', path.join(DIST_DIR, 'oxfords-shots'),
    ], env);

    // 3. Run audit.mjs on http://127.0.0.1:4173
    console.log('\n--- RUNNING OXFORDS audit.mjs ---');
    await runCommand('node', [
      auditPath,
      'http://127.0.0.1:4173',
      '--out', path.join(DIST_DIR, 'oxfords-audit'),
    ], env);

    console.log('\nAll Oxfords checks and captures completed successfully.');
  } finally {
    server.close();
  }
}

main().catch((err) => {
  console.error('[error]', err);
  process.exit(1);
});
