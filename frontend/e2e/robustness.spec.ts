import { test, expect, type Page } from '@playwright/test';

async function enterDemo(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test.describe('Надёжность и fallback', () => {
  test('отказ WebGL → интерактивная SVG-схема, выбор работает', async ({ page }) => {
    await page.addInitScript(() => {
      const orig = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
        if (type === 'webgl' || type === 'webgl2' || type === 'experimental-webgl') return null;
        return orig.call(this, type, ...(args as []));
      } as typeof orig;
    });
    await enterDemo(page);
    await page.goto('/app/map');
    await page.waitForTimeout(1500);
    await expect(page.locator('.map-canvas svg[role="application"]')).toBeVisible();
    await expect(page.getByText('Схематичный режим · без базовой карты')).toBeVisible();
    const points = page.locator('.map-canvas svg g[role="button"]');
    expect(await points.count()).toBeGreaterThan(0);
    await points.first().click();
    await expect(page.locator('.map-context')).toContainText('Паспорт объекта');
    await page.screenshot({ path: 'artifacts/qa/30-svg-fallback.png' });
  });

  test('отказ тайлов basemap → raster fallback → schematic', async ({ page }) => {
    await page.route('**/tiles.openfreemap.org/**', (route) => route.abort());
    await page.route('**/server.arcgisonline.com/**', (route) => route.abort());
    await enterDemo(page);
    await page.goto('/app/map');
    await page.waitForTimeout(8000);
    const canvas = await page.locator('.map-canvas canvas').count();
    const svg = await page.locator('.map-canvas svg[role="application"]').count();
    expect(canvas + svg).toBeGreaterThan(0);
    if (svg > 0) {
      await expect(page.getByText('Схематичный режим')).toBeVisible();
    }
    await page.screenshot({ path: 'artifacts/qa/31-tile-fallback.png' });
  });

  test('ошибка API → ErrorState с retry (live)', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Имя пользователя').fill('demo-operator');
    await page.getByLabel('Пароль').fill('demo-operator-password');
    await page.getByRole('button', { name: 'Войти' }).click();
    await expect(page).toHaveURL(/\/app/);
    await page.route('**/api/v1/analytics/overview', (route) =>
      route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'storage_unavailable', message: 'Хранилище недоступно', details: [], request_id: 'test-req-1' } }) }),
    );
    await page.goto('/app');
    await expect(page.getByRole('alert')).toContainText('Хранилище недоступно');
    await expect(page.getByText('test-req-1')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Повторить' })).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/32-error-state.png' });
    await page.unroute('**/api/v1/analytics/overview');
    await page.getByRole('button', { name: 'Повторить' }).click();
    await expect(page.locator('.kpi-strip')).toBeVisible({ timeout: 10_000 });
  });

  test('пустой результат фильтра → EmptyState', async ({ page }) => {
    await enterDemo(page);
    await page.goto('/app/assets?search=несуществующий-объект-xyz');
    await expect(page.getByRole('heading', { name: 'Объекты не найдены' })).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/33-empty-state.png' });
  });

  test('конфликт версий 409 при PATCH показывается оператору', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Имя пользователя').fill('demo-operator');
    await page.getByLabel('Пароль').fill('demo-operator-password');
    await page.getByRole('button', { name: 'Войти' }).click();
    await expect(page).toHaveURL(/\/app/);
    await page.goto('/app/assets');
    await page.locator('.table tbody tr').first().click();
    await expect(page.getByRole('heading', { name: 'Паспорт', exact: true })).toBeVisible();
    await page.route('**/api/v1/assets/*', (route) => {
      if (route.request().method() === 'PATCH') {
        return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: { code: 'conflict', message: 'Версия объекта изменилась. Обновите данные.', details: [], request_id: 'conflict-1' } }) });
      }
      return route.continue();
    });
    await page.getByRole('button', { name: 'Редактировать' }).click();
    await page.getByLabel('Название').fill('Конфликтное имя');
    await page.getByRole('button', { name: 'Сохранить' }).click();
    await expect(page.getByRole('alert')).toContainText('Версия объекта изменилась');
    await page.screenshot({ path: 'artifacts/qa/34-conflict.png' });
  });

  test('клавиатура: Tab-фокус видим, Enter открывает строку реестра', async ({ page }) => {
    await enterDemo(page);
    await page.goto('/app/assets');
    await expect(page.locator('.table tbody tr').first()).toBeVisible();
    await page.locator('.table tbody tr').first().focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/app\/assets\/.+/);
    await page.goto('/app');
    await expect(page.locator('.kpi-strip')).toBeVisible();
    await page.keyboard.press('Tab');
    const outline = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      const s = getComputedStyle(el);
      return { tag: el.tagName, width: s.outlineWidth, style: s.outlineStyle };
    });
    expect(outline.style).not.toBe('none');
  });

  test('прямые URL и reload сохраняют состояние', async ({ page }) => {
    await enterDemo(page);
    await page.goto('/app/assets');
    await page.locator('.table tbody tr').first().click();
    const url = page.url();
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Паспорт', exact: true })).toBeVisible();
    expect(page.url()).toBe(url);
    await page.goto('/app/reviews');
    await expect(page.locator('.review-queue-item').first()).toBeVisible();
    const obsUrl = page.url();
    await page.reload();
    await expect(page.locator('.review-decisions')).toBeVisible();
    expect(page.url()).toBe(obsUrl);
  });

  test('тайлы basemap реально загружаются (live-карта)', async ({ page }) => {
    await enterDemo(page);
    await page.goto('/app/map');
    await page.waitForTimeout(4500);
    const tiles = await page.evaluate(() =>
      performance.getEntriesByType('resource').filter((r) => r.name.includes('tiles.openfreemap.org')).length,
    );
    const canvas = await page.locator('.map-canvas canvas').count();
    if (canvas > 0) expect(tiles).toBeGreaterThan(0);
  });

  test('demo/live переключение не смешивает данные', async ({ page }) => {
    await enterDemo(page);
    await expect(page.getByText('Синтетические данные для демонстрации')).toBeVisible();
    await page.getByRole('button', { name: 'Подключиться к серверу' }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.getByLabel('Имя пользователя').fill('demo-operator');
    await page.getByLabel('Пароль').fill('demo-operator-password');
    await page.getByRole('button', { name: 'Войти' }).click();
    await expect(page).toHaveURL(/\/app/);
    await expect(page.getByText('Синтетические данные для демонстрации')).toHaveCount(0);
    await expect(page.locator('.shell-topbar-actions')).toContainText('LIVE API');
  });
});