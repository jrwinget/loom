import * as Dialog from '@radix-ui/react-dialog';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import { useAuthStore } from '@/stores/auth-store';

// kept in this file rather than a `/shortcuts.ts` module so each
// entry sits next to the dialog that renders it; review/timeline
// shortcuts are still registered at their use site.
const SHORTCUT_GROUPS: { heading: string; items: [string, string][] }[] = [
  {
    heading: 'Playback (when viewing an asset)',
    items: [
      ['Space', 'Play / pause'],
      ['← / →', 'Skip ±5 seconds'],
      ['Shift + ← / →', 'Step ±1 frame'],
      ['I / O', 'Mark in / out point'],
    ],
  },
  {
    heading: 'Review workspace',
    items: [
      ['Ctrl + F / ⌘ + F', 'Focus search'],
      ['Ctrl + H', 'Hide / show panel'],
    ],
  },
  {
    heading: 'Global',
    items: [['?', 'Open this dialog']],
  },
];

export function Header(): React.ReactElement {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [menuOpen, setMenuOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useKeyboardShortcut('shift+/', () => setShortcutsOpen((prev) => !prev), []);

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
          data-testid="open-shortcuts"
          onClick={() => setShortcutsOpen(true)}
        >
          ?
        </button>

        <Dialog.Root open={shortcutsOpen} onOpenChange={setShortcutsOpen}>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 bg-black/40" />
            <Dialog.Content
              data-testid="shortcuts-dialog"
              className={
                'bg-card fixed left-1/2 top-1/2 w-full max-w-md ' +
                '-translate-x-1/2 -translate-y-1/2 rounded-lg' +
                'border border-border p-6 shadow-lg'
              }
            >
              <Dialog.Title className="text-lg font-semibold text-foreground">
                Keyboard shortcuts
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-muted-foreground">
                Shortcuts are scoped to the panel that owns them.
              </Dialog.Description>
              <div className="mt-4 space-y-4">
                {SHORTCUT_GROUPS.map((group) => (
                  <section key={group.heading}>
                    <h3 className="text-sm font-medium text-foreground">
                      {group.heading}
                    </h3>
                    <dl className="mt-2 space-y-1 text-sm">
                      {group.items.map(([keys, label]) => (
                        <div key={keys} className="flex justify-between gap-4">
                          <dt className="text-muted-foreground">{label}</dt>
                          <dd className="font-mono text-xs text-foreground">
                            {keys}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                ))}
              </div>
              <div className="mt-6 flex justify-end">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90"
                  >
                    Close
                  </button>
                </Dialog.Close>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>

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
