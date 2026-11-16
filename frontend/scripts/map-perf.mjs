/* Замеры производительности карты: features/layers/FPS/memory/load-time.
   Запуск: node scripts/map-perf.mjs  (требует backend на :8000 и dev-сервер :5173).
   Нагрузочный сценарий мокает /map/* синтетическими FeatureCollection (5000 активов). */

import { chromium } from '@playwright/test';

const BASE = process.env.PERF_BASE ?? 'http://localhost:5173';

function gridFC(count, seedOffset = 0) {
  const features = [];
  const bands = ['HIGH_PRIORITY', 'MEDIUM_PRIORITY', 'LOW_PRIORITY', 'NEEDS_REVIEW'];
  for (let i = 0; i < count; i++) {
    const lon = 37.5 + ((i * 0.0037 + seedOffset) % 0.25);
    const lat = 55.68 + ((i * 0.0021 + seedOffset) % 0.14);
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: {
        id: `perf-${i}`,
        asset_type: 'telecom_well',
        display_name: `Perf well ${i}`,
        current_condition: 'ok',
        current_severity: 1,
        current_priority: (i % 100),
        priority_band: bands[i % 4],
        geolocation_status: 'CONFIRMED',
        location_accuracy_m: 4,
        lifecycle_status: 'ACTIVE',
        last_observed_at: '2026-11-10T12:00:00Z',
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

const fpsSample = async (page, ms) =>
  page.evaluate(
    (duration) =>
      new Promise((resolve) => {
        let frames = 0;
        const start = performance.now();
        const loop = (t) => {
          frames++;
          if (t - start < duration) requestAnimationFrame(loop);
          else resolve(Math.round((frames * 1000) / (t - start)));
        };
        requestAnimationFrame(loop);
      }),
    ms,
  );

const heapMB = (page) =>
  page.evaluate(() => {
    const m = performance.memory;
    return m ? Math.round(m.usedJSHeapSize / 1048576) : null;
  });

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const report = {};

  await page.goto(`${BASE}/login`);
  await page.getByLabel('Имя пользователя').fill('demo-operator');
  await page.getByLabel('Пароль').fill('demo-operator-password');
  await page.getByRole('button', { name: 'Войти' }).click();
  await page.waitForURL(/\/app/);

  await page.route('**/api/v1/map/assets**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(gridFC(5000)) }),
  );
  await page.route('**/api/v1/map/defects**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(gridFC(2000, 0.01)) }),
  );
  await page.route('**/api/v1/map/observations**', (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(gridFC(3000, 0.02)) }),
  );

  const t0 = Date.now();
  await page.goto(`${BASE}/app/map`);
  await page.waitForFunction(() => {
    const el = document.querySelector('.map-canvas [role="application"]');
    return el?.__revizorMap?.isStyleLoaded();
  }, { timeout: 30_000 });
  await page.waitForFunction(() => {
    const el = document.querySelector('.map-canvas [role="application"]');
    return el.__revizorMap.querySourceFeatures('assets').length > 0;
  }, { timeout: 30_000 });
  report.loadToMapReadyMs = Date.now() - t0;

  await page.waitForTimeout(2500);
  report.counts = await page.evaluate(() => {
    const map = document.querySelector('.map-canvas [role="application"]').__revizorMap;
    return {
      assetFeatures: map.querySourceFeatures('assets').length,
      renderedAssetPoints: map.queryRenderedFeatures({ layers: ['asset-points'] }).length,
      clusters: map.queryRenderedFeatures({ layers: ['asset-clusters'] }).length,
      styleLayers: map.getStyle().layers.length,
    };
  });
  report.heapIdleMB = await heapMB(page);
  report.fpsIdle = await fpsSample(page, 3000);

  const tiles = await page.evaluate(() => {
    const rs = performance.getEntriesByType('resource').filter((r) => r.name.includes('tiles.openfreemap.org'));
    return { count: rs.length, transferKB: Math.round(rs.reduce((s, r) => s + (r.transferSize || 0), 0) / 1024) };
  });
  report.tiles = tiles;

  await page.locator('.segmented button:has-text("3D")').click();
  const t3d = Date.now();
  await page.waitForFunction(() => {
    const map = document.querySelector('.map-canvas [role="application"]').__revizorMap;
    return map.getPitch() > 40;
  }, { timeout: 10_000 });
  report.modeSwitchMs = Date.now() - t3d;
  await page.waitForTimeout(1500);

  report.fps3dRotation = await page.evaluate(async () => {
    const map = document.querySelector('.map-canvas [role="application"]').__revizorMap;
    let frames = 0;
    const start = performance.now();
    const duration = 3000;
    map.easeTo({ bearing: 180, duration, easing: (t) => t });
    await new Promise((resolve) => {
      const loop = (t) => {
        frames++;
        if (t - start < duration) requestAnimationFrame(loop);
        else resolve();
      };
      requestAnimationFrame(loop);
    });
    return Math.round((frames * 1000) / (performance.now() - start));
  });
  report.heap3dMB = await heapMB(page);

  await page.locator('.layer-toggle:has-text("Гексагоны дефектов")').click();
  await page.waitForFunction(() => {
    const map = document.querySelector('.map-canvas [role="application"]').__revizorMap;
    return map.getLayersOrder().some((id) => id.startsWith('deck-maplibre-layer-group'));
  }, { timeout: 20_000 });
  await page.waitForTimeout(1500);
  report.fpsHexbin3d = await fpsSample(page, 3000);
  report.heapHexbinMB = await heapMB(page);

  console.log(JSON.stringify(report, null, 2));
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
