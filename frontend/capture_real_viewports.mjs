/**
 * Capture all 4 screens at real browser viewport sizes:
 * 1904×960, 1350×650, 1536×730
 * Also checks for horizontal scroll and font sizes under 14px.
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BASE = 'http://127.0.0.1:5174';
const OUT = 'C:/Users/Pradeep S/.gemini/antigravity/brain/cb462d28-18de-4a84-83e8-8ee7945a664f';

const VIEWPORTS = [
  { width: 1904, height: 960, label: '1904x960' },
  { width: 1350, height: 650, label: '1350x650' },
  { width: 1536, height: 730, label: '1536x730' },
];

const SCREENS = [
  { hash: '', tab: 'overview',  label: 'overview'  },
  { hash: '', tab: 'explorer',  label: 'explorer'  },
  { hash: '', tab: 'inspector', label: 'inspector' },
  { hash: '', tab: 'results',   label: 'results'   },
];

const TAB_MAP = {
  overview:  0,
  explorer:  1,
  inspector: 2,
  results:   3,
};

async function checkHScroll(page) {
  return page.evaluate(() =>
    document.documentElement.scrollWidth > document.documentElement.clientWidth
  );
}

async function checkFonts(page) {
  return page.evaluate(() => {
    const violations = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) {
      const style = window.getComputedStyle(node);
      const size = parseFloat(style.fontSize);
      // Allow 13px only for diff line numbers (.diff-lineno class)
      const minAllowed = node.classList.contains('diff-lineno') ? 13 : 14;
      if (size < minAllowed && node.textContent.trim().length > 0) {
        const text = node.textContent.trim().slice(0, 40);
        const selector = node.tagName.toLowerCase() + (node.className ? '.' + [...node.classList].slice(0,2).join('.') : '');
        violations.push(`${size}px on <${selector}>: "${text}"`);
      }
    }
    return violations.slice(0, 10);
  });
}

const browser = await chromium.launch({ headless: true });

const results = [];

for (const vp of VIEWPORTS) {
  for (const screen of SCREENS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 30000 });

    // Click the right nav tab
    const navButtons = await page.locator('header nav button').all();
    const idx = TAB_MAP[screen.tab];
    if (navButtons[idx]) {
      await navButtons[idx].click();
      await page.waitForTimeout(600);
    }

    const hscroll = await checkHScroll(page);
    const fontViolations = await checkFonts(page);

    const fname = `${screen.label}_${vp.label}.png`;
    const fpath = path.join(OUT, fname);
    await page.screenshot({ path: fpath, fullPage: false });

    results.push({
      screen: screen.label,
      viewport: vp.label,
      hscroll,
      fontViolations: fontViolations.length,
      fontDetails: fontViolations,
      screenshot: fname,
    });

    console.log(`${screen.label} @ ${vp.label}: hscroll=${hscroll} fonts_under14=${fontViolations.length}`);
    if (hscroll) console.error(`  !! HORIZONTAL SCROLL at ${vp.label} on ${screen.label}`);
    if (fontViolations.length) {
      fontViolations.forEach(v => console.error(`  !! FONT: ${v}`));
    }

    await context.close();
  }
}

await browser.close();

// Summary
console.log('\n=== SUMMARY ===');
const fails = results.filter(r => r.hscroll || r.fontViolations > 0);
if (fails.length === 0) {
  console.log('ALL PASS: 0 horizontal scroll, 0 font violations');
} else {
  fails.forEach(r => {
    if (r.hscroll) console.error(`FAIL: hscroll on ${r.screen} @ ${r.viewport}`);
    if (r.fontViolations) console.error(`FAIL: ${r.fontViolations} font violations on ${r.screen} @ ${r.viewport}`);
  });
}
console.log(`\nCaptures written to: ${OUT}`);
results.forEach(r => console.log(`  ${r.screenshot}`));
