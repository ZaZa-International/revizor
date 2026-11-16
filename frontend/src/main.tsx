import { StrictMode, Suspense, lazy, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './api/auth';
import { DataSourceProvider } from './data/source';
import { ApiError } from './api/client';
import { ToastStack, LoadingState, ErrorState } from './components/ui';
import './styles/tokens.css';
import './styles/base.css';
import './styles/components.css';
import './styles/app.css';
import './styles/showcase.css';

const ShowcasePage = lazy(() => import('./showcase/ShowcasePage'));
const LoginPage = lazy(() => import('./app/LoginPage'));
const AppShell = lazy(() => import('./app/AppShell'));
const OverviewPage = lazy(() => import('./app/OverviewPage'));
const MapPage = lazy(() => import('./app/MapPage'));
const AssetsPage = lazy(() => import('./app/AssetsPage'));
const AssetPassportPage = lazy(() => import('./app/AssetPassportPage'));
const ObservationsPage = lazy(() => import('./app/ObservationsPage'));
const ObservationDetailPage = lazy(() => import('./app/ObservationDetailPage'));
const DefectsPage = lazy(() => import('./app/DefectsPage'));
const DefectDetailPage = lazy(() => import('./app/DefectDetailPage'));
const ReviewsPage = lazy(() => import('./app/ReviewsPage'));
const JobsPage = lazy(() => import('./app/JobsPage'));
const JobDetailPage = lazy(() => import('./app/JobDetailPage'));
const RoutesPage = lazy(() => import('./app/RoutesPage'));
const RouteDetailPage = lazy(() => import('./app/RouteDetailPage'));
const AnalyticsPage = lazy(() => import('./app/AnalyticsPage'));
const ExportsPage = lazy(() => import('./app/ExportsPage'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && !error.retryable) return false;
        return failureCount < 2;
      },
      refetchOnWindowFocus: false,
    },
  },
});

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center' }}>
          <ErrorState error={this.state.error} onRetry={() => window.location.reload()} />
        </div>
      );
    }
    return this.props.children;
  }
}

function NotFound() {
  return (
    <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center' }}>
      <div className="state-block">
        <h3>Страница не найдена</h3>
        <p>Проверьте адрес или вернитесь на главную.</p>
        <a className="btn btn-primary" href="/">
          На главную
        </a>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <DataSourceProvider>
            <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
              <Suspense fallback={<div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center' }}><LoadingState label="Загрузка интерфейса…" /></div>}>
                <Routes>
                  <Route path="/" element={<ShowcasePage />} />
                  <Route path="/login" element={<LoginPage />} />
                  <Route path="/app" element={<AppShell />}>
                    <Route index element={<OverviewPage />} />
                    <Route path="map" element={<MapPage />} />
                    <Route path="assets" element={<AssetsPage />} />
                    <Route path="assets/:id" element={<AssetPassportPage />} />
                    <Route path="observations" element={<ObservationsPage />} />
                    <Route path="observations/:id" element={<ObservationDetailPage />} />
                    <Route path="defects" element={<DefectsPage />} />
                    <Route path="defects/:id" element={<DefectDetailPage />} />
                    <Route path="reviews" element={<ReviewsPage />} />
                    <Route path="jobs" element={<JobsPage />} />
                    <Route path="jobs/:id" element={<JobDetailPage />} />
                    <Route path="routes" element={<RoutesPage />} />
                    <Route path="routes/:id" element={<RouteDetailPage />} />
                    <Route path="analytics" element={<AnalyticsPage />} />
                    <Route path="exports" element={<ExportsPage />} />
                  </Route>
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </BrowserRouter>
            <ToastStack />
          </DataSourceProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
);