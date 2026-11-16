import { test, expect, type Page, type Browser } from '@playwright/test';

async function enterDemo(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await expect(page).toHaveURL(/\/app$/);
}

let authStatePromise: Promise<Record<string, unknown>> | null = null;

async function sharedAuthState(browser: Browser): Promise<Record<string, unknown>> {
  if (!authStatePromise) {
    authStatePromise = (async () => {
      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await page.goto('/login');
      await page.getByLabel('Имя пользователя').fill('demo-operator');
      await page.getByLabel('Пароль').fill('demo-operator-password');
      await page.getByRole('button', { name: 'Войти' }).click();
      await page.waitForURL(/\/app/, { timeout: 25_000 });
      const state = await ctx.storageState();
      await ctx.close();
      return state as Record<string, unknown>;
    })();
  }
  return authStatePromise;
}

async function livePage(browser: Browser): Promise<Page> {
  const state = await sharedAuthState(browser);
  const ctx = await browser.newContext({ storageState: state as never });
  const page = await ctx.newPage();
  await page.goto('/app');
  return page;
}

const EMPTY_FC = JSON.stringify({ type: 'FeatureCollection', features: [] });

test.describe('Карта · сценарии отказов', () => {
  test('API 503 на слое активов → ErrorState с retry', async ({ browser }) => {
    const page = await livePage(browser);
    await page.route('**/api/v1/map/assets**', (route) =>
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'storage_unavailable', message: 'Хранилище недоступно', details: [], request_id: 'map-err-1' } }),
      }),
    );
    await page.goto('/app/map');
    await expect(page.getByRole('alert').first()).toContainText('Хранилище недоступно', { timeout: 10_000 });
    await expect(page.getByText('map-err-1')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Повторить загрузку' })).toBeVisible();
    await page.context().close();
  });

  test('пустая выдача слоёв → counts 0, без падений', async ({ browser }) => {
    const page = await livePage(browser);
    await page.route('**/api/v1/map/**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: EMPTY_FC }),
    );
    await page.goto('/app/map');
    await page.waitForTimeout(3000);
    await expect(page.locator('.map-workspace')).toBeVisible();
    await expect(page.locator('.layer-toggle[aria-pressed="true"]').first()).toContainText('0 · вкл');
    await expect(page.locator('.map-context')).toContainText('Выберите объект');
    await page.context().close();
  });

  test('некорректная геометрия отклоняется адаптером, карта жива', async ({ browser }) => {
    const page = await livePage(browser);
    const badFC = JSON.stringify({
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [999, 55.7] }, properties: { id: 'bad-1', asset_type: 'pole', priority_band: 'LOW_PRIORITY' } },
        { type: 'Feature', geometry: null, properties: { id: 'no-gps', asset_type: 'pole', priority_band: 'LOW_PRIORITY' } },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [37.6173, 55.7558] }, properties: { id: 'good-1', asset_type: 'pole', priority_band: 'LOW_PRIORITY', display_name: 'Валидная опора' } },
      ],
    });
    await page.route('**/api/v1/map/assets**', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: badFC }),
    );
    await page.goto('/app/map?cam=16.00,37.61730,55.75580,0.0,0.0');
    await page.waitForTimeout(3500);
    const rendered = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      return map.queryRenderedFeatures({ layers: ['asset-points'] }).map((f: any) => f.properties.id);
    });
    expect(rendered).toContain('good-1');
    expect(rendered).not.toContain('bad-1');
    expect(rendered).not.toContain('no-gps');
    await page.context().close();
  });

  test('потеря WebGL context → schematic fallback', async ({ page }) => {
    await enterDemo(page);
    await page.goto('/app/map');
    await page.waitForTimeout(3500);
    await expect(page.locator('.map-canvas canvas')).toBeVisible();
    await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const gl = el.__revizorMap.painter.context.gl;
      const ext = gl.getExtension('WEBGL_lose_context');
      if (ext) ext.loseContext();
    });
    await page.waitForTimeout(1500);
    await expect(page.locator('.map-canvas svg[role="application"]')).toBeVisible();
    await expect(page.getByText('Схематичный режим')).toBeVisible();
  });

  test('timeout сети на слое → ErrorState, повтор восстанавливает', async ({ browser }) => {
    const page = await livePage(browser);
    let failed = true;
    await page.route('**/api/v1/map/routes**', (route) => {
      if (failed) return route.abort('timedout');
      return route.continue();
    });
    await page.goto('/app/map');
    await expect(page.getByRole('alert').first()).toBeVisible({ timeout: 15_000 });
    failed = false;
    await page.getByRole('button', { name: 'Повторить загрузку' }).click();
    await expect(page.locator('.layer-toggle:has-text("Маршруты")')).toContainText('вкл', { timeout: 15_000 });
    await page.context().close();
  });
});
