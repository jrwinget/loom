import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export interface GlobalSearchResult {
  type: 'case' | 'asset' | 'event' | 'annotation';
  id: string;
  caseId: string;
  title: string;
  snippet: string | null;
}

interface GlobalSearchResponse {
  results: GlobalSearchResult[];
}

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useGlobalSearch(
  query: string,
): ReturnType<typeof useQuery<GlobalSearchResponse>> {
  const debounced = useDebounce(query, 250);
  return useQuery({
    queryKey: ['global-search', debounced],
    queryFn: () =>
      apiClient.get<GlobalSearchResponse>(
        `/search?q=${encodeURIComponent(debounced)}`,
      ),
    // the palette only searches once the query is meaningful, so a
    // single keystroke never fans out a request
    enabled: debounced.trim().length >= 2,
  });
}
