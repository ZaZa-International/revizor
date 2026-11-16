import { describe, expect, it } from 'vitest';
import { demoData, resetDemoData } from '../demo/data';
import { demoProvider } from '../demo/provider';
import { demoFrameDataUrl } from '../demo/frames';

describe('demo-датасет', () => {
  it('детерминирован: повторная генерация идентична', () => {
    const before = demoData.assets.map((a) => `${a.id}:${a.longitude}:${a.current_condition}`).join('|');
    resetDemoData();
    const after = demoData.assets.map((a) => `${a.id}:${a.longitude}:${a.current_condition}`).join('|');
    expect(after).toBe(before);
  });

  it('координаты в допустимых диапазонах и в демо-зоне Москвы', () => {
    for (const a of demoData.assets) {
      expect(a.longitude).toBeGreaterThan(37.5);
      expect(a.longitude).toBeLessThan(37.7);
      expect(a.latitude).toBeGreaterThan(55.7);
      expect(a.latitude).toBeLessThan(55.8);
    }
  });

  it('все сущности маркированы demo в metadata', () => {
    for (const r of demoData.routes) expect((r.metadata as Record<string, unknown>).demo).toBe(true);
    for (const u of demoData.uploads) expect((u.metadata as Record<string, unknown>).demo).toBe(true);
  });

  it('наблюдения ссылаются на существующие job и asset', () => {
    const jobIds = new Set(demoData.jobs.map((j) => j.id));
    const assetIds = new Set(demoData.assets.map((a) => a.id));
    for (const o of demoData.observations) {
      expect(jobIds.has(o.processing_job_id)).toBe(true);
      if (o.asset_id) expect(assetIds.has(o.asset_id)).toBe(true);
    }
  });

  it('ухудшение состояния отражено в истории (physical change)', () => {
    const worsened = demoData.history.filter((h) => h.is_physical_change);
    expect(worsened.length).toBeGreaterThan(0);
    expect(worsened[0].previous_condition).toBe('damaged_cover');
    expect(worsened[0].new_condition).toBe('missing_cover');
  });

  it('SVG-кадр содержит маркировку синтетики и bbox', () => {
    const obs = demoData.observations[0];
    const url = demoFrameDataUrl(obs, true);
    expect(url.startsWith('data:image/svg+xml')).toBe(true);
    const svg = decodeURIComponent(url.split(',')[1]);
    expect(svg).toContain('СИНТЕТИЧЕСКИЙ КАДР');
    expect(svg).toContain('stroke="#75d7cc"');
  });
});

describe('demo-провайдер: фильтры и пагинация', () => {
  it('assets: фильтр по типу и пагинация', async () => {
    const all = await demoProvider.assets({ page_size: 100 });
    const wells = await demoProvider.assets({ asset_type: 'telecom_well', page_size: 100 });
    expect(wells.total).toBeLessThan(all.total);
    expect(wells.items.every((a) => a.asset_type === 'telecom_well')).toBe(true);
    const page1 = await demoProvider.assets({ page: 1, page_size: 5 });
    const page2 = await demoProvider.assets({ page: 2, page_size: 5 });
    expect(page1.items).toHaveLength(5);
    expect(page1.pages).toBe(Math.ceil(all.total / 5));
    expect(page1.items[0].id).not.toBe(page2.items[0].id);
  });

  it('observations: очередь UNREVIEWED и поиск по asset', async () => {
    const queue = await demoProvider.observations({ review_status: 'UNREVIEWED', page_size: 100 });
    expect(queue.total).toBeGreaterThan(0);
    expect(queue.items.every((o) => o.review_status === 'UNREVIEWED')).toBe(true);
    const assetId = demoData.observations.find((o) => o.asset_id)!.asset_id!;
    const byAsset = await demoProvider.observations({ asset_id: assetId, page_size: 100 });
    expect(byAsset.items.every((o) => o.asset_id === assetId)).toBe(true);
  });

  it('map-слои: только объекты с координатами, GeoJSON [lon,lat]', async () => {
    const fc = await demoProvider.mapAssets({});
    expect(fc.type).toBe('FeatureCollection');
    for (const f of fc.features) {
      expect(f.geometry?.type).toBe('Point');
      const [lon, lat] = (f.geometry?.coordinates ?? []) as number[];
      expect(lon).toBeGreaterThan(37);
      expect(lat).toBeGreaterThan(55);
    }
  });

  it('review CONFIRMED обновляет наблюдение и историю asset', async () => {
    resetDemoData();
    const obs = demoData.observations.find((o) => o.review_status === 'UNREVIEWED' && o.asset_id)!;
    const asset = demoData.assets.find((a) => a.id === obs.asset_id)!;
    const historyBefore = demoData.history.length;
    const review = await demoProvider.createReview({ observation_id: obs.id, decision: 'CONFIRMED', comment: 'unit' });
    expect(review.decision).toBe('CONFIRMED');
    const updated = demoData.observations.find((o) => o.id === obs.id)!;
    expect(updated.review_status).toBe('CONFIRMED');
    if (asset.current_condition !== obs.condition_class) {
      expect(demoData.history.length).toBe(historyBefore + 1);
    }
  });

  it('review CORRECTED без исправлений → 422', async () => {
    const obs = demoData.observations.find((o) => o.review_status === 'UNREVIEWED')!;
    await expect(demoProvider.createReview({ observation_id: obs.id, decision: 'CORRECTED' })).rejects.toMatchObject({
      code: 'validation_error',
      status: 422,
    });
  });

  it('review CORRECTED применяет effective-поля', async () => {
    resetDemoData();
    const obs = demoData.observations.find((o) => o.review_status === 'UNREVIEWED' && o.asset_id)!;
    await demoProvider.createReview({
      observation_id: obs.id,
      decision: 'CORRECTED',
      corrected_condition: 'ok',
      corrected_severity: 1,
    });
    const updated = demoData.observations.find((o) => o.id === obs.id)!;
    expect(updated.effective_condition).toBe('ok');
    expect(updated.effective_severity).toBe(1);
    expect(updated.condition_class).not.toBe('ok');
  });

  it('patchAsset: оптимистичная блокировка по версии', async () => {
    resetDemoData();
    const asset = demoData.assets[0];
    const v0 = asset.version;
    await expect(demoProvider.patchAsset(asset.id, { expected_version: v0 + 5 })).rejects.toMatchObject({
      code: 'conflict',
      status: 409,
    });
    const updated = await demoProvider.patchAsset(asset.id, { expected_version: v0, display_name: 'Новое имя' });
    expect(updated.display_name).toBe('Новое имя');
    expect(updated.version).toBe(v0 + 1);
  });

  it('analyticsOverview считается из данных, а не константа', async () => {
    resetDemoData();
    const o = await demoProvider.analyticsOverview();
    expect(o.assets_total).toBe(demoData.assets.length);
    expect(o.observations_total).toBe(demoData.observations.length);
    const sum = o.assets_by_type.reduce((s, x) => s + x.count, 0);
    expect(sum).toBe(o.assets_total);
  });
});