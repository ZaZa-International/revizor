/* Demo-провайдер: те же формы ответов, что и live API, поверх синтетического
   датасета. Мутации применяются к demo-хранилищу. Job-обработка симулируется
   таймером и порождает новые наблюдения (всё в пределах DEMO-режима). */
import type {
  AnalyticsOverview,
  Asset,
  AssetMapCollection,
  AssetPatch,
  ConditionHistory,
  CoverageResponse,
  Defect,
  DefectMapCollection,
  DefectPatch,
  DefectsAnalytics,
  FramePage,
  Job,
  JobCreate,
  Observation,
  ObservationMapCollection,
  Page,
  Review,
  ReviewCreate,
  Route,
  RouteCreate,
  RouteMapCollection,
  Upload,
} from '../api/types';
import { ApiError } from '../api/client';
import { demoData, DEMO_USER } from './data';
import { demoFrameDataUrl } from './frames';

const delay = (ms = 160) => new Promise((r) => setTimeout(r, ms));

function paginate<T>(items: T[], page = 1, pageSize = 20): Page<T> {
  const total = items.length;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const p = Math.min(Math.max(1, page), pages);
  return { items: items.slice((p - 1) * pageSize, p * pageSize), total, page: p, page_size: pageSize, pages };
}

type Params = Record<string, string | number | boolean | undefined | null>;

function matchDate(iso: string | null | undefined, from?: string, to?: string): boolean {
  if (!iso) return !from && !to;
  const t = new Date(iso).getTime();
  if (from && t < new Date(from).getTime()) return false;
  if (to && t > new Date(to + 'T23:59:59Z').getTime()) return false;
  return true;
}

function inBbox(lon: number | null | undefined, lat: number | null | undefined, bbox?: string): boolean {
  if (!bbox) return true;
  if (lon == null || lat == null) return false;
  const [minLon, minLat, maxLon, maxLat] = bbox.split(',').map(Number);
  return lon >= minLon && lon <= maxLon && lat >= minLat && lat <= maxLat;
}

function matchDateIso(iso: string | null | undefined, from?: string, to?: string): boolean {
  if (!iso) return !from && !to;
  const t = new Date(iso).getTime();
  if (from && t < new Date(from).getTime()) return false;
  if (to) {
    const toT = new Date(to.length <= 10 ? `${to}T23:59:59Z` : to).getTime();
    if (t > toT) return false;
  }
  return true;
}

function lineInBbox(track: GeoJSON.LineString | null | undefined, bbox?: string): boolean {
  if (!bbox) return true;
  if (!track || track.type !== 'LineString') return false;
  return track.coordinates.some((c) => inBbox(c[0], c[1], bbox));
}

function sortItems<T>(items: T[], sortBy?: string, order?: string): T[] {
  if (!sortBy) return items;
  const dir = order === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortBy];
    const bv = (b as Record<string, unknown>)[sortBy];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });
}

export const demoProvider = {
  async analyticsOverview(): Promise<AnalyticsOverview> {
    await delay();
    const d = demoData;
    const count = <T,>(items: T[], key: (x: T) => string | number) => {
      const m = new Map<string | number, number>();
      items.forEach((x) => m.set(key(x), (m.get(key(x)) ?? 0) + 1));
      return [...m.entries()].map(([k, c]) => ({ key: k, count: c }));
    };
    const reviewed = d.observations.filter((o) => o.review_status !== 'UNREVIEWED').length;
    return {
      assets_total: d.assets.length,
      observations_total: d.observations.length,
      defects_total: d.defects.length,
      uploads_total: d.uploads.length,
      routes_total: d.routes.length,
      observations_reviewed: reviewed,
      observations_reviewed_ratio: d.observations.length ? reviewed / d.observations.length : 0,
      assets_without_location: d.assets.filter((a) => a.geolocation_status === 'UNAVAILABLE').length,
      assets_by_type: count(d.assets, (a) => a.asset_type),
      assets_by_priority_band: count(d.assets, (a) => a.priority_band ?? 'NEEDS_REVIEW'),
      defects_by_status: count(d.defects, (x) => x.status),
      defects_by_severity: count(d.defects, (x) => x.severity ?? 0),
      jobs_by_status: count(d.jobs, (j) => j.status),
    } as AnalyticsOverview;
  },

  async analyticsDefects(): Promise<DefectsAnalytics> {
    await delay();
    const m = new Map<string, { count: number; sevSum: number; confirmed: number }>();
    demoData.defects.forEach((x) => {
      const e = m.get(x.defect_type) ?? { count: 0, sevSum: 0, confirmed: 0 };
      e.count += 1;
      e.sevSum += x.severity ?? 0;
      if (x.status === 'CONFIRMED') e.confirmed += 1;
      m.set(x.defect_type, e);
    });
    return {
      by_type: [...m.entries()].map(([key, e]) => ({
        defect_type: key,
        count: e.count,
        avg_severity: e.count ? e.sevSum / e.count : null,
        confirmed_count: e.confirmed,
      })),
      open_high_severity_count: demoData.defects.filter(
        (x) => ['OPEN', 'CONFIRMED'].includes(x.status) && (x.severity ?? 0) >= 4,
      ).length,
    } as DefectsAnalytics;
  },

  async analyticsCoverage(): Promise<CoverageResponse> {
    await delay();
    const lons = demoData.assets.map((a) => a.longitude).filter((x): x is number => x != null);
    const lats = demoData.assets.map((a) => a.latitude).filter((x): x is number => x != null);
    const area = {
      min_longitude: Math.min(...lons) - 0.01,
      min_latitude: Math.min(...lats) - 0.008,
      max_longitude: Math.max(...lons) + 0.01,
      max_latitude: Math.max(...lats) + 0.008,
    };
    const cellM = 250;
    const mPerDegLon = 111_320 * Math.cos((area.min_latitude * Math.PI) / 180);
    const cols = Math.max(1, Math.ceil(((area.max_longitude - area.min_longitude) * mPerDegLon) / cellM));
    const rows = Math.max(1, Math.ceil(((area.max_latitude - area.min_latitude) * 110_574) / cellM));
    const cells = new Map<string, number>();
    demoData.observations.forEach((o) => {
      if (o.longitude == null || o.latitude == null) return;
      const cx = Math.floor(((o.longitude - area.min_longitude) * mPerDegLon) / cellM);
      const cy = Math.floor(((o.latitude - area.min_latitude) * 110_574) / cellM);
      const k = `${cx},${cy}`;
      cells.set(k, (cells.get(k) ?? 0) + 1);
    });
    const covered = [...cells.entries()].map(([k, n]) => {
      const [cx, cy] = k.split(',').map(Number);
      return { cx, cy, observations: n };
    });
    return {
      area_bbox: area,
      grid_cell_m: cellM,
      grid_cols: cols,
      grid_rows: rows,
      total_cells: cols * rows,
      covered_cells: covered.length,
      coverage_ratio: covered.length / (cols * rows),
      gap_cells: cols * rows - covered.length,
      covered_cell_counts: covered,
      routes: demoData.routes.map((r) => ({
        route_id: r.id,
        name: r.name,
        observations: demoData.observations.filter((o) => o.processing_job_id && demoData.jobs.find((j) => j.id === o.processing_job_id)?.route_id === r.id).length,
      })),
      note: 'демо: эвристическая сетка покрытия, не модель дорожной сети',
    } as CoverageResponse;
  },

  async assets(p: Params = {}): Promise<Page<Asset>> {
    await delay();
    let items = [...demoData.assets];
    if (p.asset_type) items = items.filter((a) => a.asset_type === p.asset_type);
    if (p.priority_band) items = items.filter((a) => a.priority_band === p.priority_band);
    if (p.lifecycle_status) items = items.filter((a) => a.lifecycle_status === p.lifecycle_status);
    if (p.geolocation_status) items = items.filter((a) => a.geolocation_status === p.geolocation_status);
    if (p.search) {
      const q = String(p.search).toLowerCase();
      items = items.filter(
        (a) => a.display_name?.toLowerCase().includes(q) || a.external_id?.toLowerCase().includes(q) || a.id.includes(q),
      );
    }
    if (p.bbox) items = items.filter((a) => inBbox(a.longitude, a.latitude, String(p.bbox)));
    items = items.filter((a) => matchDate(a.created_at, p.date_from as string, p.date_to as string));
    items = sortItems(items, (p.sort_by as string) || 'created_at', p.order as string);
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async asset(id: string): Promise<Asset> {
    await delay();
    const a = demoData.assets.find((x) => x.id === id);
    if (!a) throw new ApiError('not_found', 'Объект не найден', 404);
    return a;
  },

  async patchAsset(id: string, patch: AssetPatch): Promise<Asset> {
    await delay(220);
    const a = demoData.assets.find((x) => x.id === id);
    if (!a) throw new ApiError('not_found', 'Объект не найден', 404);
    if (patch.expected_version !== a.version) {
      throw new ApiError('conflict', 'Версия объекта изменилась. Обновите данные.', 409);
    }
    if (patch.display_name !== undefined) a.display_name = patch.display_name;
    if (patch.external_id !== undefined) a.external_id = patch.external_id;
    if (patch.lifecycle_status != null) a.lifecycle_status = patch.lifecycle_status;
    if (patch.priority_override !== undefined && patch.priority_override !== null) {
      a.priority_override = patch.priority_override;
      a.priority_override_reason = patch.priority_override_reason ?? null;
      a.current_priority = patch.priority_override;
    }
    if (patch.location) {
      a.longitude = patch.location.longitude;
      a.latitude = patch.location.latitude;
      a.geolocation_status = 'CONFIRMED';
    }
    a.version += 1;
    a.updated_at = new Date().toISOString();
    return a;
  },

  async assetHistory(id: string, p: Params = {}): Promise<Page<ConditionHistory>> {
    await delay();
    const items = demoData.history
      .filter((h) => h.asset_id === id)
      .sort((a, b) => (b.detected_at ?? '').localeCompare(a.detected_at ?? ''));
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async assetObservations(id: string, p: Params = {}): Promise<Page<Observation>> {
    return this.observations({ ...p, asset_id: id });
  },

  async assetDefects(id: string, p: Params = {}): Promise<Page<Defect>> {
    return this.defects({ ...p, asset_id: id });
  },

  async observations(p: Params = {}): Promise<Page<Observation>> {
    await delay();
    let items = [...demoData.observations];
    if (p.asset_id) items = items.filter((o) => o.asset_id === p.asset_id);
    if (p.job_id) items = items.filter((o) => o.processing_job_id === p.job_id);
    if (p.object_type) items = items.filter((o) => o.object_type === p.object_type);
    if (p.review_status) items = items.filter((o) => o.review_status === p.review_status);
    if (p.dedup_result) items = items.filter((o) => o.dedup_result === p.dedup_result);
    if (p.bbox) items = items.filter((o) => inBbox(o.longitude, o.latitude, String(p.bbox)));
    items = items.filter((o) => matchDate(o.observed_at, p.date_from as string, p.date_to as string));
    items = sortItems(items, (p.sort_by as string) || 'observed_at', (p.order as string) || 'desc');
    const page = paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
    page.items = page.items.map(withDemoImages);
    return page;
  },

  async observation(id: string): Promise<Observation> {
    await delay();
    const o = demoData.observations.find((x) => x.id === id);
    if (!o) throw new ApiError('not_found', 'Наблюдение не найдено', 404);
    return withDemoImages(o);
  },

  async defects(p: Params = {}): Promise<Page<Defect>> {
    await delay();
    let items = [...demoData.defects];
    if (p.asset_id) items = items.filter((x) => x.asset_id === p.asset_id);
    if (p.status) items = items.filter((x) => x.status === p.status);
    if (p.defect_type) items = items.filter((x) => x.defect_type === p.defect_type);
    if (p.severity_min) items = items.filter((x) => (x.severity ?? 0) >= Number(p.severity_min));
    if (p.severity_max) items = items.filter((x) => (x.severity ?? 0) <= Number(p.severity_max));
    items = items.filter((x) => matchDate(x.created_at, p.date_from as string, p.date_to as string));
    items = sortItems(items, (p.sort_by as string) || 'created_at', (p.order as string) || 'desc');
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async defect(id: string): Promise<Defect> {
    await delay();
    const x = demoData.defects.find((d) => d.id === id);
    if (!x) throw new ApiError('not_found', 'Дефект не найден', 404);
    return x;
  },

  async patchDefect(id: string, patch: DefectPatch): Promise<Defect> {
    await delay(220);
    const x = demoData.defects.find((d) => d.id === id);
    if (!x) throw new ApiError('not_found', 'Дефект не найден', 404);
    if (patch.status != null) x.status = patch.status;
    if (patch.severity !== undefined && patch.severity !== null) x.severity = patch.severity;
    if (patch.description !== undefined) x.description = patch.description;
    x.updated_at = new Date().toISOString();
    return x;
  },

  async reviews(p: Params = {}): Promise<Page<Review>> {
    await delay();
    let items = [...demoData.reviews];
    if (p.observation_id) items = items.filter((r) => r.observation_id === p.observation_id);
    if (p.defect_id) items = items.filter((r) => r.defect_id === p.defect_id);
    if (p.decision) items = items.filter((r) => r.decision === p.decision);
    items = sortItems(items, 'created_at', (p.order as string) || 'desc');
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async createReview(payload: ReviewCreate): Promise<Review> {
    await delay(260);
    const obs = payload.observation_id ? demoData.observations.find((o) => o.id === payload.observation_id) : undefined;
    const defect = payload.defect_id ? demoData.defects.find((d) => d.id === payload.defect_id) : undefined;
    if (!obs && !defect) throw new ApiError('not_found', 'Запись для проверки не найдена', 404);
    if (payload.decision === 'CORRECTED') {
      const hasCorrection =
        payload.corrected_asset_type || payload.corrected_condition || payload.corrected_defect_type || payload.corrected_severity;
      if (!hasCorrection) throw new ApiError('validation_error', 'CORRECTED требует хотя бы одного исправления', 422);
    }
    const review: Review = {
      id: crypto.randomUUID(),
      observation_id: payload.observation_id ?? null,
      defect_id: payload.defect_id ?? null,
      reviewer_id: DEMO_USER.id,
      decision: payload.decision,
      corrected_asset_type: payload.corrected_asset_type ?? null,
      corrected_condition: payload.corrected_condition ?? null,
      corrected_defect_type: payload.corrected_defect_type ?? null,
      corrected_severity: payload.corrected_severity ?? null,
      comment: payload.comment ?? null,
      reviewed_at: payload.reviewed_at ?? new Date().toISOString(),
      created_at: new Date().toISOString(),
    } as Review;
    demoData.reviews.unshift(review);

    if (obs) {
      obs.review_status = payload.decision;
      if (payload.decision === 'CORRECTED') {
        if (payload.corrected_asset_type) obs.effective_asset_type = payload.corrected_asset_type;
        if (payload.corrected_condition) obs.effective_condition = payload.corrected_condition;
        if (payload.corrected_severity) obs.effective_severity = payload.corrected_severity;
      }
      const asset = obs.asset_id ? demoData.assets.find((a) => a.id === obs.asset_id) : undefined;
      if (asset && payload.decision !== 'REJECTED' && payload.decision !== 'NEEDS_MORE_INFORMATION') {
        const condition = obs.effective_condition ?? obs.condition_class;
        const severity = obs.effective_severity ?? obs.severity;
        if (asset.current_condition !== condition || asset.current_severity !== severity) {
          asset.current_condition = condition;
          asset.current_severity = severity;
          asset.version += 1;
          asset.updated_at = new Date().toISOString();
          demoData.history.unshift({
            id: crypto.randomUUID(),
            asset_id: asset.id,
            observation_id: obs.id,
            review_id: review.id,
            change_source: 'HUMAN_REVIEW',
            previous_condition: asset.current_condition,
            new_condition: condition,
            previous_severity: asset.current_severity,
            new_severity: severity,
            previous_priority: asset.current_priority,
            new_priority: asset.current_priority,
            is_physical_change: false,
            note: payload.comment ?? null,
            detected_at: obs.observed_at,
          } as ConditionHistory);
        }
      }
    }
    if (defect) {
      if (payload.decision === 'CONFIRMED') defect.status = 'CONFIRMED';
      if (payload.decision === 'REJECTED') defect.status = 'REJECTED';
      if (payload.decision === 'CORRECTED') {
        if (payload.corrected_severity) defect.severity = payload.corrected_severity;
        if (payload.corrected_defect_type) defect.defect_type = payload.corrected_defect_type;
      }
      defect.updated_at = new Date().toISOString();
    }
    return review;
  },

  async jobs(p: Params = {}): Promise<Page<Job>> {
    await delay();
    let items = [...demoData.jobs];
    if (p.status) items = items.filter((j) => j.status === p.status);
    if (p.upload_id) items = items.filter((j) => j.upload_id === p.upload_id);
    if (p.route_id) items = items.filter((j) => j.route_id === p.route_id);
    items = sortItems(items, 'created_at', (p.order as string) || 'desc');
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async job(id: string): Promise<Job> {
    await delay(120);
    const j = demoData.jobs.find((x) => x.id === id);
    if (!j) throw new ApiError('not_found', 'Задача не найдена', 404);
    return j;
  },

  async jobFrames(id: string, p: Params = {}): Promise<FramePage> {
    await delay();
    const items = demoData.frames.filter((f) => (f as unknown as { job_id: string }).job_id === id).sort((a, b) => a.frame_index - b.frame_index);
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 50) as FramePage;
  },

  async createJob(payload: JobCreate): Promise<Job> {
    await delay(240);
    const upload = demoData.uploads.find((u) => u.id === payload.upload_id);
    if (!upload) throw new ApiError('not_found', 'Загрузка не найдена', 404);
    const existing = demoData.jobs.find((j) => j.upload_id === payload.upload_id && j.status !== 'FAILED' && j.status !== 'CANCELLED');
    if (existing) return existing;
    const job: Job = {
      id: crypto.randomUUID(),
      upload_id: payload.upload_id,
      route_id: payload.route_id ?? upload.route_id ?? null,
      status: 'PROCESSING',
      progress: 0,
      current_stage: 'FRAME_EXTRACTION',
      total_frames: 24,
      processed_frames: 0,
      failed_frames: 0,
      rejected_frames: 0,
      options: { demo: true },
      error_code: null,
      error_message: null,
      created_by: DEMO_USER.id,
      created_at: new Date().toISOString(),
      started_at: new Date().toISOString(),
      finished_at: null,
      updated_at: new Date().toISOString(),
    } as Job;
    demoData.jobs.unshift(job);
    simulateJob(job);
    return job;
  },

  async cancelJob(id: string): Promise<Job> {
    await delay();
    const j = demoData.jobs.find((x) => x.id === id);
    if (!j) throw new ApiError('not_found', 'Задача не найдена', 404);
    if (!['PENDING', 'QUEUED', 'PROCESSING'].includes(j.status)) {
      throw new ApiError('invalid_job_state', 'Задачу нельзя отменить в текущем статусе', 409);
    }
    j.status = 'CANCELLED';
    j.finished_at = new Date().toISOString();
    return j;
  },

  async retryJob(id: string): Promise<Job> {
    await delay();
    const j = demoData.jobs.find((x) => x.id === id);
    if (!j) throw new ApiError('not_found', 'Задача не найдена', 404);
    if (!['FAILED', 'PARTIALLY_COMPLETED', 'CANCELLED'].includes(j.status)) {
      throw new ApiError('invalid_job_state', 'Повтор доступен только для завершённых с ошибкой задач', 409);
    }
    j.status = 'PROCESSING';
    j.progress = 0;
    j.processed_frames = 0;
    j.finished_at = null;
    simulateJob(j);
    return j;
  },

  async uploads(p: Params = {}): Promise<Page<Upload>> {
    await delay();
    let items = [...demoData.uploads];
    if (p.media_type) items = items.filter((u) => u.media_type === p.media_type);
    if (p.route_id) items = items.filter((u) => u.route_id === p.route_id);
    if (p.search) {
      const q = String(p.search).toLowerCase();
      items = items.filter((u) => u.original_filename.toLowerCase().includes(q));
    }
    items = sortItems(items, 'created_at', (p.order as string) || 'desc');
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async createUpload(file: File, routeId?: string): Promise<{ upload: Upload; created: boolean }> {
    await delay(400);
    const upload: Upload = {
      id: crypto.randomUUID(),
      original_filename: file.name,
      storage_key: `uploads/demo/${crypto.randomUUID()}/${file.name}`,
      content_type: file.type || 'application/octet-stream',
      file_size: file.size,
      checksum_sha256: crypto.randomUUID().replace(/-/g, '') + crypto.randomUUID().replace(/-/g, '').slice(0, 32),
      media_type: file.type.startsWith('video') ? 'VIDEO' : 'IMAGE',
      uploaded_by: DEMO_USER.id,
      route_id: routeId ?? null,
      metadata: { demo: true },
      created_at: new Date().toISOString(),
      presigned_url: null,
    } as Upload;
    demoData.uploads.unshift(upload);
    return { upload, created: true };
  },

  async routes(p: Params = {}): Promise<Page<Route>> {
    await delay();
    const items = sortItems([...demoData.routes], 'created_at', (p.order as string) || 'desc');
    return paginate(items, Number(p.page) || 1, Number(p.page_size) || 20);
  },

  async route(id: string): Promise<Route> {
    await delay();
    const r = demoData.routes.find((x) => x.id === id);
    if (!r) throw new ApiError('not_found', 'Маршрут не найден', 404);
    return r;
  },

  async createRoute(payload: RouteCreate): Promise<Route> {
    await delay(240);
    if (!payload.track || payload.track.length < 2) {
      throw new ApiError('validation_error', 'Трек должен содержать минимум 2 точки', 422);
    }
    const route: Route = {
      id: crypto.randomUUID(),
      name: payload.name,
      vehicle_id: payload.vehicle_id ?? null,
      started_at: payload.started_at ?? null,
      finished_at: payload.finished_at ?? null,
      track_geojson: { type: 'LineString', coordinates: payload.track },
      total_distance_m: Math.round(payload.track.length * 180),
      metadata: { demo: true },
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as Route;
    demoData.routes.unshift(route);
    return route;
  },

  async mapAssets(p: Params = {}): Promise<AssetMapCollection> {
    await delay();
    let items = demoData.assets.filter((a) => a.longitude != null && a.latitude != null);
    if (p.asset_type) items = items.filter((a) => a.asset_type === p.asset_type);
    if (p.priority_band) items = items.filter((a) => a.priority_band === p.priority_band);
    if (p.bbox) items = items.filter((a) => inBbox(a.longitude, a.latitude, String(p.bbox)));
    items = sortItems(items, 'current_priority', 'desc');
    return {
      type: 'FeatureCollection',
      features: items.slice(0, Number(p.limit) || 2000).map((a) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [a.longitude!, a.latitude!] },
        properties: {
          id: a.id,
          asset_type: a.asset_type,
          display_name: a.display_name,
          current_condition: a.current_condition,
          current_severity: a.current_severity,
          current_priority: a.current_priority,
          priority_band: a.priority_band,
          geolocation_status: a.geolocation_status,
          location_accuracy_m: a.location_accuracy_m,
          lifecycle_status: a.lifecycle_status,
          last_observed_at: a.last_observed_at,
        },
      })),
    } as AssetMapCollection;
  },

  async mapDefects(p: Params = {}): Promise<DefectMapCollection> {
    await delay();
    const items = demoData.defects
      .map((d) => ({ d, a: demoData.assets.find((x) => x.id === d.asset_id) }))
      .filter((x) => x.a?.longitude != null && x.a?.latitude != null)
      .filter((x) => !p.status || x.d.status === p.status)
      .filter((x) => !p.severity_min || (x.d.severity ?? 0) >= Number(p.severity_min))
      .filter((x) => inBbox(x.a!.longitude, x.a!.latitude, p.bbox as string));
    items.sort((x, y) => (y.d.severity ?? 0) - (x.d.severity ?? 0));
    return {
      type: 'FeatureCollection',
      features: items.map(({ d, a }) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [a!.longitude!, a!.latitude!] },
        properties: {
          id: d.id,
          asset_id: d.asset_id,
          asset_type: a!.asset_type,
          defect_type: d.defect_type,
          severity: d.severity ?? 0,
          status: d.status,
          current_priority: a!.current_priority,
          first_detected_at: d.first_detected_at ?? '',
          last_detected_at: d.last_detected_at ?? '',
        },
      })),
    } as DefectMapCollection;
  },

  async mapObservations(p: Params = {}): Promise<ObservationMapCollection> {
    await delay();
    let items = demoData.observations.filter((o) => o.longitude != null && o.latitude != null);
    if (p.job_id) items = items.filter((o) => o.processing_job_id === p.job_id);
    if (p.bbox) items = items.filter((o) => inBbox(o.longitude, o.latitude, String(p.bbox)));
    items = items.filter((o) => matchDateIso(o.observed_at, p.date_from as string, p.date_to as string));
    items = sortItems(items, 'observed_at', 'desc');
    return {
      type: 'FeatureCollection',
      features: items.slice(0, Number(p.limit) || 2000).map((o) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [o.longitude!, o.latitude!] },
        properties: {
          id: o.id,
          asset_id: o.asset_id,
          object_type: o.object_type,
          condition_class: o.condition_class,
          detector_confidence: o.detector_confidence,
          review_status: o.review_status,
          dedup_result: o.dedup_result,
          observed_at: o.observed_at,
          processing_job_id: o.processing_job_id,
        },
      })),
    } as ObservationMapCollection;
  },

  async mapRoutes(p: Params = {}): Promise<RouteMapCollection> {
    await delay();
    let items = demoData.routes.filter((r) => r.track_geojson);
    if (p.bbox) items = items.filter((r) => lineInBbox(r.track_geojson as GeoJSON.LineString | null, String(p.bbox)));
    items = items.filter((r) => matchDateIso(r.started_at, p.date_from as string, p.date_to as string));
    items = sortItems(items, 'started_at', 'desc');
    return {
      type: 'FeatureCollection',
      features: items.slice(0, Number(p.limit) || 100).map((r) => ({
        type: 'Feature',
        geometry: r.track_geojson!,
        properties: { id: r.id, name: r.name, vehicle_id: r.vehicle_id, started_at: r.started_at, finished_at: r.finished_at, total_distance_m: r.total_distance_m },
      })),
    } as RouteMapCollection;
  },

  async mlHealth() {
    await delay(80);
    return { status: 'ok', model_loaded: true, provider: 'mock', details: { demo: true } };
  },

  async mlModelInfo() {
    await delay(80);
    return { name: 'mock-infrastructure-detector', version: '0.1.0-mock', schema_version: '1.0' };
  },
};

function withDemoImages(o: Observation): Observation {
  return { ...o, image_url: demoFrameDataUrl(o, true), crop_url: demoFrameDataUrl(o, false) };
}

const jobTimers = new Map<string, ReturnType<typeof setInterval>>();

function simulateJob(job: Job): void {
  const stages: NonNullable<Job['current_stage']>[] = ['FRAME_EXTRACTION', 'QUALITY_GATE', 'INFERENCE', 'DEDUPLICATION', 'RISK_SCORING', 'PERSISTENCE', 'COMPLETED'];
  let tick = 0;
  const total = job.total_frames || 24;
  const timer = setInterval(() => {
    if (job.status === 'CANCELLED') {
      clearInterval(timer);
      jobTimers.delete(job.id);
      return;
    }
    tick += 1;
    job.processed_frames = Math.min(total, Math.round((tick / 14) * total));
    job.progress = Math.min(1, tick / 14);
    job.current_stage = stages[Math.min(stages.length - 1, Math.floor((tick / 14) * stages.length))];
    if (tick >= 14) {
      clearInterval(timer);
      jobTimers.delete(job.id);
      job.status = 'COMPLETED';
      job.progress = 1;
      job.current_stage = 'COMPLETED';
      job.finished_at = new Date().toISOString();
      job.rejected_frames = 1;
      job.processed_frames = total - 1;
      generateDemoDetections(job);
    }
  }, 420);
  jobTimers.set(job.id, timer);
}

function generateDemoDetections(job: Job): void {
  const route = demoData.routes.find((r) => r.id === job.route_id);
  const trackCoords = (route?.track_geojson?.coordinates ?? []) as [number, number][];
  const baseLon = trackCoords[0]?.[0] ?? 37.6173;
  const baseLat = trackCoords[0]?.[1] ?? 55.7558;
  const plans: { type: string; condition: string; severity: number; conf: number }[] = [
    { type: 'telecom_well', condition: 'damaged_cover', severity: 4, conf: 0.87 },
    { type: 'telecom_cabinet', condition: 'ok', severity: 1, conf: 0.93 },
    { type: 'pole', condition: 'tilted', severity: 4, conf: 0.79 },
  ];
  plans.forEach((plan, i) => {
    const lon = baseLon + 0.002 + i * 0.0016;
    const lat = baseLat + 0.0008 + i * 0.0005;
    const near = demoData.assets.find(
      (a) => a.asset_type === plan.type && Math.abs((a.longitude ?? 0) - lon) < 0.001 && Math.abs((a.latitude ?? 0) - lat) < 0.001,
    );
    const assetId = near?.id ?? crypto.randomUUID();
    if (!near) {
      demoData.assets.unshift({
        id: assetId,
        external_id: `DEMO-NEW-${assetId.slice(0, 4).toUpperCase()}`,
        asset_type: plan.type,
        display_name: `Новый объект (${plan.type})`,
        longitude: lon,
        latitude: lat,
        location_accuracy_m: 4,
        geolocation_status: 'CONFIRMED',
        current_condition: plan.condition,
        current_severity: plan.severity,
        current_priority: plan.severity * 16,
        priority_band: plan.severity >= 4 ? 'HIGH_PRIORITY' : plan.severity >= 3 ? 'MEDIUM_PRIORITY' : 'LOW_PRIORITY',
        priority_factors: { severity: plan.severity, confidence: plan.conf, computed_priority: plan.severity * 16 },
        priority_policy_version: '1.0',
        priority_override: null,
        priority_override_reason: null,
        lifecycle_status: 'ACTIVE',
        first_observed_at: new Date().toISOString(),
        last_observed_at: new Date().toISOString(),
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Asset);
    }
    const obsId = crypto.randomUUID();
    demoData.observations.unshift({
      id: obsId,
      asset_id: assetId,
      processing_job_id: job.id,
      frame_id: crypto.randomUUID(),
      detection_id: crypto.randomUUID(),
      observed_at: new Date().toISOString(),
      detected_at: new Date().toISOString(),
      object_type: plan.type,
      condition_class: plan.condition,
      detector_confidence: plan.conf,
      classifier_confidence: plan.conf - 0.03,
      severity: plan.severity,
      bbox: { x_min: 500 + i * 200, y_min: 380, x_max: 850 + i * 200, y_max: 700 },
      image_width: 1920,
      image_height: 1080,
      image_id: crypto.randomUUID(),
      crop_image_id: crypto.randomUUID(),
      longitude: lon,
      latitude: lat,
      location_accuracy_m: 4,
      geolocation_status: 'CONFIRMED',
      geolocation_source: 'GPS',
      tracking_id: null,
      model_name: 'mock-infrastructure-detector',
      model_version: '0.1.0-mock',
      dedup_result: near ? 'MATCHED' : 'NEW_ASSET',
      dedup_score: near ? 0.9 : 0,
      dedup_explanation: { reason: near ? 'matched_by_distance_and_type' : 'no_candidates_in_radius', demo: true },
      review_status: 'UNREVIEWED',
      effective_asset_type: plan.type,
      effective_condition: plan.condition,
      effective_severity: plan.severity,
      created_at: new Date().toISOString(),
      image_url: null,
      crop_url: null,
    } as Observation);
    if (plan.condition !== 'ok' && !demoData.defects.some((d) => d.asset_id === assetId && d.defect_type === plan.condition)) {
      demoData.defects.unshift({
        id: crypto.randomUUID(),
        asset_id: assetId,
        defect_type: plan.condition === 'damaged_cover' ? 'damaged_cover' : plan.condition === 'tilted' ? 'pole_tilt' : 'other',
        status: 'OPEN',
        severity: plan.severity,
        description: 'Обнаружено при обработке (демо).',
        first_detected_at: new Date().toISOString(),
        last_detected_at: new Date().toISOString(),
        resolved_at: null,
        observation_count: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as Defect);
    }
  });
}