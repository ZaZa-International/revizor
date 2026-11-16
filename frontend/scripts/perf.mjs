/* Performance-замер: LCP, CLS, long tasks, ресурсы. */
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const BASE = process.env.PERF_BASE ?? 'http://localhost:5173';
const report = {};
const browser = await chromium.launch();

async function measure(path, name, setup) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(() => {
    window.__lcp = 0;
    window.__cls = 0;
    window.__longTasks = [];
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      window.__lcp = entries[entries.length - 1].startTime;
    }).observe({ type: 'largest-contentful-paint', buffered: true });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) if (!e.hadRecentInput) window.__cls += e.value;
    }).observe({ type: 'layout-shift', buffered: true });
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__longTasks.push(Math.round(e.duration));
    }).observe({ type: 'longtask', buffered: true });
  });
  const t0 = Date.now();
  await page.goto(BASE + path, { waitUntil: 'load' });
  if (setup) await setup(page);
  await page.waitForTimeout(3500);
  const metrics = await page.evaluate(() => ({
    lcp: Math.round(window.__lcp),
    cls: +window.__cls.toFixed(4),
    longTasks: window.__longTasks,
    resources: performance.getEntriesByType('resource').length,
    transferKB: Math.round(performance.getEntriesByType('resource').reduce((s, r) => s + (r.transferSize || 0), 0) / 1024),
    heroSrc: document.querySelector('.hero-media img')?.currentSrc ?? null,
    heroNatural: document.querySelector('.hero-media img')?.naturalWidth ?? null,
  }));
  report[name] = { ...metrics, wallMs: Date.now() - t0 };
  await page.close();
}

await measure('/', 'showcase', async (page) => {
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.5));
  await page.waitForTimeout(800);
  await page.evaluate(() => window.scrollTo(0, 0));
});

await measure('/login', 'login');

await measure('/app', 'app-demo', async (page) => {
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await page.waitForTimeout(2000);
});

await measure('/app/map', 'app-map', async (page) => {
  await page.goto(BASE + '/login');
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await page.waitForTimeout(800);
  await page.goto(BASE + '/app/map');
  await page.waitForTimeout(4000);
});

await browser.close();
fs.writeFileSync('artifacts/qa/performance.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));