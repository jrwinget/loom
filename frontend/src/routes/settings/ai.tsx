import { useMemo, useState } from 'react';

import {
  useAiProviders,
  useAiSettings,
  useUpdateAiSettings,
  type AiProvider,
  type AiSettings,
  type AiSettingsUpdate,
} from '@/hooks/use-ai-settings';

const GROUP_LABELS: Record<string, string> = {
  frontier: 'Frontier providers',
  oss: 'Open-source / self-hosted',
  custom: 'Custom',
};
const GROUP_ORDER = ['frontier', 'oss', 'custom'];

function AiSettingsForm(props: {
  initial: AiSettings;
  providers: AiProvider[];
}): React.ReactElement {
  const { initial, providers } = props;
  const update = useUpdateAiSettings();

  const [engine, setEngine] = useState(initial.transcriptionEngine);
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.transcriptionModel);
  const [baseUrl, setBaseUrl] = useState(initial.apiBaseUrl);
  const [apiKey, setApiKey] = useState('');

  const cloud = engine === 'cloud';
  const selected = useMemo(
    () => providers.find((p) => p.id === provider),
    [providers, provider],
  );
  const grouped = useMemo(() => {
    return GROUP_ORDER.map((group) => ({
      group,
      label: GROUP_LABELS[group] ?? group,
      items: providers.filter((p) => p.group === group),
    })).filter((g) => g.items.length > 0);
  }, [providers]);

  // a provider with a fixed catalog picks from a dropdown; one with an
  // open list (custom) takes a free-form model id.
  const hasModelCatalog = (selected?.models.length ?? 0) > 0;
  const baseUrlEditable = selected?.baseUrlEditable ?? false;
  const unavailable = selected != null && !selected.available;

  const onProviderChange = (id: string): void => {
    setProvider(id);
    const next = providers.find((p) => p.id === id);
    if (!next) return;
    // seed the model from the new provider's catalog; leave free-form
    // providers' model untouched so a typed value survives re-selection.
    if (next.models.length > 0) setModel(next.models[0].id);
    // lock the base url to the catalog for hosted providers.
    if (!next.baseUrlEditable) setBaseUrl(next.baseUrl);
  };

  const canSave = !cloud || (provider !== '' && !unavailable);

  const handleSave = (e: React.FormEvent): void => {
    e.preventDefault();
    const patch: AiSettingsUpdate = { transcription_engine: engine };
    if (cloud) {
      patch.provider = provider;
      patch.transcription_model = model;
      // only meaningful for editable providers; the backend derives the
      // url from the catalog for hosted ones.
      if (baseUrlEditable) patch.api_base_url = baseUrl;
    }
    // only send the key when the user typed one, so an unchanged form
    // doesn't clear a stored key.
    if (apiKey) patch.api_key = apiKey;
    update.mutate(patch);
    setApiKey('');
  };

  return (
    <form onSubmit={handleSave} className="mt-6 space-y-6">
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-foreground">
          Transcription engine
        </legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="engine"
            value="local"
            checked={!cloud}
            onChange={() => setEngine('local')}
            className="mt-1"
          />
          <span>
            <span className="font-medium text-foreground">On-device</span>
            <span className="block text-muted-foreground">
              Runs locally; nothing leaves this machine. Requires the local
              model to be installed.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="engine"
            value="cloud"
            checked={cloud}
            onChange={() => setEngine('cloud')}
            className="mt-1"
          />
          <span>
            <span className="font-medium text-foreground">
              Cloud (your API key)
            </span>
            <span className="block text-muted-foreground">
              Sends audio to a provider you choose and configure below.
            </span>
          </span>
        </label>
      </fieldset>

      {cloud && (
        <div className="space-y-4 rounded border border-border p-4">
          <p
            role="note"
            className="rounded bg-yellow-100 px-3 py-2 text-xs text-yellow-900"
          >
            Evidence audio will be sent to this provider for processing. Each
            cloud transcription is recorded in the asset&apos;s chain of
            custody.
          </p>

          <label className="block text-sm">
            <span className="text-muted-foreground">Provider</span>
            <select
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
              data-testid="provider-select"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
            >
              <option value="">Select a provider…</option>
              {grouped.map((g) => (
                <optgroup key={g.group} label={g.label}>
                  {g.items.map((p) => (
                    <option key={p.id} value={p.id} disabled={!p.available}>
                      {p.label}
                      {p.available ? '' : ' (unavailable)'}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          {selected?.note && (
            <p className="text-xs text-muted-foreground">{selected.note}</p>
          )}

          {selected && !unavailable && (
            <>
              <label className="block text-sm">
                <span className="text-muted-foreground">Model</span>
                {hasModelCatalog ? (
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    data-testid="model-select"
                    className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
                  >
                    {selected.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="whisper-1"
                    data-testid="model-input"
                    className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
                  />
                )}
              </label>

              <label className="block text-sm">
                <span className="text-muted-foreground">API base URL</span>
                <input
                  type="url"
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  readOnly={!baseUrlEditable}
                  placeholder="https://your-server.example/v1"
                  data-testid="base-url-input"
                  className={
                    'mt-1 w-full rounded border border-border px-2 py-1 ' +
                    (baseUrlEditable
                      ? 'bg-background'
                      : 'bg-muted text-muted-foreground')
                  }
                />
              </label>

              <label className="block text-sm">
                <span className="text-muted-foreground">
                  API key{' '}
                  {initial.apiKeySet && (
                    <span className="text-green-700">
                      (a key is configured)
                    </span>
                  )}
                  {!selected.requiresApiKey && (
                    <span className="text-muted-foreground">
                      (optional for this provider)
                    </span>
                  )}
                </span>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    initial.apiKeySet ? '•••••••• (unchanged)' : 'sk-…'
                  }
                  autoComplete="off"
                  className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
                />
              </label>
            </>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={update.isPending || !canSave}
        className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {update.isPending ? 'Saving…' : 'Save'}
      </button>
    </form>
  );
}

export function AiSettingsPage(): React.ReactElement {
  const settings = useAiSettings();
  const providers = useAiProviders();
  const ready = settings.data != null && providers.data != null;

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold text-foreground">AI &amp; models</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Choose how transcription runs. OCR and scene detection run on-device
        only.
      </p>
      {!ready ? (
        <p className="mt-6 text-sm text-muted-foreground">Loading…</p>
      ) : (
        <AiSettingsForm initial={settings.data} providers={providers.data} />
      )}
    </div>
  );
}
