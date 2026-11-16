import { test, expect, type Page } from '@playwright/test';

const errors: string[] = [];

function trackErrors(page: Page) {
  page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(`console: ${msg.text()}`);
  });
}

test.describe('Public Showcase', () => {
  test('hero и сцены рендерятся без ошибок JS', async ({ page }) => {
    trackErrors(page);
    await page.goto('/');
    await expect(page.locator('.hero-title')).toContainText('Городская сеть');
    await expect(page.locator('.hero-title')).toContainText('Под наблюдением');
    await expect(page.getByRole('link', { name: /Открыть платформу/ }).first()).toBeVisible();
    await page.screenshot({ path: 'artifacts/qa/01-hero.png' });

    for (const id of ['network', 'pipeline', 'twin', 'scenario', 'platform']) {
      await expect(page.locator(`#${id}`)).toBeAttached();
    }
    await expect(page.locator('.pipeline-step')).toHaveCount(8);
    await expect(page.locator('.scenario-step-btn')).toHaveCount(6);
    await expect(page.locator('.preview-card')).toHaveCount(3);
    await expect(page.locator('.final-title')).toContainText('Управляйте состоянием инфраструктуры');
  });

  test('прокрутка сцен и скриншоты', async ({ page }) => {
    trackErrors(page);
    await page.goto('/');
    await page.waitForTimeout(1200);

    await page.locator('#network').scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollBy(0, window.innerHeight * 1.2));
    await page.waitForTimeout(900);
    await page.screenshot({ path: 'artifacts/qa/02-network-mid.png' });

    await page.locator('#pipeline').scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await page.screenshot({ path: 'artifacts/qa/03-pipeline.png' });

    await page.locator('#twin').scrollIntoViewIfNeeded();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: 'artifacts/qa/04-twin-map.png' });

    await page.locator('#scenario').scrollIntoViewIfNeeded();
    await page.waitForTimeout(700);
    await page.screenshot({ path: 'artifacts/qa/05-scenario.png' });

    await page.locator('#platform').scrollIntoViewIfNeeded();
    await page.waitForTimeout(1800);
    await page.screenshot({ path: 'artifacts/qa/06-platform-preview.png' });

    await page.locator('.final').scrollIntoViewIfNeeded();
    await page.waitForTimeout(700);
    await page.screenshot({ path: 'artifacts/qa/07-final-cta.png' });
  });

  test('сценарий: шаги и решение оператора', async ({ page }) => {
    trackErrors(page);
    await page.goto('/');
    await page.locator('#scenario').scrollIntoViewIfNeeded();
    await page.getByRole('button', { name: /Решение оператора/ }).click();
    await expect(page.getByRole('button', { name: /Подтвердить дефект/ })).toBeVisible();
    await page.getByRole('button', { name: /Подтвердить дефект/ }).click();
    await expect(page.locator('.scenario-visual')).toContainText('CONFIRMED');
    await page.getByRole('button', { name: /История состояния/ }).click();
    await expect(page.locator('.scenario-visual')).toContainText('HUMAN_REVIEW');
  });

  test('CTA ведёт в /app (демо-режим)', async ({ page }) => {
    trackErrors(page);
    await page.goto('/');
    await page.locator('.final').scrollIntoViewIfNeeded();
    await page.getByRole('button', { name: 'Демо-режим без сервера' }).click();
    await expect(page).toHaveURL(/\/app$/);
    await expect(page.locator('.shell-topbar-title')).toContainText('Обзор инфраструктуры');
    await expect(page.getByText('Синтетические данные для демонстрации')).toBeVisible();
  });

  test('reduced motion: статичная сцена, функции доступны', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    trackErrors(page);
    await page.goto('/');
    await expect(page.locator('.hero-title')).toBeVisible();
    const trackHeight = await page.locator('.net-track').evaluate((el) => el.getBoundingClientRect().height);
    const stageHeight = await page.locator('.net-stage').evaluate((el) => el.getBoundingClientRect().height);
    expect(trackHeight).toBeLessThan(stageHeight + 4);
    await expect(page.locator('.net-caption').last()).toContainText('Revizor делает сеть видимой');
    await page.screenshot({ path: 'artifacts/qa/08-reduced-motion.png' });
  });

  test('прямой переход в /app без сессии → login', async ({ page }) => {
    trackErrors(page);
    await page.goto('/app');
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Демо-режим без сервера' })).toBeVisible();
  });

  test.afterEach(() => {
    const real = errors.filter((e) => !/favicon|404|net::ERR|Failed to load resource/i.test(e));
    expect(real, `JS errors: ${real.join('\n')}`).toHaveLength(0);
    errors.length = 0;
  });
});