import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { SearchResponse } from '@/types/transcript';

// debounce hook: only emits value after delay ms
function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

export function useSearch(
  caseId: string,
  query: string,
  types?: string[],
): ReturnType<typeof useQuery<SearchResponse>> {
  const debouncedQuery = useDebounce(query, 300);

  return useQuery({
    queryKey: queryKeys.search.results(caseId, debouncedQuery, types),
    queryFn: () => {
      const params = new URLSearchParams({
        q: debouncedQuery,
      });
      if (types && types.length > 0) {
        types.forEach((t) => params.append('type', t));
      }
      return apiClient.get<SearchResponse>(
        `/cases/${caseId}/search?${params.toString()}`,
      );
    },
    enabled: !!caseId && debouncedQuery.trim().length >= 2,
  });
}
