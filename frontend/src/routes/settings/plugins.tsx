import { useState } from 'react';
import { PluginList } from '@/components/plugin/plugin-list';
import { WebhookConfig } from '@/components/plugin/webhook-config';
import type { Plugin } from '@/types/plugin';

export function PluginsSettingsPage(): React.ReactElement {
  const [selectedPlugin, setSelectedPlugin] = useState<Plugin | null>(null);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-muted-foreground">Manage plugins and integrations</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <PluginList onSelectPlugin={setSelectedPlugin} />
        </div>
        <div>
          {selectedPlugin ? (
            <div>
              <h2 className="mb-4 text-lg font-semibold">
                {selectedPlugin.name}
              </h2>
              <WebhookConfig pluginId={selectedPlugin.id} />
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              Select a plugin to configure webhooks
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
