import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../api/auth';
import { useAnalyticsOverview, useMapAssets, useMapRoutes, useObservations } from '../data/hooks';
import { demoProvider } from '../demo/provider';

/* Данные showcase: живые при наличии сессии, иначе явно demo-сценарий.
   Без сессии live-хуки отключены (enabled: live), чтобы не делать
   авторизованных запросов и не получать 401 в консоли. */
export function useShowcaseData() {
  const { session } = useAuth();
  const live = !!session;

  const liveOverview = useAnalyticsOverview({ enabled: live });
  const liveAssets = useMapAssets({ limit: 500 }, { enabled: live });
  const liveRoutes = useMapRoutes({}, { enabled: live });
  const liveQueue = useObservations({ review_status: 'UNREVIEWED', page_size: 1 }, { enabled: live });

  const demoOverview = useQuery({ queryKey: ['showcase-demo-overview'], queryFn: () => demoProvider.analyticsOverview(), enabled: !live, staleTime: Infinity });
  const demoAssets = useQuery({ queryKey: ['showcase-demo-assets'], queryFn: () => demoProvider.mapAssets({}), enabled: !live, staleTime: Infinity });
  const demoRoutes = useQuery({ queryKey: ['showcase-demo-routes'], queryFn: () => demoProvider.mapRoutes(), enabled: !live, staleTime: Infinity });
  const demoQueue = useQuery({ queryKey: ['showcase-demo-queue'], queryFn: () => demoProvider.observations({ review_status: 'UNREVIEWED', page_size: 1 }), enabled: !live, staleTime: Infinity });

  return {
    live,
    overview: live ? liveOverview.data : demoOverview.data,
    assets: live ? liveAssets.data : demoAssets.data,
    routes: live ? liveRoutes.data : demoRoutes.data,
    queueTotal: (live ? liveQueue.data?.total : demoQueue.data?.total) ?? 0,
    loading: live ? liveOverview.isPending : demoOverview.isPending,
  };
}