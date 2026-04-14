export function Dashboard(): React.ReactElement {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-semibold text-foreground">
          Welcome to Loom
        </h1>
        <p className="mt-2 text-muted-foreground">
          Select a case to get started
        </p>
      </div>
    </div>
  );
}
