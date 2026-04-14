export interface Plugin {
  id: string;
  name: string;
  description: string | null;
  version: string;
  pluginType: string;
  isEnabled: boolean;
  config: Record<string, unknown> | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface PluginListResponse {
  items: Plugin[];
  total: number;
}

export interface CreatePluginPayload {
  name: string;
  description?: string;
  version: string;
  plugin_type: string;
  config?: Record<string, unknown>;
}

export interface UpdatePluginPayload {
  description?: string;
  version?: string;
  is_enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface Webhook {
  id: string;
  pluginId: string;
  url: string;
  events: string[];
  isActive: boolean;
  lastTriggeredAt: string | null;
  failureCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface WebhookListResponse {
  items: Webhook[];
  total: number;
}

export interface CreateWebhookPayload {
  plugin_id: string;
  url: string;
  events: string[];
  secret?: string;
}

export interface UpdateWebhookPayload {
  url?: string;
  events?: string[];
  is_active?: boolean;
}

export interface WebhookDelivery {
  id: string;
  eventType: string;
  statusCode: number | null;
  deliveredAt: string | null;
  createdAt: string;
}

export interface WebhookDeliveryListResponse {
  items: WebhookDelivery[];
  total: number;
}
