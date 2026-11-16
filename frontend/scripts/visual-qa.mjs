/* Программный визуальный QA: метрики композиции, контраст, типографика,
   scrub-сцена, карта, фокус. Скриншоты — в artifacts/qa для человеческого просмотра. */
import { chromium } from '@playwright/test';
import fs from 'node:fs';

const BASE = 'http://localhost:5173';
const OUT = 'artifacts/qa';
fs.mkdirSync(OUT, { recursive: true });

function luminance(hex) {
  const c = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(c.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(fg, bg) {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

const report = { contrast: {}, typography: {}, composition: {}, scrub: {}, map: {}, focus: {}, errors: [] };

const TOKEN_PAIRS = [
  ['ink on bg', '#E9EEE9', '#091318', 4.5],
  ['muted on surface', '#A0B3B5', '#102129', 4.5],
  ['faint on bg', '#7D959B', '#091318', 4.5],
  ['accent on bg', '#75D7CC', '#091318', 4.5],
  ['warn on bg', '#F0A45C', '#091318', 4.5],
  ['crit on bg', '#E66C61', '#091318', 4.5],
  ['ok on bg', '#9DBFA8', '#091318', 4.5],
  ['accent-ink on accent', '#06231F', '#75D7CC', 4.5],
  ['paper-ink on paper', '#14232B', '#F2F3EF', 4.5],
  ['paper-muted on paper', '#4E6268', '#F2F3EF', 4.5],
  ['paper-accent on paper', '#0E6E62', '#F2F3EF', 4.5],
  ['control-border on surface', '#55707A', '#102129', 3],
];

for (const [name, fg, bg, min] of TOKEN_PAIRS) {
  const ratio = contrast(fg, bg);
  report.contrast[name] = { ratio: +ratio.toFixed(2), min, pass: ratio >= min };
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on('pageerror', (e) => report.errors.push(`pageerror: ${e.message}`));
page.on('console', (m) => {
  if (m.type() === 'error' && !/favicon|net::ERR|Failed to load resource/i.test(m.text())) report.errors.push(m.text());
});

await page.goto(BASE + '/');
await page.waitForTimeout(3200);

report.typography = await page.evaluate(() => {
  const cs = (sel) => {
    const el = document.querySelector(sel);
    return el ? getComputedStyle(el).fontFamily : null;
  };
  return {
    heroTitle: cs('.hero-title'),
    body: cs('.hero-sub'),
    coords: cs('.hero-coords'),
    oswaldLoaded: document.fonts.check('600 48px Oswald'),
    plexLoaded: document.fonts.check('400 15px "IBM Plex Sans"'),
    monoLoaded: document.fonts.check('500 13px "JetBrains Mono"'),
    heroTitleSize: getComputedStyle(document.querySelector('.hero-title')).fontSize,
  };
});

report.composition.hero = await page.evaluate(() => {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const rect = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const title = rect('.hero-title');
  const cta = rect('.hero-cta');
  const coords = rect('.hero-coords');
  const overlap = (a, b) => a && b && a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
  return {
    viewport: { vw, vh },
    title,
    cta,
    coords,
    titleInViewport: title && title.x >= 0 && title.y >= 0 && title.x + title.w <= vw,
    ctaVisible: cta && cta.y + cta.h <= vh,
    titleCoordsOverlap: overlap(title, coords),
    ctaCoordsOverlap: overlap(cta, coords),
    imgComplete: document.querySelector('.hero-media img')?.complete ?? false,
    imgNaturalWidth: document.querySelector('.hero-media img')?.naturalWidth ?? 0,
  };
});
await page.screenshot({ path: `${OUT}/qa1-hero-1440.png` });

report.scrub = await page.evaluate(async () => {
  const track = document.querySelector('.net-track');
  const start = track.getBoundingClientRect().top + window.scrollY;
  const photo = document.querySelector('.net-photo');
  const before = getComputedStyle(photo).opacity;
  window.scrollTo(0, start + window.innerHeight * 1.4);
  await new Promise((r) => setTimeout(r, 1400));
  const after = getComputedStyle(photo).opacity;
  const netPaths = [...document.querySelectorAll('.net-svg path')];
  const drawn = netPaths.filter((p) => parseFloat(getComputedStyle(p).strokeDashoffset || '0') < 0.5).length;
  window.scrollTo(0, start + window.innerHeight * 2.2);
  await new Promise((r) => setTimeout(r, 1400));
  const statValue = document.querySelector('.net-stat-value')?.textContent;
  const cap3 = getComputedStyle(document.querySelectorAll('.net-caption')[2]).opacity;
  window.scrollTo(0, 0);
  return { photoOpacityBefore: before, photoOpacityMid: after, pathsDrawn: drawn, totalPaths: netPaths.length, statValueAtEnd: statValue, caption3OpacityAtEnd: cap3 };
});
await page.evaluate(() => {
  const track = document.querySelector('.net-track');
  window.scrollTo(0, track.getBoundingClientRect().top + window.scrollY + window.innerHeight * 1.5);
});
await page.waitForTimeout(1300);
await page.screenshot({ path: `${OUT}/qa1-network-scrub-1440.png` });

await page.locator('#pipeline').scrollIntoViewIfNeeded();
await page.waitForTimeout(900);
report.composition.pipeline = await page.evaluate(() => {
  const steps = [...document.querySelectorAll('.pipeline-step')];
  const inView = steps.filter((s) => s.classList.contains('in-view')).length;
  const bg = getComputedStyle(document.querySelector('.pipeline-section')).backgroundColor;
  return { steps: steps.length, inView, lightBackground: bg };
});
await page.screenshot({ path: `${OUT}/qa1-pipeline-1440.png` });

await page.locator('#twin').scrollIntoViewIfNeeded();
await page.waitForTimeout(4000);
report.map = await page.evaluate(() => {
  const canvas = document.querySelector('.twin-map canvas');
  const svgFallback = document.querySelector('.twin-map svg[role="application"]');
  const attrib = document.querySelector('.twin-map .maplibregl-ctrl-attrib')?.textContent ?? '';
  return {
    webglCanvas: !!canvas,
    canvasSize: canvas ? { w: canvas.width, h: canvas.height } : null,
    svgFallback: !!svgFallback,
    attribution: attrib.slice(0, 80),
    demoBadge: document.querySelector('.twin-map .badge')?.textContent ?? '',
  };
});
const tileRequests = [];
page.on('response', (r) => {
  if (r.url().includes('server.arcgisonline.com')) tileRequests.push(r.status());
});
await page.waitForTimeout(2500);
report.map.tileStatuses = tileRequests.slice(0, 12);
await page.screenshot({ path: `${OUT}/qa1-twin-1440.png` });

await page.locator('#scenario').scrollIntoViewIfNeeded();
await page.waitForTimeout(700);
await page.screenshot({ path: `${OUT}/qa1-scenario-1440.png` });
await page.locator('#platform').scrollIntoViewIfNeeded();
await page.waitForTimeout(2200);
await page.screenshot({ path: `${OUT}/qa1-platform-1440.png` });
await page.locator('.final').scrollIntoViewIfNeeded();
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/qa1-final-1440.png` });

report.focus = await page.evaluate(() => {
  const link = document.querySelector('.sc-nav-cta a');
  link.focus();
  const s = getComputedStyle(link);
  return { outlineWidth: s.outlineWidth, outlineColor: s.outlineColor, outlineStyle: s.outlineStyle };
});

await page.goto(BASE + '/login');
await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/qa1-app-overview-1440.png`, fullPage: true });
for (const [path, name] of [['/app/map', 'map'], ['/app/assets', 'assets'], ['/app/reviews', 'reviews'], ['/app/jobs', 'jobs'], ['/app/analytics', 'analytics'], ['/app/defects', 'defects'], ['/app/routes', 'routes'], ['/app/exports', 'exports'], ['/app/observations', 'observations']]) {
  await page.goto(BASE + path);
  await page.waitForTimeout(path === '/app/map' ? 3500 : 1300);
  await page.screenshot({ path: `${OUT}/qa1-app-${name}-1440.png`, fullPage: path !== '/app/map' });
}

await page.setViewportSize({ width: 390, height: 844 });
await page.goto(BASE + '/');
await page.waitForTimeout(2500);
await page.screenshot({ path: `${OUT}/qa1-hero-390.png` });
await page.goto(BASE + '/app');
await page.waitForTimeout(1500);
await page.screenshot({ path: `${OUT}/qa1-app-overview-390.png`, fullPage: true });
await page.goto(BASE + '/app/map');
await page.waitForTimeout(3000);
await page.screenshot({ path: `${OUT}/qa1-app-map-390.png` });

await browser.close();
fs.writeFileSync(`${OUT}/visual-qa-cycle1.json`, JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));