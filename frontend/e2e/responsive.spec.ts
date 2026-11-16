import { test, expect, type Page } from '@playwright/test';

const WIDTHS = [360, 375, 390, 768, 1024, 1280, 1440, 1920];

const PAGES = [
  { path: '/', name: 'showcase' },
  { path: '/app', name: 'overview' },
  { path: '/app/map', name: 'map' },
  { path: '/app/assets', name: 'assets' },
  { path: '/app/reviews', name: 'reviews' },
  { path: '/app/jobs', name: 'jobs' },
  { path: '/app/analytics', name: 'analytics' },
  { path: '/app/exports', name: 'exports' },
];

async function enterDemo(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test.describe('Responsive: без горизонтального переполнения', () => {
  for (const width of WIDTHS) {
    test(`ширина ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: width < 768 ? 844 : 900 });
      await enterDemo(page);
      const problems: string[] = [];
      for (const p of PAGES) {
        await page.goto(p.path);
        await page.waitForTimeout(p.path === '/' ? 1500 : 900);
        const overflow = await page.evaluate(() => {
          const doc = document.documentElement;
          const bad: string[] = [];
          if (doc.scrollWidth > doc.clientWidth + 1) {
            bad.push(`document scrollWidth ${doc.scrollWidth} > ${doc.clientWidth}`);
          }
          const inScrollContainer = (el: Element) => {
            let p = el.parentElement;
            while (p && p !== document.body) {
              const s = getComputedStyle(p);
              if (['auto', 'scroll', 'hidden'].includes(s.overflowX)) return true;
              p = p.parentElement;
            }
            return false;
          };
          document.querySelectorAll('body *').forEach((el) => {
            if (el.closest('svg')) return;
            const r = el.getBoundingClientRect();
            if (r.width > 0 && (r.right > doc.clientWidth + 2 || r.left < -2)) {
              const style = getComputedStyle(el);
              if (style.position === 'fixed') return;
              if (inScrollContainer(el)) return;
              const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ')[0] : el.tagName;
              bad.push(`${cls} right=${Math.round(r.right)} left=${Math.round(r.left)}`);
            }
          });
          return bad.slice(0, 6);
        });
        if (overflow.length) problems.push(`${p.name}: ${overflow.join('; ')}`);
      }
      await page.screenshot({ path: `artifacts/qa/responsive-${width}-overview.png` });
      expect(problems, problems.join('\n')).toHaveLength(0);
    });
  }
});

test.describe('Mobile: навигация и действия', () => {
  test('компактная навигация на 390px', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await enterDemo(page);
    await expect(page.locator('.shell-mobile-bar')).toBeVisible();
    await expect(page.locator('.shell-rail')).toBeHidden();
    const navLinks = page.locator('.shell-mobile-nav a');
    await expect(navLinks).toHaveCount(10);
    await navLinks.filter({ hasText: 'Проверка' }).click();
    await expect(page).toHaveURL(/\/app\/reviews/);
    await expect(page.locator('.review-decisions')).toBeVisible({ timeout: 10_000 });
    await page.screenshot({ path: 'artifacts/qa/mobile-390-reviews.png', fullPage: true });
  });

  test('карта на мобильном: сначала карта, панели ниже', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await enterDemo(page);
    await page.goto('/app/map');
    await page.waitForTimeout(2500);
    const canvasBox = await page.locator('.map-canvas').boundingBox();
    const sideBox = await page.locator('.map-side').boundingBox();
    expect(canvasBox).not.toBeNull();
    expect(sideBox).not.toBeNull();
    expect(canvasBox!.y).toBeLessThan(sideBox!.y);
    await page.screenshot({ path: 'artifacts/qa/mobile-390-map.png', fullPage: true });
  });
});