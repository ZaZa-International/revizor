import { test, expect, type Page } from '@playwright/test';

const errors: string[] = [];

function trackErrors(page: Page) {
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
  });
}

async function loginLive(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Имя пользователя').fill('demo-operator');
  await page.getByLabel('Пароль').fill('demo-operator-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await expect(page).toHaveURL(/\/app/, { timeout: 15_000 });
}

test.describe('Command Center · live API @live', () => {
  test('login → overview с реальными агрегатами', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await expect(page.getByText('Синтетические данные для демонстрации')).toHaveCount(0);
    await expect(page.locator('.kpi-value').first()).not.toHaveText('—');
    await expect(page.locator('.kpi-value').first()).not.toHaveText('0');
    await page.screenshot({ path: 'artifacts/qa/20-live-overview.png', fullPage: true });
  });

  test('assets: реестр и паспорт из API', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await page.goto('/app/assets');
    await expect(page.locator('.table tbody tr').first()).toBeVisible({ timeout: 15_000 });
    const count = await page.locator('.table tbody tr').count();
    expect(count).toBeGreaterThan(0);
    await page.locator('.table tbody tr').first().click();
    await expect(page.getByRole('heading', { name: 'Паспорт', exact: true })).toBeVisible();
    await expect(page.getByText('Факторы приоритета')).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/21-live-passport.png', fullPage: true });
  });

  test('map: GeoJSON-слои загружаются', async ({ page }) => {
    trackErrors(page);
    const mapResponses: string[] = [];
    page.on('response', (res) => {
      if (res.url().includes('/api/v1/map/')) mapResponses.push(res.url());
    });
    await loginLive(page);
    await page.goto('/app/map');
    await page.waitForTimeout(3000);
    expect(mapResponses.some((u) => u.includes('/map/assets'))).toBeTruthy();
    await expect(page.locator('.map-workspace')).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/22-live-map.png' });
  });

  test('reviews: реальное решение CONFIRMED через API', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await page.goto('/app/reviews');
    await expect(page.locator('.review-queue-item').first()).toBeVisible({ timeout: 15_000 });
    const before = await page.locator('.review-queue-item').count();
    const reviewPromise = page.waitForResponse((r) => r.url().includes('/api/v1/reviews') && r.request().method() === 'POST');
    await page.getByRole('button', { name: /Подтвердить/ }).first().click();
    await page.getByRole('button', { name: 'Сохранить решение' }).click();
    const reviewRes = await reviewPromise;
    expect(reviewRes.status()).toBeLessThan(300);
    await expect(page.locator('.toast-success')).toBeVisible();
    await page.waitForTimeout(1200);
    const after = await page.locator('.review-queue-item').count();
    expect(after).toBeLessThan(before);
    await page.screenshot({ path: 'artifacts/qa/23-live-reviews.png', fullPage: true });
  });

  test('jobs: реальная загрузка и обработка', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await page.goto('/app/jobs');
    await page.locator('input[type=file]').setInputFiles('e2e/fixtures/survey-frame.jpg');
    await expect(page.locator('.upload-zone')).toContainText('survey-frame.jpg');
    await page.getByRole('button', { name: 'Загрузить' }).click();
    await expect(page).toHaveURL(/\/app\/jobs\/.+/, { timeout: 30_000 });
    await expect(page.locator('.stage-track')).toBeVisible();
    await expect(page.getByText(/Завершена|Частично завершена|Ошибка/).first()).toBeVisible({ timeout: 60_000 });
    await page.screenshot({ path: 'artifacts/qa/24-live-job.png', fullPage: true });
  });

  test('analytics и exports из API', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await page.goto('/app/analytics');
    await expect(page.getByRole('heading', { name: 'Объекты по типам' })).toBeVisible();
    await page.goto('/app/exports');
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'Скачать CSV' }).first().click(),
    ]);
    expect(download.suggestedFilename()).toContain('assets');
  });

  test('logout отзывает сессию', async ({ page }) => {
    trackErrors(page);
    await loginLive(page);
    await page.getByRole('button', { name: /Выйти/ }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto('/app');
    await expect(page).toHaveURL(/\/login/);
  });

  test.afterEach(() => {
    const real = errors.filter((e) => !/favicon|net::ERR|Failed to load resource|401|404|AbortError: signal is aborted/i.test(e));
    expect(real, `JS errors: ${real.join('\n')}`).toHaveLength(0);
    errors.length = 0;
  });
});