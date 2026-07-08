import { useEffect } from 'react';
import { resolveTheme, useThemeStore } from '@/stores/theme-store';

const QUERY = '(prefers-color-scheme: dark)';

function apply(dark: boolean): void {
  document.documentElement.classList.toggle('dark', dark);
}

// stamps the `dark` class on the document element and, for the
// "system" preference, follows the os live. mounted above the router
// so login/first-run are themed too.
export function ThemeProvider(props: {
  children: React.ReactNode;
}): React.ReactElement {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    // matchMedia is absent in some embedded webviews (and jsdom);
    // "system" then falls back to light rather than crashing
    if (typeof window.matchMedia !== 'function') {
      apply(theme === 'dark');
      return;
    }

    const media = window.matchMedia(QUERY);
    apply(resolveTheme(theme, media.matches) === 'dark');

    if (theme !== 'system') return;
    const onChange = (e: MediaQueryListEvent): void => apply(e.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [theme]);

  return <>{props.children}</>;
}
