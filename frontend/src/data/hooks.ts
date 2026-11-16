import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { api, networkError, newIdempotencyKey, unwrap } from '../api/client';
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
import { demoProvider } from '../demo/provider';
import { useDataSource } from './source';

type Q = Record<string, string | number | boolean | undefined | null>;

function clean(q: Q): Q {
  const out: Q = {};
  Object.entries(q).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') out[k] = v;
  });
  return out;
}

async function live<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    throw networkError(err);
  }
}

/* ── Analytics ─────────────────────────────────────── */
export function useAnalyticsOverview(options?: Partial<UseQueryOptions<AnalyticsOverview>>) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['analytics-overview', mode],
    queryFn: () =>
      mode === 'demo' ? demoProvider.analyticsOverview() : live(() => unwrap(api.GET('/api/v1/analytics/overview'))),
    staleTime: 30_000,
    ...options,
  });
}

export function useDefectsAnalytics() {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['analytics-defects', mode],
    queryFn: () =>
      mode === 'demo' ? demoProvider.analyticsDefects() : live(() => unwrap(api.GET('/api/v1/analytics/defects'))),
    staleTime: 30_000,
  });
}

export function useCoverage() {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['analytics-coverage', mode],
    queryFn: () =>
      mode === 'demo' ? demoProvider.analyticsCoverage() : live(() => unwrap(api.GET('/api/v1/analytics/coverage'))),
    staleTime: 60_000,
  });
}

/* ── Assets ────────────────────────────────────────── */
export function useAssets(params: Q, options?: Partial<UseQueryOptions<Page<Asset>>>) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['assets', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.assets(q)
        : live(() => unwrap(api.GET('/api/v1/assets', { params: { query: q as never } }))),
    ...options,
  });
}

export function useAsset(id: string | undefined) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['asset', mode, id],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.asset(id!)
        : live(() => unwrap(api.GET('/api/v1/assets/{asset_id}', { params: { path: { asset_id: id! } } }))),
  });
}

export function useAssetHistory(id: string | undefined, page = 1) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['asset-history', mode, id, page],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.assetHistory(id!, { page, page_size: 50 })
        : live(() =>
            unwrap(
              api.GET('/api/v1/assets/{asset_id}/history', {
                params: { path: { asset_id: id! }, query: { page, page_size: 50 } },
              }),
            ),
          ),
  });
}

export function useAssetObservations(id: string | undefined, params: Q = {}) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['asset-observations', mode, id, q],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.assetObservations(id!, q)
        : live(() =>
            unwrap(
              api.GET('/api/v1/assets/{asset_id}/observations', {
                params: { path: { asset_id: id! }, query: q as never },
              }),
            ),
          ),
  });
}

export function useAssetDefects(id: string | undefined, params: Q = {}) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['asset-defects', mode, id, q],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.assetDefects(id!, q)
        : live(() =>
            unwrap(
              api.GET('/api/v1/assets/{asset_id}/defects', {
                params: { path: { asset_id: id! }, query: q as never },
              }),
            ),
          ),
  });
}

export function usePatchAsset() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: AssetPatch }) =>
      mode === 'demo'
        ? demoProvider.patchAsset(id, patch)
        : live(() =>
            unwrap(api.PATCH('/api/v1/assets/{asset_id}', { params: { path: { asset_id: id } }, body: patch })),
          ),
    onSuccess: (asset) => {
      qc.invalidateQueries({ queryKey: ['asset', mode, asset.id] });
      qc.invalidateQueries({ queryKey: ['assets', mode] });
      qc.invalidateQueries({ queryKey: ['map-assets', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
    },
  });
}

/* ── Observations ──────────────────────────────────── */
export function useObservations(params: Q, options?: Partial<UseQueryOptions<Page<Observation>>>) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['observations', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.observations(q)
        : live(() => unwrap(api.GET('/api/v1/observations', { params: { query: q as never } }))),
    ...options,
  });
}

export function useObservation(id: string | undefined) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['observation', mode, id],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.observation(id!)
        : live(() =>
            unwrap(api.GET('/api/v1/observations/{observation_id}', { params: { path: { observation_id: id! } } })),
          ),
  });
}

/* ── Defects ───────────────────────────────────────── */
export function useDefects(params: Q, options?: Partial<UseQueryOptions<Page<Defect>>>) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['defects', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.defects(q)
        : live(() => unwrap(api.GET('/api/v1/defects', { params: { query: q as never } }))),
    ...options,
  });
}

export function useDefect(id: string | undefined) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['defect', mode, id],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.defect(id!)
        : live(() => unwrap(api.GET('/api/v1/defects/{defect_id}', { params: { path: { defect_id: id! } } }))),
  });
}

export function usePatchDefect() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: DefectPatch }) =>
      mode === 'demo'
        ? demoProvider.patchDefect(id, patch)
        : live(() =>
            unwrap(api.PATCH('/api/v1/defects/{defect_id}', { params: { path: { defect_id: id } }, body: patch })),
          ),
    onSuccess: (defect) => {
      qc.invalidateQueries({ queryKey: ['defect', mode, defect.id] });
      qc.invalidateQueries({ queryKey: ['defects', mode] });
      qc.invalidateQueries({ queryKey: ['asset-defects', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-defects', mode] });
    },
  });
}

/* ── Reviews ───────────────────────────────────────── */
export function useReviews(params: Q) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['reviews', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.reviews(q)
        : live(() => unwrap(api.GET('/api/v1/reviews', { params: { query: q as never } }))),
  });
}

export function useCreateReview() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ReviewCreate) =>
      mode === 'demo'
        ? demoProvider.createReview(payload)
        : live(() =>
            unwrap(
              api.POST('/api/v1/reviews', {
                body: payload,
                headers: { 'Idempotency-Key': newIdempotencyKey() },
              }),
            ),
          ),
    onSuccess: (review) => {
      qc.invalidateQueries({ queryKey: ['observations', mode] });
      qc.invalidateQueries({ queryKey: ['observation', mode] });
      qc.invalidateQueries({ queryKey: ['reviews', mode] });
      qc.invalidateQueries({ queryKey: ['assets', mode] });
      qc.invalidateQueries({ queryKey: ['asset', mode] });
      qc.invalidateQueries({ queryKey: ['asset-history', mode] });
      qc.invalidateQueries({ queryKey: ['defects', mode] });
      qc.invalidateQueries({ queryKey: ['defect', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
      if (review.observation_id) {
        qc.invalidateQueries({ queryKey: ['observation', mode, review.observation_id] });
      }
    },
  });
}

/* ── Jobs / Uploads ────────────────────────────────── */
export function useJobs(params: Q) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['jobs', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.jobs(q)
        : live(() => unwrap(api.GET('/api/v1/jobs', { params: { query: q as never } }))),
    refetchInterval: (query) => {
      const data = query.state.data as Page<Job> | undefined;
      const active = data?.items.some((j) => ['PENDING', 'QUEUED', 'PROCESSING'].includes(j.status));
      return active ? 2000 : false;
    },
  });
}

export function useJob(id: string | undefined) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['job', mode, id],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.job(id!)
        : live(() => unwrap(api.GET('/api/v1/jobs/{job_id}', { params: { path: { job_id: id! } } }))),
    refetchInterval: (query) => {
      const j = query.state.data as Job | undefined;
      return j && ['PENDING', 'QUEUED', 'PROCESSING'].includes(j.status) ? 1500 : false;
    },
  });
}

export function useJobFrames(id: string | undefined, page = 1) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['job-frames', mode, id, page],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.jobFrames(id!, { page, page_size: 50 })
        : live(() =>
            unwrap(
              api.GET('/api/v1/jobs/{job_id}/frames', {
                params: { path: { job_id: id! }, query: { page, page_size: 50 } },
              }),
            ),
          ),
  });
}

export function useCreateJob() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: JobCreate) =>
      mode === 'demo'
        ? demoProvider.createJob(payload)
        : live(() =>
            unwrap(
              api.POST('/api/v1/jobs', { body: payload, headers: { 'Idempotency-Key': newIdempotencyKey() } }),
            ),
          ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
    },
  });
}

export function useJobAction(action: 'retry' | 'cancel') {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      mode === 'demo'
        ? action === 'retry'
          ? demoProvider.retryJob(id)
          : demoProvider.cancelJob(id)
        : live(() =>
            action === 'retry'
              ? unwrap(api.POST('/api/v1/jobs/{job_id}/retry', { params: { path: { job_id: id } } }))
              : unwrap(api.POST('/api/v1/jobs/{job_id}/cancel', { params: { path: { job_id: id } } })),
          ),
    onSuccess: (job) => {
      qc.invalidateQueries({ queryKey: ['job', mode, job.id] });
      qc.invalidateQueries({ queryKey: ['jobs', mode] });
      qc.invalidateQueries({ queryKey: ['job-frames', mode] });
    },
  });
}

export function useUploads(params: Q) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['uploads', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.uploads(q)
        : live(() => unwrap(api.GET('/api/v1/uploads', { params: { query: q as never } }))),
  });
}

export function useCreateUpload() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, routeId, metadata }: { file: File; routeId?: string; metadata?: string }) => {
      if (mode === 'demo') return demoProvider.createUpload(file, routeId);
      const body = new FormData();
      body.append('file', file);
      if (routeId) body.append('route_id', routeId);
      if (metadata) body.append('metadata', metadata);
      return live(() =>
        unwrap(
          api.POST('/api/v1/uploads', {
            body: body as never,
            headers: { 'Idempotency-Key': newIdempotencyKey() },
            bodySerializer: (b) => b as unknown as FormData,
          }),
        ),
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['uploads', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
    },
  });
}

/* ── Routes ────────────────────────────────────────── */
export function useRoutes(params: Q = {}) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['routes', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.routes(q)
        : live(() => unwrap(api.GET('/api/v1/routes', { params: { query: q as never } }))),
  });
}

export function useRoute(id: string | undefined) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['route', mode, id],
    enabled: !!id,
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.route(id!)
        : live(() => unwrap(api.GET('/api/v1/routes/{route_id}', { params: { path: { route_id: id! } } }))),
  });
}

export function useCreateRoute() {
  const { mode } = useDataSource();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RouteCreate) =>
      mode === 'demo'
        ? demoProvider.createRoute(payload)
        : live(() => unwrap(api.POST('/api/v1/routes', { body: payload }))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['routes', mode] });
      qc.invalidateQueries({ queryKey: ['map-routes', mode] });
      qc.invalidateQueries({ queryKey: ['analytics-overview', mode] });
    },
  });
}

/* ── Map layers ────────────────────────────────────── */
export function useMapAssets(params: Q = {}, options?: Partial<UseQueryOptions<AssetMapCollection>>) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['map-assets', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.mapAssets(q)
        : live(() => unwrap(api.GET('/api/v1/map/assets', { params: { query: q as never } }))),
    staleTime: 30_000,
    ...options,
  });
}

export function useMapDefects(params: Q = {}, options?: Partial<UseQueryOptions<DefectMapCollection>>) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['map-defects', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.mapDefects(q)
        : live(() => unwrap(api.GET('/api/v1/map/defects', { params: { query: q as never } }))),
    staleTime: 30_000,
    ...options,
  });
}

export function useMapObservations(params: Q = {}) {
  const { mode } = useDataSource();
  const q = clean(params);
  return useQuery({
    queryKey: ['map-observations', mode, q],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.mapObservations(q)
        : live(() => unwrap(api.GET('/api/v1/map/observations', { params: { query: q as never } }))),
    staleTime: 30_000,
  });
}

export function useMapRoutes(options?: Partial<UseQueryOptions<RouteMapCollection>>) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['map-routes', mode],
    queryFn: () =>
      mode === 'demo'
        ? demoProvider.mapRoutes()
        : live(() => unwrap(api.GET('/api/v1/map/routes'))),
    staleTime: 60_000,
    ...options,
  });
}

/* ── Временные корзины наблюдений (агрегация на клиенте) ── */
export function useObservationTimeBuckets(days = 14) {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['obs-time-buckets', mode, days],
    queryFn: async () => {
      const pages = await Promise.all(
        [1, 2, 3].map((page) =>
          mode === 'demo'
            ? demoProvider.observations({ page, page_size: 100 })
            : live(() => unwrap(api.GET('/api/v1/observations', { params: { query: { page, page_size: 100 } } }))),
        ),
      );
      const items = pages.flatMap((p) => p.items);
      const total = pages[0]?.total ?? items.length;
      const now = new Date();
      const buckets: { label: string; value: number }[] = [];
      for (let i = days - 1; i >= 0; i--) {
        const d = new Date(now.getTime() - i * 86_400_000);
        const key = d.toISOString().slice(0, 10);
        const label = `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;
        buckets.push({ label, value: items.filter((o) => (o.observed_at ?? '').slice(0, 10) === key).length });
      }
      return { buckets, sampleSize: items.length, total };
    },
    staleTime: 60_000,
  });
}

/* ── ML / health ───────────────────────────────────── */
export function useMlStatus() {
  const { mode } = useDataSource();
  return useQuery({
    queryKey: ['ml-status', mode],
    queryFn: async () => {
      if (mode === 'demo') {
        return { health: await demoProvider.mlHealth(), info: await demoProvider.mlModelInfo() };
      }
      return live(async () => ({
        health: await unwrap(api.GET('/api/v1/ml/health')),
        info: await unwrap(api.GET('/api/v1/ml/model-info')),
      }));
    },
    staleTime: 60_000,
    retry: 1,
  });
}

export type {
  AnalyticsOverview,
  Asset,
  AssetMapCollection,
  ConditionHistory,
  CoverageResponse,
  Defect,
  DefectMapCollection,
  DefectsAnalytics,
  FramePage,
  Job,
  Observation,
  ObservationMapCollection,
  Review,
  Route,
  RouteMapCollection,
  Upload,
};