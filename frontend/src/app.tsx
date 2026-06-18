import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { FirstRunGuard } from '@/components/auth/first-run-guard';
import { ProtectedRoute } from '@/components/auth/protected-route';
import { ErrorBoundary } from '@/components/layout/error-boundary';
import { CaseLayout } from '@/components/layout/case-layout';
import { Shell } from '@/components/layout/shell';
import { ToastContainer } from '@/components/layout/toast-container';
import { Dashboard } from '@/routes/index';
import { FirstRunPage } from '@/routes/first-run';
import { ForgotPasswordPage } from '@/routes/forgot-password';
import { LoginPage } from '@/routes/login';
import { CaseListPage } from '@/routes/cases/index';
import { CaseDetailPage } from '@/routes/cases/[caseId]/index';
import { AssetsPage } from '@/routes/cases/[caseId]/assets';
import { TimelinePage } from '@/routes/cases/[caseId]/timeline';
import { ConflictsPage } from '@/routes/cases/[caseId]/conflicts';
import { ExportPage } from '@/routes/cases/[caseId]/export';
import { ClustersPage } from '@/routes/cases/[caseId]/clusters';
import { MapPage } from '@/routes/cases/[caseId]/map';
import { ReviewPage } from '@/routes/cases/[caseId]/review';
import { OrganizationsPage } from '@/routes/organizations/index';
import { PluginsSettingsPage } from '@/routes/settings/plugins';
import { SecuritySettingsPage } from '@/routes/settings/security';
import { StorageSettingsPage } from '@/routes/settings/storage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

function NotFound(): React.ReactElement {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-foreground">404</h1>
        <p className="mt-2 text-muted-foreground">Page not found</p>
      </div>
    </div>
  );
}

export function App(): React.ReactElement {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <FirstRunGuard>
            <Routes>
              <Route path="first-run" element={<FirstRunPage />} />
              <Route path="login" element={<LoginPage />} />
              <Route path="forgot-password" element={<ForgotPasswordPage />} />
              <Route element={<ProtectedRoute />}>
                <Route element={<Shell />}>
                  <Route index element={<Dashboard />} />
                  <Route path="organizations" element={<OrganizationsPage />} />
                  <Route path="cases" element={<CaseListPage />} />
                  <Route path="cases/:caseId" element={<CaseLayout />}>
                    <Route index element={<CaseDetailPage />} />
                    <Route path="assets" element={<AssetsPage />} />
                    <Route path="timeline" element={<TimelinePage />} />
                    <Route path="conflicts" element={<ConflictsPage />} />
                    <Route path="clusters" element={<ClustersPage />} />
                    <Route path="map" element={<MapPage />} />
                    <Route path="export" element={<ExportPage />} />
                    <Route path="review/:assetId" element={<ReviewPage />} />
                  </Route>
                  <Route
                    path="settings/plugins"
                    element={<PluginsSettingsPage />}
                  />
                  <Route
                    path="settings/security"
                    element={<SecuritySettingsPage />}
                  />
                  <Route
                    path="settings/storage"
                    element={<StorageSettingsPage />}
                  />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Route>
            </Routes>
          </FirstRunGuard>
          <ToastContainer />
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
