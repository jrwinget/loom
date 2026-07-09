import { useNavigate } from 'react-router-dom';

interface CaseCardProps {
  id: string;
  name: string;
  description: string | null;
  status: string;
  assetCount: number;
  eventCount: number;
  createdAt: string;
}

const statusColors: Record<string, string> = {
  active:
    'bg-green-100 text-green-800 dark:bg-green-900 ' + 'dark:text-green-200',
  archived:
    'bg-gray-100 text-gray-800 dark:bg-gray-900 ' + 'dark:text-gray-200',
  exported:
    'bg-blue-100 text-blue-800 dark:bg-blue-900 ' + 'dark:text-blue-200',
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function CaseCard(props: CaseCardProps): React.ReactElement {
  const navigate = useNavigate();
  const { id, name, description, status, assetCount, eventCount, createdAt } =
    props;

  const colorClass = statusColors[status] ?? statusColors['archived'];
  // truncate description to ~100 chars (description is optional)
  const truncated =
    description && description.length > 100
      ? description.slice(0, 100) + '...'
      : (description ?? '');

  return (
    <button
      type="button"
      data-testid={`case-card-${id}`}
      className="border-border bg-card hover:bg-accent/50 flex w-full flex-col rounded-lg border p-4 text-left shadow-xs transition-colors"
      onClick={() => navigate(`/cases/${id}`)}
    >
      {/* header row */}
      <div className="flex items-start justify-between">
        <h3 className="text-foreground text-sm font-semibold">{name}</h3>
        <span
          data-testid="status-badge"
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}
        >
          {status}
        </span>
      </div>

      {/* description */}
      <p className="text-muted-foreground mt-1 text-xs">{truncated}</p>

      {/* stats row */}
      <div className="text-muted-foreground mt-3 flex items-center gap-4 text-xs">
        <span>{assetCount} assets</span>
        <span>{eventCount} events</span>
        <span className="ml-auto">{formatDate(createdAt)}</span>
      </div>
    </button>
  );
}
