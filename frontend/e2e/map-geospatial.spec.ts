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
}

async function waitForMap(page: Page) {
  await page.waitForSelector('.map-canvas [role="application"]', { timeout: 20_000 });
  await page.waitForFunction(
    () => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      return !!el?.__revizorMap && el.__revizorMap.isStyleLoaded();
    },
    { timeout: 20_000 },
  );
}

async function openMap(page: Page, query = '') {
  await page.goto(`/app/map${query}`);
  await expect(page.locator('.map-workspace')).toBeVisible();
  await waitForMap(page);
}

async function clickAsset(page: Page): Promise<string> {
  await page.waitForFunction(
    () => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el?.__revizorMap;
      return !!map && map.queryRenderedFeatures({ layers: ['asset-points'] }).length > 0;
    },
    { timeout: 15_000 },
  );
  const pos = await page.evaluate(() => {
    const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
    const map = el.__revizorMap;
    const assets = map.queryRenderedFeatures({ layers: ['asset-points'] });
    if (!assets.length) return null;
    const f = assets[0];
    const p = map.project(f.geometry.coordinates);
    const rect = map.getCanvas().getBoundingClientRect();
    return { id: String(f.properties.id), x: rect.left + p.x, y: rect.top + p.y };
  });
  expect(pos, 'на карте есть несгруппированный актив').not.toBeNull();
  await page.mouse.click(pos!.x, pos!.y);
  await page.waitForTimeout(1200);
  return pos!.id;
}

test.describe('Геопространственная карта · 2D/3D', () => {
  test('2D: векторный basemap, слои, кластеры, легенда S4+', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page);
    await expect(page.locator('.map-canvas canvas')).toBeVisible();
    const info = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      return {
        hasVectorSource: !!map.getSource('openmaptiles'),
        clusters: map.queryRenderedFeatures({ layers: ['asset-clusters'] }).length,
        pitch: map.getPitch(),
      };
    });
    expect(info.hasVectorSource).toBe(true);
    expect(info.pitch).toBe(0);
    await expect(page.getByText('кольцо — дефект S4+')).toBeVisible();
    const tiles = await page.evaluate(() =>
      performance.getEntriesByType('resource').filter((r) => r.name.includes('tiles.openfreemap.org')).length,
    );
    expect(tiles).toBeGreaterThan(0);
    await page.screenshot({ path: '../docs/assets/geospatial/2d-map.png' });
  });

  test('2D → 3D: наклон, здания, выбор не сбрасывается', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page, '?cam=16.50,37.61730,55.75580,0.0,0.0');
    const id = await clickAsset(page);
    await expect(page).toHaveURL(new RegExp(`selected=${id}`));
    await expect(page.locator('.map-context')).toContainText('Паспорт объекта');

    await page.locator('.segmented button:has-text("3D")').click();
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        return el.__revizorMap.getPitch() > 40;
      },
      { timeout: 10_000 },
    );
    await page.waitForTimeout(800);
    const state3d = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      return {
        pitch: map.getPitch(),
        buildings: map.getLayoutProperty('building-3d', 'visibility'),
        buildingFill: map.getLayoutProperty('building', 'visibility'),
        extrusions: map.queryRenderedFeatures({ layers: ['building-3d'] }).length,
      };
    });
    expect(state3d.pitch).toBeGreaterThan(40);
    expect(state3d.buildings).toBe('visible');
    expect(state3d.buildingFill).toBe('none');
    expect(state3d.extrusions).toBeGreaterThan(0);
    await expect(page).toHaveURL(/mode=3d/);
    await expect(page).toHaveURL(new RegExp(`selected=${id}`));
    await expect(page.locator('.map-context')).toContainText('Паспорт объекта');
    await page.screenshot({ path: '../docs/assets/geospatial/3d-selected-asset.png' });

    await page.locator('.segmented button:has-text("2D")').click();
    await page.waitForTimeout(1200);
    await expect(page).toHaveURL(new RegExp(`selected=${id}`));
    const pitch2d = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      return el.__revizorMap.getPitch();
    });
    expect(pitch2d).toBe(0);
  });

  test('deep-link ?selected восстанавливает панель без клика', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page, '?cam=16.50,37.61730,55.75580,0.0,0.0');
    const id = await clickAsset(page);
    const url = page.url();
    await page.goto('about:blank');
    await page.goto(url);
    await waitForMap(page);
    await expect(page.locator('.map-context')).toContainText('Паспорт объекта');
    await expect(page.locator('.map-context .tab').first()).toBeVisible();
  });

  test('фильтры пишутся в URL и сохраняются при 2D↔3D', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page);
    await page.getByLabel('Тип объекта').selectOption('telecom_well');
    await expect(page).toHaveURL(/asset_type=telecom_well/);
    await page.getByLabel('Приоритет').selectOption('HIGH_PRIORITY');
    await expect(page).toHaveURL(/priority_band=HIGH_PRIORITY/);
    await page.locator('.segmented button:has-text("3D")').click();
    await page.waitForTimeout(800);
    await expect(page).toHaveURL(/asset_type=telecom_well/);
    await expect(page).toHaveURL(/priority_band=HIGH_PRIORITY/);
    await expect(page).toHaveURL(/mode=3d/);
    await page.reload();
    await page.waitForTimeout(2500);
    await expect(page.getByLabel('Тип объекта')).toHaveValue('telecom_well');
    await expect(page.getByLabel('Приоритет')).toHaveValue('HIGH_PRIORITY');
  });

  test('Infrastructure view: покрытие, наблюдения, период', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page);
    await page.locator('.map-toolbar select').selectOption('infrastructure');
    await expect(page).toHaveURL(/view=infrastructure/);
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        const map = el.__revizorMap;
        return map.getLayoutProperty('coverage-cells', 'visibility') === 'visible' && map.querySourceFeatures('coverage').length > 0;
      },
      { timeout: 15_000 },
    );
    const layers = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      return {
        coverage: map.getLayoutProperty('coverage-cells', 'visibility'),
        obs: map.getLayoutProperty('obs-points', 'visibility'),
        accuracy: map.getLayoutProperty('accuracy-fill', 'visibility'),
        coverageCells: map.querySourceFeatures('coverage').length,
      };
    });
    expect(layers.coverage).toBe('visible');
    expect(layers.obs).toBe('visible');
    expect(layers.accuracy).toBe('visible');
    expect(layers.coverageCells).toBeGreaterThan(0);
    await expect(page.getByText('Покрытие обследованием')).toBeVisible();
    await expect(page.getByLabel('Дата начала периода')).toBeVisible();
    await page.screenshot({ path: '../docs/assets/geospatial/infrastructure-view.png' });
  });

  test('выбор наблюдения и дефекта открывает инспекцию', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page, '?view=infrastructure&cam=16.50,37.61730,55.75580,0.0,0.0');
    await page.locator('.layer-toggle:has-text("Объекты (Asset)")').click();
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        return el.__revizorMap.queryRenderedFeatures({ layers: ['obs-points'] }).length > 0;
      },
      { timeout: 15_000 },
    );
    const obsPos = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      const obs = map.queryRenderedFeatures({ layers: ['obs-points'] });
      if (!obs.length) return null;
      const p = map.project(obs[0].geometry.coordinates);
      const rect = map.getCanvas().getBoundingClientRect();
      return { x: rect.left + p.x, y: rect.top + p.y };
    });
    expect(obsPos).not.toBeNull();
    await page.mouse.click(obsPos!.x, obsPos!.y);
    await page.waitForTimeout(1200);
    await expect(page).toHaveURL(/layer=observations/);
    await expect(page.locator('.map-context')).toContainText('Confidence модели');
    await expect(page.locator('.map-context')).toContainText('Карточка наблюдения');
    await page.screenshot({ path: '../docs/assets/geospatial/selected-observation.png' });

    await page.locator('.map-toolbar button[aria-label="Сбросить камеру"]').click();
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        return el.__revizorMap.queryRenderedFeatures({ layers: ['defect-rings'] }).length > 0;
      },
      { timeout: 15_000 },
    );
    const defPos = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      const map = el.__revizorMap;
      const defs = map.queryRenderedFeatures({ layers: ['defect-rings'] });
      if (!defs.length) return null;
      const p = map.project(defs[0].geometry.coordinates);
      const rect = map.getCanvas().getBoundingClientRect();
      return { x: rect.left + p.x, y: rect.top + p.y };
    });
    expect(defPos).not.toBeNull();
    await page.mouse.click(defPos!.x, defPos!.y);
    await page.waitForTimeout(1200);
    await expect(page).toHaveURL(/layer=defects/);
    await expect(page.locator('.map-context')).toContainText('Карточка дефекта');
    await page.screenshot({ path: '../docs/assets/geospatial/selected-defect.png' });
  });

  test('гексагональная агрегация deck.gl подключается lazy', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page);
    await page.locator('.layer-toggle:has-text("Гексагоны дефектов")').click();
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        return el.__revizorMap.getLayersOrder().some((id: string) => id.startsWith('deck-maplibre-layer-group'));
      },
      { timeout: 20_000 },
    );
    const groups = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      return el.__revizorMap.getLayersOrder().filter((id: string) => id.startsWith('deck-maplibre-layer-group'));
    });
    expect(groups.length).toBeGreaterThan(0);
    await expect(page).toHaveURL(/hexbin/);
    await page.screenshot({ path: '../docs/assets/geospatial/hexbin-2d.png' });
  });

  test('демо-сценарий: запуск, пауза, шаги, подтверждение, выход', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page);
    await page.locator('.map-toolbar button:has-text("Демо-сценарий")').click();
    await expect(page.locator('.walkthrough-panel')).toBeVisible();
    await expect(page.locator('.walkthrough-title')).toHaveText('3D-карта района');
    await page.locator('.walkthrough-controls button:has-text("Пауза")').click();

    const next = page.locator('.walkthrough-controls button[aria-label="Следующий шаг"]');
    for (let i = 0; i < 6; i++) {
      await next.click();
      await page.waitForTimeout(500);
    }
    await expect(page.locator('.walkthrough-title')).toHaveText('Сравнение объездов');
    await expect(page.locator('.compare-grid')).toBeVisible();
    await page.screenshot({ path: '../docs/assets/geospatial/walkthrough-compare.png' });

    await next.click();
    await page.waitForTimeout(500);
    await expect(page.locator('.walkthrough-title')).toHaveText('Физическое изменение');
    await next.click();
    await expect(page.locator('.walkthrough-title')).toHaveText('Подтверждение оператором');
    await expect(page.locator('.walkthrough-controls')).toContainText('Ожидание действия оператора');
    const confirmBtn = page.locator('.map-context button:has-text("Подтвердить наблюдение")');
    await expect(confirmBtn).toBeVisible({ timeout: 10_000 });
    await confirmBtn.click();
    await expect(page.locator('.walkthrough-title')).toHaveText('История обновлена', { timeout: 10_000 });

    await page.locator('.walkthrough-panel button[aria-label="Выйти из сценария"]').click();
    await expect(page.locator('.walkthrough-panel')).toHaveCount(0);
    await expect(page).not.toHaveURL(/mode=3d/);
  });

  test('сброс камеры возвращает обзор данных', async ({ page }) => {
    trackErrors(page);
    await enterDemo(page);
    await openMap(page, '?cam=17.00,37.61730,55.75580,55.0,-15.0&mode=3d');
    await page.locator('.map-toolbar button[aria-label="Сбросить камеру"]').click();
    await page.waitForFunction(
      () => {
        const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
        return el.__revizorMap.getZoom() < 15;
      },
      { timeout: 10_000 },
    );
    const zoom = await page.evaluate(() => {
      const el = document.querySelector('.map-canvas [role="application"]') as HTMLElement & { __revizorMap?: any };
      return el.__revizorMap.getZoom();
    });
    expect(zoom).toBeLessThan(15);
  });

  test.afterEach(() => {
    const real = errors.filter((e) => !/favicon|net::ERR|Failed to load resource|AbortError: signal is aborted/i.test(e));
    expect(real, `JS errors: ${real.join('\n')}`).toHaveLength(0);
    errors.length = 0;
  });
});
