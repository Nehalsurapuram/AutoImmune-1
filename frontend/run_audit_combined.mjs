/**
 * Starts Vite preview on port 5174, runs the Oxfords audit.mjs against it,
 * writes JSON output, then kills the server.
 * Usage: node run_audit_combined.mjs
 */
import { spawn, execSync } from 'child_process';
import { createServer } from 'http';
import { readFileSync, existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.join(__dirname, 'dist');
const AUDIT_SCRIPT = path.resolve(__dirname, '../.agents/skills/oxfords/skills/oxfords/scripts/audit.mjs');
const OUT_DIR = path.join(DIST, 'oxfords-audit');
const PORT = 5174;

// Start a simple static file server for dist/
const { createReadStream } = await import('fs');
const { extname } = await import('path');
const mime = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.mjs': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
};

const server = createServer((req, res) => {
  let urlPath = req.url.split('?')[0];
  if (urlPath === '/' || !extname(urlPath)) urlPath = '/index.html';
  const filePath = path.join(DIST, urlPath);
  if (!existsSync(filePath)) {
    // SPA fallback
    const idx = path.join(DIST, 'index.html');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    createReadStream(idx).pipe(res);
    return;
  }
  const ext = extname(filePath);
  res.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream' });
  createReadStream(filePath).pipe(res);
});

await new Promise((resolve, reject) => {
  server.listen(PORT, '127.0.0.1', resolve);
  server.on('error', reject);
});
console.log(`Static server listening on http://127.0.0.1:${PORT}`);

// Now run audit.mjs as a child process, forwarding env
let exitCode = 0;
try {
  const env = {
    ...process.env,
    OXFORDS_PLAYWRIGHT: path.join(__dirname, 'node_modules/playwright'),
  };
  const result = execSync(
    `node "${AUDIT_SCRIPT}" "http://127.0.0.1:${PORT}" --out "${OUT_DIR}" --json`,
    { env, encoding: 'utf8', timeout: 120000 }
  );
  console.log(result);
} catch (err) {
  console.error(err.stdout || '');
  console.error(err.stderr || err.message);
  exitCode = 1;
} finally {
  server.close();
}

process.exit(exitCode);

