import { useState } from 'react';
import {
  usePlugins,
  useCreatePlugin,
  useUpdatePlugin,
} from '@/hooks/use-plugins';
import type { Plugin } from '@/types/plugin';

const PLUGIN_TYPES = ['webhook', 'activity', 'integration'] as const;

function TypeBadge({ type }: { type: string }): React.ReactElement {
  const colors: Record<string, string> = {
    webhook: 'bg-blue-100 text-blue-800',
    activity: 'bg-green-100 text-green-800',
    integration: 'bg-purple-100 text-purple-800',
  };

  return (
    <span
      data-testid={`type-badge-${type}`}
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[type] ?? 'bg-gray-100 text-gray-800'}`}
    >
      {type}
    </span>
  );
}

interface CreateDialogProps {
  open: boolean;
  onClose: () => void;
}

function CreatePluginDialog({
  open,
  onClose,
}: CreateDialogProps): React.ReactElement | null {
  const [name, setName] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [pluginType, setPluginType] = useState<string>('webhook');
  const [description, setDescription] = useState('');

  const createPlugin = useCreatePlugin();

  if (!open) return null;

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    createPlugin.mutate(
      {
        name,
        version,
        plugin_type: pluginType,
        description: description || undefined,
      },
      {
        onSuccess: () => {
          setName('');
          setVersion('1.0.0');
          setPluginType('webhook');
          setDescription('');
          onClose();
        },
      },
    );
  };

  return (
    <div
      data-testid="create-plugin-dialog"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-lg">
        <h2 className="mb-4 text-lg font-semibold">Create Plugin</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="plugin-name" className="block text-sm font-medium">
              Name
            </label>
            <input
              id="plugin-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
              required
            />
          </div>
          <div>
            <label
              htmlFor="plugin-version"
              className="block text-sm font-medium"
            >
              Version
            </label>
            <input
              id="plugin-version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
              required
            />
          </div>
          <div>
            <label htmlFor="plugin-type" className="block text-sm font-medium">
              Type
            </label>
            <select
              id="plugin-type"
              value={pluginType}
              onChange={(e) => setPluginType(e.target.value)}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            >
              {PLUGIN_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              htmlFor="plugin-description"
              className="block text-sm font-medium"
            >
              Description
            </label>
            <textarea
              id="plugin-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
              rows={3}
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border px-4 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
            >
              Create
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

interface PluginCardProps {
  plugin: Plugin;
  onSelect: (plugin: Plugin) => void;
}

function PluginCard({ plugin, onSelect }: PluginCardProps): React.ReactElement {
  const updatePlugin = useUpdatePlugin(plugin.id);

  const handleToggle = (): void => {
    updatePlugin.mutate({ is_enabled: !plugin.isEnabled });
  };

  return (
    <div
      data-testid={`plugin-card-${plugin.id}`}
      className="rounded-lg border p-4 hover:border-primary/50"
    >
      <div className="flex items-start justify-between">
        <button
          type="button"
          onClick={() => onSelect(plugin)}
          className="flex-1 text-left"
        >
          <h3 className="font-medium">{plugin.name}</h3>
          {plugin.description && (
            <p className="mt-1 text-sm text-muted-foreground">
              {plugin.description}
            </p>
          )}
          <div className="mt-2 flex items-center gap-2">
            <TypeBadge type={plugin.pluginType} />
            <span className="text-xs text-muted-foreground">
              v{plugin.version}
            </span>
          </div>
        </button>
        <button
          data-testid={`toggle-${plugin.id}`}
          onClick={handleToggle}
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            plugin.isEnabled
              ? 'bg-green-100 text-green-800'
              : 'bg-gray-100 text-gray-500'
          }`}
          aria-label={plugin.isEnabled ? 'Disable plugin' : 'Enable plugin'}
        >
          {plugin.isEnabled ? 'Enabled' : 'Disabled'}
        </button>
      </div>
    </div>
  );
}

interface PluginListProps {
  onSelectPlugin?: (plugin: Plugin) => void;
}

export function PluginList({
  onSelectPlugin,
}: PluginListProps): React.ReactElement {
  const [showCreate, setShowCreate] = useState(false);
  const { data, isLoading } = usePlugins();

  if (isLoading) {
    return <div data-testid="plugin-list-loading">Loading plugins...</div>;
  }

  const plugins = data?.items ?? [];

  return (
    <div data-testid="plugin-list">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Plugins</h2>
        <button
          data-testid="create-plugin-btn"
          onClick={() => setShowCreate(true)}
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
        >
          Add Plugin
        </button>
      </div>

      {plugins.length === 0 ? (
        <p className="text-muted-foreground">No plugins installed</p>
      ) : (
        <div className="space-y-3">
          {plugins.map((plugin) => (
            <PluginCard
              key={plugin.id}
              plugin={plugin}
              onSelect={onSelectPlugin ?? (() => {})}
            />
          ))}
        </div>
      )}

      <CreatePluginDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
      />
    </div>
  );
}
