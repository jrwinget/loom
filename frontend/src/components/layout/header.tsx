import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';

export function Header(): React.ReactElement {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const toggleMenu = useCallback(() => {
    setMenuOpen((prev) => !prev);
  }, []);

  const handleLogout = useCallback(() => {
    useAuthStore.getState().clearAuth();
    navigate('/login');
  }, [navigate]);

  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (e: MouseEvent): void => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [menuOpen]);

  return (
    <header
      className={
        'flex h-14 items-center justify-between ' +
        'border-b border-border px-6'
      }
      role="banner"
    >
      <nav aria-label="Breadcrumb">
        <div className="text-sm text-muted-foreground">
          <span>Home</span>
        </div>
      </nav>

      <div className="flex items-center gap-4">
        <button
          type="button"
          className={
            'rounded-md border border-border px-2 py-1 ' +
            'text-xs text-muted-foreground hover:bg-accent'
          }
          aria-label="Keyboard shortcuts"
        >
          ?
        </button>

        <div ref={menuRef} className="relative">
          <button
            type="button"
            className={
              'flex h-8 w-8 items-center justify-center ' +
              'rounded-full bg-muted text-xs font-medium' +
              'text-foreground'
            }
            aria-label="User menu"
            aria-expanded={menuOpen}
            aria-haspopup="true"
            data-testid="user-menu-button"
            onClick={toggleMenu}
          >
            {user?.email?.charAt(0).toUpperCase() ?? '?'}
          </button>

          {menuOpen && (
            <div
              data-testid="user-menu-dropdown"
              className={
                'absolute right-0 top-full z-50 mt-1 w-56 ' +
                'rounded-md border border-border bg-background' +
                'py-1 shadow-lg'
              }
            >
              {user?.email && (
                <p
                  className={
                    'truncate border-b border-border px-3 ' +
                    'py-2 text-sm text-foreground'
                  }
                  data-testid="user-menu-email"
                >
                  {user.email}
                </p>
              )}
              <a
                href="/settings/security"
                className={
                  'block px-3 py-2 text-sm ' +
                  'text-muted-foreground hover:bg-accent'
                }
                onClick={(e) => {
                  e.preventDefault();
                  setMenuOpen(false);
                  navigate('/settings/security');
                }}
              >
                Settings
              </a>
              <button
                type="button"
                data-testid="logout-button"
                className={
                  'w-full px-3 py-2 text-left text-sm ' +
                  'text-muted-foreground hover:bg-accent'
                }
                onClick={handleLogout}
              >
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
