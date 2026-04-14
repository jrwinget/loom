import { useState } from 'react';
import {
  useWebhooks,
  useCreateWebhook,
  useWebhookDeliveries,
} from '@/hooks/use-plugins';
import type { Webhook } from '@/types/plugin';

const EVENT_TYPES = [
  'asset.uploaded',
  'asset.processed',
  'asset.deleted',
  'annotation.created',
  'annotation.updated',
  'annotation.deleted',
  'event.created',
  'event.updated',
  'event.accepted',
  'export.completed',
  'case.created',
  'case.archived',
] as const;

interface DeliveryLogProps {
  pluginId: string;
  webhookId: string;
}

function DeliveryLog({
  pluginId,
  webhookId,
}: DeliveryLogProps): React.ReactElement {
  const { data, isLoading } = useWebhookDeliveries(pluginId, webhookId);

  if (isLoading) {
    return <div>Loading deliveries...</div>;
  }

  const deliveries = data?.items ?? [];

  if (deliveries.length === 0) {
    return <p className="text-sm text-muted-foreground">No deliveries yet</p>;
  }

  return (
    <table data-testid="delivery-log" className="w-full text-sm">
      <thead>
        <tr className="border-b text-left">
          <th className="pb-2">Event</th>
          <th className="pb-2">Status</th>
          <th className="pb-2">Delivered</th>
        </tr>
      </thead>
      <tbody>
        {deliveries.map((d) => (
          <tr key={d.id} className="border-b">
            <td className="py-2">{d.eventType}</td>
            <td className="py-2">
              <span
                className={`inline-flex rounded-full px-2 py-0.5 text-xs ${
                  d.statusCode && d.statusCode < 300
                    ? 'bg-green-100 text-green-800'
                    : 'bg-red-100 text-red-800'
                }`}
              >
                {d.statusCode ?? 'failed'}
              </span>
            </td>
            <td className="py-2 text-muted-foreground">
              {d.deliveredAt ?? 'pending'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface WebhookConfigProps {
  pluginId: string;
}

export function WebhookConfig({
  pluginId,
}: WebhookConfigProps): React.ReactElement {
  const [url, setUrl] = useState('');
  const [secret, setSecret] = useState('');
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [expandedWebhook, setExpandedWebhook] = useState<string | null>(null);

  const { data, isLoading } = useWebhooks(pluginId);
  const createWebhook = useCreateWebhook(pluginId);

  const handleToggleEvent = (event: string): void => {
    setSelectedEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event],
    );
  };

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!url || selectedEvents.length === 0) return;

    createWebhook.mutate(
      {
        plugin_id: pluginId,
        url,
        events: selectedEvents,
        secret: secret || undefined,
      },
      {
        onSuccess: () => {
          setUrl('');
          setSecret('');
          setSelectedEvents([]);
        },
      },
    );
  };

  const webhooks: Webhook[] = data?.items ?? [];

  return (
    <div data-testid="webhook-config">
      <h3 className="mb-4 font-medium">Webhooks</h3>

      {/* create form */}
      <form
        onSubmit={handleSubmit}
        className="mb-6 space-y-4 rounded-lg border p-4"
      >
        <div>
          <label htmlFor="webhook-url" className="block text-sm font-medium">
            URL
          </label>
          <input
            id="webhook-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/webhook"
            className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            required
          />
        </div>

        <div>
          <label htmlFor="webhook-secret" className="block text-sm font-medium">
            Secret (optional)
          </label>
          <input
            id="webhook-secret"
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="HMAC signing secret"
            className="mt-1 block w-full rounded-md border px-3 py-2 text-sm"
          />
        </div>

        <div>
          <span className="block text-sm font-medium">Events</span>
          <div
            data-testid="event-checkboxes"
            className="mt-2 grid grid-cols-2 gap-2"
          >
            {EVENT_TYPES.map((event) => (
              <label key={event} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selectedEvents.includes(event)}
                  onChange={() => handleToggleEvent(event)}
                  className="rounded border"
                />
                {event}
              </label>
            ))}
          </div>
        </div>

        <button
          type="submit"
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground"
          disabled={!url || selectedEvents.length === 0}
        >
          Add Webhook
        </button>
      </form>

      {/* existing webhooks */}
      {isLoading ? (
        <div>Loading webhooks...</div>
      ) : webhooks.length === 0 ? (
        <p className="text-muted-foreground">No webhooks configured</p>
      ) : (
        <div className="space-y-3">
          {webhooks.map((webhook) => (
            <div key={webhook.id} className="rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">{webhook.url}</p>
                  <p className="text-sm text-muted-foreground">
                    {webhook.events.join(', ')}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      webhook.isActive
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {webhook.isActive ? 'Active' : 'Inactive'}
                  </span>
                  <button
                    onClick={() =>
                      setExpandedWebhook(
                        expandedWebhook === webhook.id ? null : webhook.id,
                      )
                    }
                    className="rounded-md border px-3 py-1 text-xs"
                  >
                    Deliveries
                  </button>
                </div>
              </div>
              {expandedWebhook === webhook.id && (
                <div className="mt-4 border-t pt-4">
                  <DeliveryLog pluginId={pluginId} webhookId={webhook.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
