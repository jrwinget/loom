export function Header(): React.ReactElement {
  return (
    <header
      className="flex h-14 items-center justify-between border-b border-border px-6"
      role="banner"
    >
      {/* breadcrumb area */}
      <nav aria-label="Breadcrumb">
        <div className="text-sm text-muted-foreground">
          <span>Home</span>
        </div>
      </nav>

      <div className="flex items-center gap-4">
        {/* keyboard shortcuts hint */}
        <button
          type="button"
          className="rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent"
          aria-label="Keyboard shortcuts"
        >
          ?
        </button>

        {/* user menu placeholder */}
        <button
          type="button"
          className="h-8 w-8 rounded-full bg-muted"
          aria-label="User menu"
        />
      </div>
    </header>
  );
}
