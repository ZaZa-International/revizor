/* Программный визуальный аудит: геометрия, переполнения, контраст реального
   текста, типографика, состояния компонентов. Скриншоты — для человеческого ревью.
   Запуск: node scripts/visual-audit.mjs [before|after] */
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const BASE = process.env.AUDIT_BASE ?? 'http://localhost:5173';
const TAG = process.argv[2] ?? 'before';
const OUT = `artifacts/audit-${TAG}`;
fs.mkdirSync(OUT, { recursive: true });

const report = { tag: BASE, pages: {}, showcase: {}, probes: {}, errors: [] };

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => report.errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error') report.errors.push(m.text().slice(0, 200));
});

const AUDIT_FN = () => {
  const lum = (rgb) => {
    const [r, g, b] = rgb.map((v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const parse = (c) => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map((s) => parseFloat(s));
    return { rgb: p.slice(0, 3), a: p.length > 3 ? p[3] : 1 };
  };
  const effBg = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
      const bg = parse(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0.85) return bg.rgb;
      node = node.parentElement;
    }
    return [9, 19, 24];
  };
  const contrast = (fg, bg) => {
    const l1 = lum(fg);
    const l2 = lum(bg);
    const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
    return (hi + 0.05) / (lo + 0.05);
  };

  const overflow = [];
  const vw = document.documentElement.clientWidth;
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.position === 'fixed' || cs.visibility === 'hidden' || cs.display === 'none') continue;
    if (el.closest('.table-wrap, .tabs, .scenario-rail, .shell-mobile-nav, .maplibregl-map')) continue;
    let clipped = false;
    let anc = el.parentElement;
    while (anc && anc !== document.body) {
      const ox = getComputedStyle(anc).overflowX;
      if (ox === 'hidden' || ox === 'auto' || ox === 'scroll') { clipped = true; break; }
      anc = anc.parentElement;
    }
    if (clipped) continue;
    if (r.right > vw + 2 || r.left < -2) {
      overflow.push({ tag: el.tagName, cls: String(el.className).slice(0, 60), right: Math.round(r.right), vw });
      if (overflow.length > 8) break;
    }
  }

  const lowContrast = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  let n;
  while ((n = walker.nextNode())) {
    const text = n.textContent.trim();
    if (!text || text.length < 2) continue;
    const el = n.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.bottom < 0 || r.top > window.innerHeight * 3) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.5) continue;
    if (el.closest('svg, .maplibregl-map, button[disabled], .hero-media')) continue;
    const fg = parse(cs.color);
    if (!fg || fg.a < 0.5) continue;
    const size = parseFloat(cs.fontSize);
    const weight = parseInt(cs.fontWeight, 10);
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const ratio = contrast(fg.rgb, effBg(el));
    const min = large ? 3 : 4.5;
    if (ratio < min) {
      lowContrast.push({ text: text.slice(0, 40), cls: String(el.className).slice(0, 50), ratio: +ratio.toFixed(2), min, size, color: cs.color });
      if (lowContrast.length > 15) break;
    }
  }

  const fonts = {
    oswald600: document.fonts.check('600 48px Oswald'),
    plex400: document.fonts.check('400 15px "IBM Plex Sans"'),
    mono500: document.fonts.check('500 13px "JetBrains Mono"'),
    mono600: document.fonts.check('600 13px "JetBrains Mono"'),
  };

  return {
    scrollW: document.documentElement.scrollWidth,
    vw,
    overflow,
    lowContrast,
    fonts,
    h1: document.querySelector('h1')?.textContent?.trim().slice(0, 60) ?? null,
  };
};

async function auditPage(path, name, { wait = 1400, fullPage = true, width = 1440, height = 900 } = {}) {
  await page.setViewportSize({ width, height });
  await page.goto(BASE + path);
  await page.waitForTimeout(wait);
  const data = await page.evaluate(AUDIT_FN);
  await page.screenshot({ path: `${OUT}/${name}-${width}.png`, fullPage: fullPage && width > 500 });
  report.pages[`${name}@${width}`] = data;
}

await page.goto(BASE + '/login');
await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
await page.waitForTimeout(1200);

const APP_PAGES = [
  ['/app', 'overview'],
  ['/app/map', 'map', 4000, false],
  ['/app/assets', 'assets'],
  ['/app/observations', 'observations'],
  ['/app/defects', 'defects'],
  ['/app/reviews', 'reviews'],
  ['/app/jobs', 'jobs'],
  ['/app/routes', 'routes'],
  ['/app/analytics', 'analytics'],
  ['/app/exports', 'exports'],
];
for (const [path, name, wait, full] of APP_PAGES) {
  await auditPage(path, name, { wait: wait ?? 1400, fullPage: full ?? true });
}

await page.goto(BASE + '/app/assets');
await page.waitForTimeout(1200);
const firstRow = page.locator('.table-wrap tbody tr').first();
if (await firstRow.count()) {
  await firstRow.click();
  await page.waitForTimeout(1600);
  report.pages['passport@1440'] = await page.evaluate(AUDIT_FN);
  await page.screenshot({ path: `${OUT}/passport-1440.png`, fullPage: true });
}

await page.goto(BASE + '/app/reviews');
await page.waitForTimeout(1400);
const queueItem = page.locator('.review-queue-item').first();
if (await queueItem.count()) {
  await queueItem.click();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${OUT}/reviews-card-1440.png`, fullPage: true });
}

await page.goto(BASE + '/app/jobs');
await page.waitForTimeout(1200);
const jobRow = page.locator('.table-wrap tbody tr').first();
if (await jobRow.count()) {
  await jobRow.click();
  await page.waitForTimeout(1400);
  report.pages['job-detail@1440'] = await page.evaluate(AUDIT_FN);
  await page.screenshot({ path: `${OUT}/job-detail-1440.png`, fullPage: true });
}

await page.goto(BASE + '/');
await page.waitForTimeout(2800);
report.showcase.hero = await page.evaluate(AUDIT_FN);
await page.screenshot({ path: `${OUT}/showcase-hero-1440.png` });
for (const [sel, name, wait] of [
  ['#network', 'showcase-network', 1800],
  ['#pipeline', 'showcase-pipeline', 1200],
  ['#twin', 'showcase-twin', 4200],
  ['#scenario', 'showcase-scenario', 1000],
  ['#platform', 'showcase-platform', 2600],
  ['.final', 'showcase-final', 1000],
]) {
  const loc = page.locator(sel).first();
  if (await loc.count()) {
    if (sel === '#network') {
      await page.evaluate(() => {
        const t = document.querySelector('.net-track');
        window.scrollTo(0, t.getBoundingClientRect().top + window.scrollY + window.innerHeight * 1.6);
      });
    } else {
      await loc.scrollIntoViewIfNeeded();
    }
    await page.waitForTimeout(wait);
    await page.screenshot({ path: `${OUT}/${name}-1440.png` });
  }
}

report.probes.columnChartText = await page.evaluate(() => {
  const charts = [...document.querySelectorAll('.col-chart')];
  if (charts.length === 0) return 'no ColumnChart on current page';
  return charts.map((c) => {
    const px = (sel) => {
      const el = c.querySelector(sel);
      return el ? { font: getComputedStyle(el).fontSize, text: el.textContent.slice(0, 12) } : null;
    };
    return { bars: c.querySelectorAll('.col-chart-bar').length, tick: px('.col-chart-tick'), value: px('.col-chart-val'), xlabel: px('.col-chart-xlabel') };
  });
});

await page.goto(BASE + '/app/analytics');
await page.waitForTimeout(1600);
report.probes.columnChartText = await page.evaluate(() => {
  const charts = [...document.querySelectorAll('.col-chart')];
  return charts.map((c) => {
    const px = (sel) => {
      const el = c.querySelector(sel);
      return el ? { font: getComputedStyle(el).fontSize, text: el.textContent.slice(0, 12) } : null;
    };
    return { bars: c.querySelectorAll('.col-chart-bar').length, tick: px('.col-chart-tick'), value: px('.col-chart-val'), xlabel: px('.col-chart-xlabel') };
  });
});

await page.goto(BASE + '/app/assets');
await page.waitForTimeout(1400);
report.probes.sortKeyboard = await page.evaluate(() => {
  const ths = [...document.querySelectorAll('th.sortable')];
  return ths.map((th) => ({ text: th.textContent.trim().slice(0, 20), hasButton: !!th.querySelector('button.th-sort'), ariaSort: th.getAttribute('aria-sort') }));
});

await page.goto(BASE + '/app/assets');
await page.waitForTimeout(1200);
const firstAsset = page.locator('.table-wrap tbody tr').first();
if (await firstAsset.count()) {
  await firstAsset.click();
  await page.waitForTimeout(1500);
  report.probes.tabs = await page.evaluate(() => {
    const tabs = [...document.querySelectorAll('[role="tab"]')];
    return tabs.map((t) => ({ text: t.textContent.trim().slice(0, 20), tabindex: t.tabIndex, controls: t.getAttribute('aria-controls') }));
  });
  const activeTab = page.locator('[role="tab"][aria-selected="true"]');
  if (await activeTab.count()) {
    await activeTab.focus();
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(400);
    report.probes.tabArrowKey = await page.evaluate(() => document.querySelector('[role="tab"][aria-selected="true"]')?.textContent?.trim());
  }
}

await page.goto(BASE + '/app/reviews');
await page.waitForTimeout(1400);
const qItem = page.locator('.review-queue-item').first();
if (await qItem.count()) {
  await qItem.click();
  await page.waitForTimeout(600);
  await page.locator('.decision-btn:has-text("Подтвердить")').first().click();
  await page.locator('button:has-text("Сохранить решение")').click();
  await page.waitForTimeout(900);
  report.probes.toast = await page.evaluate(() => {
    const t = document.querySelector('.toast');
    return { present: !!t, hasClose: !!t?.querySelector('.toast-close'), text: t?.textContent?.slice(0, 60) };
  });
  const closeBtn = page.locator('.toast .toast-close').first();
  if (await closeBtn.count()) {
    await closeBtn.click();
    await page.waitForTimeout(300);
    report.probes.toastDismissed = await page.evaluate(() => !document.querySelector('.toast'));
  }
}

for (const [path, name] of [['/', 'showcase-hero'], ['/app', 'overview'], ['/app/map', 'map'], ['/app/assets', 'assets'], ['/app/reviews', 'reviews'], ['/app/analytics', 'analytics']]) {
  await auditPage(path, name, { width: 390, height: 844, wait: path === '/app/map' ? 3500 : 1500, fullPage: false });
}

await browser.close();
fs.writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 2));
const issues = Object.entries(report.pages).flatMap(([k, v]) => [
  ...v.overflow.map((o) => `${k}: overflow ${o.cls} right=${o.right}/${o.vw}`),
  ...v.lowContrast.map((c) => `${k}: contrast ${c.ratio}<${c.min} "${c.text}" (${c.cls})`),
]);
console.log(JSON.stringify({ issues, errors: report.errors, probes: report.probes }, null, 2));