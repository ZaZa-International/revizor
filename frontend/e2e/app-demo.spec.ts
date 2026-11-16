import { test, expect, type Page } from '@playwright/test';

const errors: string[] = [];

function trackErrors(page: Page) {
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
  });
}

async function enterDemo(page: Page) {
  await page.goto('/login');
  await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText('Синтетические данные для демонстрации')).toBeVisible();
}

test.describe('Command Center · demo-режим', () => {
  test('Overview: KPI и блоки внимания', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await expect(page.locator('.kpi-strip .kpi')).toHaveCount(4);
    await expect(page.locator('.kpi-value').first()).not.toHaveText('—');
    await expect(page.getByRole('heading', { name: 'Требуют внимания' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Дефекты S4–S5' })).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/10-app-overview.png', fullPage: true });
  });

  test('Map: слои, выбор объекта, контекст', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.getByRole('link', { name: 'Карта', exact: true }).first().click();
    await expect(page).toHaveURL(/\/app\/map/);
    await page.waitForTimeout(2500);
    await expect(page.locator('.map-workspace')).toBeVisible();
    await expect(page.getByRole('button', { name: /Объекты \(Asset\)/ })).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/11-app-map.png' });
  });

  test('Assets: реестр → паспорт → вкладки', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.getByRole('link', { name: 'Объекты', exact: true }).first().click();
    await expect(page.locator('.table tbody tr').first()).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/12-app-assets.png' });
    await page.locator('.table tbody tr').first().click();
    await expect(page).toHaveURL(/\/app\/assets\/.+/);
    await expect(page.getByRole('heading', { name: 'Паспорт', exact: true })).toBeVisible();
    await expect(page.getByText('Факторы приоритета')).toBeVisible();
    await page.getByRole('tab', { name: 'История состояния' }).click();
    await expect(page.locator('.table tbody tr').first()).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/13-app-passport.png', fullPage: true });
  });

  test('Reviews: решение CONFIRMED применяется и очередь уменьшается', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.getByRole('link', { name: /Проверка/ }).first().click();
    await expect(page).toHaveURL(/\/app\/reviews/);
    await expect(page.locator('.review-queue-item').first()).toBeVisible();
    const before = await page.locator('.review-queue-item').count();
    expect(before).toBeGreaterThan(0);
    await expect(page.locator('.review-decisions')).toBeVisible();
    await page.getByRole('button', { name: /Подтвердить/ }).first().click();
    await page.getByRole('button', { name: 'Сохранить решение' }).click();
    await expect(page.locator('.toast-success')).toBeVisible();
    await page.waitForTimeout(800);
    const after = await page.locator('.review-queue-item').count();
    expect(after).toBe(before - 1);
    await page.screenshot({ path: 'artifacts/qa/14-app-reviews.png', fullPage: true });
  });

  test('Reviews: CORRECTED требует исправление', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/reviews');
    await expect(page.locator('.review-decisions')).toBeVisible();
    await page.getByRole('button', { name: /Скорректировать/ }).first().click();
    await page.getByRole('button', { name: 'Сохранить решение' }).click();
    await expect(page.getByRole('alert')).toContainText('хотя бы одно исправление');
  });

  test('Jobs: загрузка и симуляция обработки', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/jobs');
    await expect(page.getByRole('heading', { name: 'Новая загрузка' })).toBeVisible();
    const buffer = Buffer.from('fake-jpeg-for-demo-upload');
    await page.locator('input[type=file]').setInputFiles({ name: 'demo-frame.jpg', mimeType: 'image/jpeg', buffer });
    await expect(page.locator('.upload-zone')).toContainText('demo-frame.jpg');
    await page.getByRole('button', { name: 'Загрузить' }).click();
    await expect(page).toHaveURL(/\/app\/jobs\/.+/, { timeout: 15_000 });
    await expect(page.locator('.stage-track')).toBeVisible();
    await expect(page.getByText('Завершена', { exact: false }).first()).toBeVisible({ timeout: 20_000 });
    await page.screenshot({ path: 'artifacts/qa/15-app-job.png', fullPage: true });
  });

  test('Analytics: распределения и покрытие', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/analytics');
    await expect(page.getByRole('heading', { name: 'Объекты по типам' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Покрытие обследования' })).toBeVisible();
    await expect(page.getByText('Методология: группировка')).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/16-app-analytics.png', fullPage: true });
  });

  test('Defects: карточка и смена статуса', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/defects');
    await page.locator('.table tbody tr').first().click();
    await expect(page.getByRole('heading', { name: 'Управление' })).toBeVisible();
    await page.locator('select').first().selectOption('IN_PROGRESS');
    await page.getByRole('button', { name: 'Сохранить изменения' }).click();
    await expect(page.locator('.toast-success')).toBeVisible();
  });

  test('Exports: demo CSV скачивается', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/exports');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Скачать CSV' }).first().click(),
    ]);
    expect(download.suggestedFilename()).toContain('revizor-demo-assets');
  });

  test('Routes: список и создание', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await page.goto('/app/routes');
    await expect(page.locator('.table tbody tr').first()).toBeVisible();
    await page.getByRole('button', { name: /Новый маршрут/ }).click();
    await page.getByLabel('Название').fill('Тестовый объезд');
    await page.getByLabel(/Трек/).fill('[[37.61,55.75],[37.62,55.76]]');
    await page.getByRole('button', { name: 'Создать' }).click();
    await expect(page).toHaveURL(/\/app\/routes\/.+/, { timeout: 10_000 });
  });

  test.afterEach(() => {
    const real = errors.filter((e) => !/favicon|net::ERR|Failed to load resource/i.test(e));
    expect(real, `JS errors: ${real.join('\n')}`).toHaveLength(0);
    errors.length = 0;
  });
});