import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Shell } from '@/components/layout/shell';
import { Dashboard } from '@/routes/index';
import { CaseListPage } from '@/routes/cases/index';
import { CaseDetailPage } from '@/routes/cases/[caseId]/index';
import { AssetsPage } from '@/routes/cases/[caseId]/assets';
import { TimelinePage } from '@/routes/cases/[caseId]/timeline';
import { ExportPage } from '@/routes/cases/[caseId]/export';
import { ReviewPage } from '@/routes/cases/[caseId]/review';

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
        <Routes>
          <Route element={<Shell />}>
            <Route index element={<Dashboard />} />
            <Route path="cases" element={<CaseListPage />} />
            <Route path="cases/:caseId" element={<CaseDetailPage />} />
            <Route path="cases/:caseId/assets" element={<AssetsPage />} />
            <Route path="cases/:caseId/timeline" element={<TimelinePage />} />
            <Route path="cases/:caseId/export" element={<ExportPage />} />
            <Route
              path="cases/:caseId/review/:assetId"
              element={<ReviewPage />}
            />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
