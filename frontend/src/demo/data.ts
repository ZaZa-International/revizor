/* Детерминированный синтетический DEMO-датасет.
   Все данные искусственные; координаты условны (центр Москвы как демо-зона).
   Формы ответов зеркалят OpenAPI-контракт. Используется ТОЛЬКО в явно
   включённом demo-режиме и в публичной демонстрации showcase. */
import type {
  Asset,
  ConditionHistory,
  Defect,
  Job,
  JobFrame,
  Observation,
  Review,
  Route,
  Upload,
} from '../api/types';

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let rng = mulberry32(20261115);

function uuid(): string {
  const hex = '0123456789abcdef';
  let out = '';
  for (let i = 0; i < 36; i++) {
    if (i === 8 || i === 13 || i === 18 || i === 23) out += '-';
    else if (i === 14) out += '4';
    else if (i === 19) out += hex[(Math.floor(rng() * 16) & 0x3) | 0x8];
    else out += hex[Math.floor(rng() * 16)];
  }
  return out;
}

const ANCHOR = Date.UTC(2026, 10, 15, 12, 0, 0);
const iso = (offsetMinutes: number) => new Date(ANCHOR + offsetMinutes * 60_000).toISOString();

export const DEMO_USER = {
  id: uuid(),
  username: 'demo-operator',
  email: 'demo-operator@revizor.example',
  role: 'OPERATOR' as const,
  is_active: true,
  created_at: iso(-60 * 24 * 30),
};

interface RoutePlan {
  name: string;
  vehicle: string;
  startLon: number;
  startLat: number;
  endLon: number;
  endLat: number;
  offsetMin: number;
}

const ROUTE_PLANS: RoutePlan[] = [
  { name: 'Объезд А — Тверской район', vehicle: 'МГТС-001', startLon: 37.6095, startLat: 55.7548, endLon: 37.6255, endLat: 55.7582, offsetMin: -60 * 24 * 14 },
  { name: 'Объезд Б — Арбат', vehicle: 'МГТС-002', startLon: 37.5895, startLat: 55.7478, endLon: 37.6008, endLat: 55.7503, offsetMin: -60 * 24 * 14 + 180 },
  { name: 'Объезд В — Пресня', vehicle: 'МГТС-001', startLon: 37.5598, startLat: 55.7618, endLon: 37.5752, endLat: 55.7652, offsetMin: -60 * 24 * 5 },
];

type AssetType = 'telecom_well' | 'pole' | 'telecom_cabinet' | 'cable_line';

interface AssetPlan {
  type: AssetType;
  condition: string;
  severity: number;
  confidence: number;
  route: number;
  t: number;
  worsened?: boolean;
}

const ASSET_PLANS: AssetPlan[] = [
  { type: 'telecom_well', condition: 'damaged_cover', severity: 4, confidence: 0.91, route: 0, t: 0.12 },
  { type: 'telecom_well', condition: 'missing_cover', severity: 5, confidence: 0.88, route: 0, t: 0.28, worsened: true },
  { type: 'telecom_well', condition: 'ok', severity: 1, confidence: 0.95, route: 0, t: 0.44 },
  { type: 'telecom_well', condition: 'subsided', severity: 4, confidence: 0.72, route: 0, t: 0.61 },
  { type: 'pole', condition: 'tilted', severity: 4, confidence: 0.85, route: 0, t: 0.74 },
  { type: 'pole', condition: 'ok', severity: 1, confidence: 0.96, route: 0, t: 0.88 },
  { type: 'telecom_cabinet', condition: 'door_open', severity: 3, confidence: 0.89, route: 1, t: 0.15 },
  { type: 'telecom_cabinet', condition: 'damaged', severity: 3, confidence: 0.81, route: 1, t: 0.38 },
  { type: 'telecom_cabinet', condition: 'ok', severity: 1, confidence: 0.94, route: 1, t: 0.62 },
  { type: 'telecom_well', condition: 'ok', severity: 1, confidence: 0.93, route: 1, t: 0.81 },
  { type: 'cable_line', condition: 'cable_sag', severity: 3, confidence: 0.77, route: 2, t: 0.2 },
  { type: 'cable_line', condition: 'ok', severity: 1, confidence: 0.92, route: 2, t: 0.47 },
  { type: 'pole', condition: 'damaged', severity: 3, confidence: 0.58, route: 2, t: 0.66 },
  { type: 'pole', condition: 'ok', severity: 1, confidence: 0.9, route: 2, t: 0.85 },
  { type: 'telecom_well', condition: 'damaged_cover', severity: 3, confidence: 0.62, route: 2, t: 0.95 },
  { type: 'telecom_cabinet', condition: 'ok', severity: 1, confidence: 0.97, route: 0, t: 0.52 },
];

const CONDITION_DEFECT: Record<string, string> = {
  damaged_cover: 'damaged_cover',
  missing_cover: 'missing_cover',
  door_open: 'cabinet_door_open',
  tilted: 'pole_tilt',
  subsided: 'well_subsidence',
  cable_sag: 'cable_sag',
  cable_break: 'cable_break',
  damaged: 'other',
};

const STREET_NAMES = [
  'Тверская ул.',
  'Большая Никитская ул.',
  'ул. Арбат',
  'Смоленская ул.',
  'ул. Красная Пресня',
  'Звенигородское ш.',
];

export interface DemoData {
  routes: Route[];
  uploads: Upload[];
  jobs: Job[];
  frames: JobFrame[];
  assets: Asset[];
  observations: Observation[];
  defects: Defect[];
  reviews: Review[];
  history: ConditionHistory[];
}

function build(): DemoData {
  rng = mulberry32(20261115);
  const routes: Route[] = [];
  const uploads: Upload[] = [];
  const jobs: Job[] = [];
  const frames: JobFrame[] = [];
  const assets: Asset[] = [];
  const observations: Observation[] = [];
  const defects: Defect[] = [];
  const reviews: Review[] = [];
  const history: ConditionHistory[] = [];

  const routeIds: string[] = [];
  const jobIds: string[] = [];

  ROUTE_PLANS.forEach((plan, ri) => {
    const routeId = uuid();
    routeIds.push(routeId);
    const track: [number, number][] = [];
    for (let i = 0; i <= 12; i++) {
      const t = i / 12;
      track.push([
        plan.startLon + (plan.endLon - plan.startLon) * t + (rng() - 0.5) * 0.0006,
        plan.startLat + (plan.endLat - plan.startLat) * t + (rng() - 0.5) * 0.0004,
      ]);
    }
    const startedAt = iso(plan.offsetMin);
    const finishedAt = iso(plan.offsetMin + 95);
    routes.push({
      id: routeId,
      name: plan.name,
      vehicle_id: plan.vehicle,
      started_at: startedAt,
      finished_at: finishedAt,
      track_geojson: { type: 'LineString', coordinates: track },
      total_distance_m: 2400 + ri * 650,
      metadata: { demo: true },
      created_at: startedAt,
      updated_at: startedAt,
    } as Route);

    const uploadId = uuid();
    const jobId = uuid();
    jobIds.push(jobId);
    uploads.push({
      id: uploadId,
      original_filename: `demo-survey-${ri + 1}.mp4`,
      storage_key: `uploads/demo/survey-${ri + 1}.mp4`,
      content_type: 'video/mp4',
      file_size: 48_000_000 + ri * 7_000_000,
      checksum_sha256: uuid().replace(/-/g, '') + uuid().replace(/-/g, '').slice(0, 32),
      media_type: 'VIDEO',
      uploaded_by: DEMO_USER.id,
      route_id: routeId,
      metadata: { demo: true, capture_started_at: startedAt },
      created_at: startedAt,
      presigned_url: null,
    } as Upload);

    const frameCount = 42 + ri * 6;
    jobs.push({
      id: jobId,
      upload_id: uploadId,
      route_id: routeId,
      status: 'COMPLETED',
      progress: 1,
      current_stage: 'COMPLETED',
      total_frames: frameCount,
      processed_frames: frameCount - 3,
      failed_frames: 1,
      rejected_frames: 2,
      options: { demo: true },
      error_code: null,
      error_message: null,
      created_by: DEMO_USER.id,
      created_at: iso(plan.offsetMin + 5),
      started_at: iso(plan.offsetMin + 6),
      finished_at: iso(plan.offsetMin + 40),
      updated_at: iso(plan.offsetMin + 40),
    } as Job);

    for (let fi = 0; fi < frameCount; fi++) {
      const status = fi === 17 ? 'FAILED' : fi === 9 || fi === 31 ? 'REJECTED' : 'PROCESSED';
      frames.push({
        id: uuid(),
        job_id: jobId,
        frame_index: fi,
        status,
        quality_verdict: status === 'REJECTED' ? 'REJECT' : 'PASS',
        reject_reason: status === 'REJECTED' ? 'blur' : null,
        error_code: status === 'FAILED' ? 'ml_timeout' : null,
        storage_key: `frames/${jobId}/${String(fi).padStart(6, '0')}.jpg`,
        observed_at: iso(plan.offsetMin + 6 + fi * 0.8),
        longitude: track[Math.min(12, Math.floor((fi / frameCount) * 12))][0],
        latitude: track[Math.min(12, Math.floor((fi / frameCount) * 12))][1],
        detections_count: status === 'PROCESSED' ? Math.floor(rng() * 3) : 0,
      } as JobFrame);
    }
  });

  ASSET_PLANS.forEach((plan, ai) => {
    const rp = ROUTE_PLANS[plan.route];
    const lon = rp.startLon + (rp.endLon - rp.startLon) * plan.t + (rng() - 0.5) * 0.0012;
    const lat = rp.startLat + (rp.endLat - rp.startLat) * plan.t + (rng() - 0.5) * 0.0008;
    const assetId = uuid();
    const firstOffset = rp.offsetMin + 10 + plan.t * 80;
    const hasSecond = plan.route === 2 || ai % 3 === 0 || plan.worsened === true;
    const secondOffset = -60 * 24 * 5 + 20 + plan.t * 70;
    const street = STREET_NAMES[(ai + plan.route) % STREET_NAMES.length];
    const typeLabel =
      plan.type === 'telecom_well' ? 'Колодец связи' : plan.type === 'pole' ? 'Опора' : plan.type === 'telecom_cabinet' ? 'Телеком-шкаф' : 'Кабельная линия';
    const externalId = `DEMO-${plan.type === 'telecom_well' ? 'W' : plan.type === 'pole' ? 'P' : plan.type === 'telecom_cabinet' ? 'C' : 'L'}-${String(ai + 1).padStart(4, '0')}`;

    const finalCondition = plan.worsened ? 'missing_cover' : plan.condition;
    const finalSeverity = plan.worsened ? 5 : plan.severity;
    const lastOffset = hasSecond ? secondOffset : firstOffset;
    const band =
      finalSeverity >= 4 && plan.confidence >= 0.7 ? 'HIGH_PRIORITY'
      : finalSeverity >= 3 ? 'MEDIUM_PRIORITY'
      : plan.confidence < 0.65 ? 'NEEDS_REVIEW'
      : 'LOW_PRIORITY';
    const priority = Math.min(99, Math.round(finalSeverity * 16 * (0.6 + plan.confidence * 0.4) + (plan.type === 'telecom_well' ? 8 : 0)));

    assets.push({
      id: assetId,
      external_id: externalId,
      asset_type: plan.type,
      display_name: `${typeLabel} №${4200 + ai} (${street})`,
      longitude: lon,
      latitude: lat,
      location_accuracy_m: 3 + rng() * 4,
      geolocation_status: 'CONFIRMED',
      current_condition: finalCondition,
      current_severity: finalSeverity,
      current_priority: priority,
      priority_band: band,
      priority_factors: {
        severity: finalSeverity,
        severity_normalized: finalSeverity / 5,
        severity_known: true,
        impact_factor: plan.type === 'telecom_well' ? 1 : 0.8,
        confidence: plan.confidence,
        confidence_factor: 0.6 + plan.confidence * 0.4,
        computed_priority: priority,
        manual_override: null,
        review_decision: ai % 4 === 0 ? 'CONFIRMED' : null,
        deduplication_result: 'NEW_ASSET',
      },
      priority_policy_version: '1.0',
      priority_override: null,
      priority_override_reason: null,
      lifecycle_status: 'ACTIVE',
      first_observed_at: iso(firstOffset),
      last_observed_at: iso(lastOffset),
      version: hasSecond ? 2 : 1,
      created_at: iso(firstOffset + 2),
      updated_at: iso(lastOffset + 2),
    } as Asset);

    const surveys = hasSecond ? [firstOffset, secondOffset] : [firstOffset];
    surveys.forEach((offset, si) => {
      const isWorsenedNow = plan.worsened && si === 1;
      const condition = isWorsenedNow ? 'missing_cover' : plan.worsened && si === 0 ? 'damaged_cover' : plan.condition;
      const severity = isWorsenedNow ? 5 : plan.worsened && si === 0 ? 4 : plan.severity;
      const obsId = uuid();
      const jobId = jobIds[plan.route];
      const reviewed = si === 0 && ai % 4 === 0;
      const bboxX = 300 + rng() * 900;
      const bboxY = 260 + rng() * 420;
      const bw = 220 + rng() * 260;
      const bh = 200 + rng() * 260;

      observations.push({
        id: obsId,
        asset_id: assetId,
        processing_job_id: jobId,
        frame_id: uuid(),
        detection_id: uuid(),
        observed_at: iso(offset),
        detected_at: iso(offset + 3),
        object_type: plan.type,
        condition_class: condition,
        detector_confidence: plan.confidence,
        classifier_confidence: plan.confidence - 0.04,
        severity,
        bbox: { x_min: bboxX, y_min: bboxY, x_max: bboxX + bw, y_max: bboxY + bh },
        image_width: 1920,
        image_height: 1080,
        image_id: uuid(),
        crop_image_id: uuid(),
        longitude: lon + (rng() - 0.5) * 0.0002,
        latitude: lat + (rng() - 0.5) * 0.0002,
        location_accuracy_m: 4,
        geolocation_status: 'CONFIRMED',
        geolocation_source: 'GPS',
        tracking_id: si === 0 ? `demo-track-${ai}` : null,
        model_name: 'mock-infrastructure-detector',
        model_version: '0.1.0-mock',
        dedup_result: si === 0 ? 'NEW_ASSET' : 'MATCHED',
        dedup_score: si === 0 ? 0 : 0.86 + rng() * 0.1,
        dedup_explanation:
          si === 0
            ? { reason: 'no_candidates_in_radius', demo: true }
            : { reason: 'matched_by_distance_and_type', distance_m: 2.1, type_match: true, demo: true },
        review_status: reviewed ? 'CONFIRMED' : 'UNREVIEWED',
        effective_asset_type: plan.type,
        effective_condition: condition,
        effective_severity: severity,
        created_at: iso(offset + 3),
        image_url: null,
        crop_url: null,
      } as Observation);

      if (reviewed) {
        reviews.push({
          id: uuid(),
          observation_id: obsId,
          defect_id: null,
          reviewer_id: DEMO_USER.id,
          decision: 'CONFIRMED',
          corrected_asset_type: null,
          corrected_condition: null,
          corrected_defect_type: null,
          corrected_severity: null,
          comment: 'Подтверждено по кадру объезда (демо).',
          reviewed_at: iso(offset + 60),
          created_at: iso(offset + 60),
        } as Review);
      }

      if (condition !== 'ok' && si === surveys.length - 1) {
        const defectType = CONDITION_DEFECT[condition] ?? 'other';
        const existing = defects.find((d) => d.asset_id === assetId);
        if (!existing) {
          defects.push({
            id: uuid(),
            asset_id: assetId,
            defect_type: defectType,
            status: reviewed ? 'CONFIRMED' : 'OPEN',
            severity,
            description: `${condition} — обнаружено при объезде (демо-данные).`,
            first_detected_at: iso(firstOffset),
            last_detected_at: iso(offset),
            resolved_at: null,
            observation_count: surveys.length,
            created_at: iso(firstOffset + 4),
            updated_at: iso(offset + 4),
          } as Defect);
        }
      }

      const prevCondition = si === 0 ? null : plan.worsened ? 'damaged_cover' : plan.condition;
      const prevSeverity = si === 0 ? null : plan.worsened ? 4 : plan.severity;
      history.push({
        id: uuid(),
        asset_id: assetId,
        observation_id: obsId,
        review_id: null,
        change_source: 'ML_PREDICTION',
        previous_condition: prevCondition,
        new_condition: condition,
        previous_severity: prevSeverity,
        new_severity: severity,
        previous_priority: null,
        new_priority: priority,
        is_physical_change: si > 0 && plan.worsened === true,
        note: plan.worsened && si === 1 ? 'Состояние ухудшилось между объездами (демо).' : null,
        detected_at: iso(offset),
      } as ConditionHistory);
    });
  });

  const ambiguousAsset = assets[3];
  const ambObsId = uuid();
  observations.push({
    id: ambObsId,
    asset_id: null,
    processing_job_id: jobIds[0],
    frame_id: uuid(),
    detection_id: uuid(),
    observed_at: iso(-60 * 24 * 5 + 40),
    detected_at: iso(-60 * 24 * 5 + 43),
    object_type: 'telecom_well',
    condition_class: 'damaged_cover',
    detector_confidence: 0.54,
    classifier_confidence: 0.5,
    severity: 3,
    bbox: { x_min: 700, y_min: 400, x_max: 1050, y_max: 720 },
    image_width: 1920,
    image_height: 1080,
    image_id: uuid(),
    crop_image_id: uuid(),
    longitude: ambiguousAsset.longitude! + 0.0004,
    latitude: ambiguousAsset.latitude! + 0.0002,
    location_accuracy_m: 6,
    geolocation_status: 'ESTIMATED',
    geolocation_source: 'GPS',
    tracking_id: null,
    model_name: 'mock-infrastructure-detector',
    model_version: '0.1.0-mock',
    dedup_result: 'POSSIBLE_MATCH',
    dedup_score: 0.61,
    dedup_explanation: {
      reason: 'possible_match_not_merged',
      candidate_asset_id: ambiguousAsset.id,
      distance_m: 38,
      margin: 0.08,
      demo: true,
    },
    review_status: 'UNREVIEWED',
    effective_asset_type: 'telecom_well',
    effective_condition: 'damaged_cover',
    effective_severity: 3,
    created_at: iso(-60 * 24 * 5 + 43),
    image_url: null,
    crop_url: null,
  } as Observation);

  return { routes, uploads, jobs, frames, assets, observations, defects, reviews, history };
}

export const demoData: DemoData = build();

export function resetDemoData(): void {
  const fresh = build();
  Object.assign(demoData, fresh);
}