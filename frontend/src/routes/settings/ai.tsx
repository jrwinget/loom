import { useMemo, useState } from 'react';

import { EnginesPanel } from '@/components/settings/engines-panel';
import {
  useAiProviders,
  useAiSettings,
  useTextGenProviders,
  useTextGenSettings,
  useUpdateAiSettings,
  useUpdateTextGenSettings,
  type AiProvider,
  type AiSettings,
  type AiSettingsUpdate,
  type TextGenProvider,
  type TextGenSettings,
  type TextGenSettingsUpdate,
} from '@/hooks/use-ai-settings';

const GROUP_LABELS: Record<string, string> = {
  oss: 'Open-source / self-hosted',
  custom: 'Custom',
};
const GROUP_ORDER = ['oss', 'custom'];

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
  const [whisperModel, setWhisperModel] = useState(initial.whisperModel);
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
    if (!cloud) patch.whisper_model = whisperModel;
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
        <legend className="text-foreground text-sm font-medium">
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
            <span className="text-foreground font-medium">On-device</span>
            <span className="text-muted-foreground block">
              Runs locally; nothing leaves this machine. Requires a downloaded
              speech model (see below).
            </span>
            {!cloud && (
              <label className="mt-2 block text-sm">
                <span className="text-muted-foreground">Speech model</span>
                <select
                  data-testid="whisper-model-select"
                  value={whisperModel}
                  onChange={(e) => setWhisperModel(e.target.value)}
                  className="border-border bg-background ml-2 rounded border px-2 py-1"
                >
                  <option value="tiny">tiny (fastest)</option>
                  <option value="base">base (balanced)</option>
                  <option value="small">small (most accurate)</option>
                </select>
              </label>
            )}
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
            <span className="text-foreground font-medium">
              Cloud (your API key)
            </span>
            <span className="text-muted-foreground block">
              Sends audio to a provider you choose and configure below.
            </span>
          </span>
        </label>
      </fieldset>

      {cloud && !initial.providerAvailable && (
        <p
          role="alert"
          data-testid="provider-unavailable-banner"
          className={
            'rounded bg-red-100 px-3 py-2 text-xs text-red-900 ' +
            'dark:bg-red-900 dark:text-red-100'
          }
        >
          Your configured transcription provider is no longer supported;
          on-device transcription is being used instead. Choose a new provider
          below.
        </p>
      )}
      {cloud && initial.providerAvailable && !initial.keyDecryptable && (
        <p
          role="alert"
          data-testid="key-undecryptable-banner"
          className={
            'rounded bg-red-100 px-3 py-2 text-xs text-red-900 ' +
            'dark:bg-red-900 dark:text-red-100'
          }
        >
          The stored API key can&apos;t be read on this machine (it may have
          been set up on a different install). Re-enter it below.
        </p>
      )}

      {cloud && (
        <div className="border-border space-y-4 rounded border p-4">
          <p
            role="note"
            className={
              'rounded bg-yellow-100 px-3 py-2 text-xs text-yellow-900 ' +
              'dark:bg-yellow-900 dark:text-yellow-100'
            }
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
              className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
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
            <p className="text-muted-foreground text-xs">{selected.note}</p>
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
                    className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
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
                    className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
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
                    'border-border mt-1 w-full rounded border px-2 py-1 ' +
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
                  className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
                />
              </label>
            </>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={update.isPending || !canSave}
        className="bg-primary text-primary-foreground hover:bg-primary/90 rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {update.isPending ? 'Saving…' : 'Save transcription settings'}
      </button>
    </form>
  );
}

function TextGenSettingsForm(props: {
  initial: TextGenSettings;
  providers: TextGenProvider[];
}): React.ReactElement {
  const { initial, providers } = props;
  const update = useUpdateTextGenSettings();

  const [enabled, setEnabled] = useState(initial.enabled);
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.model);
  const [baseUrl, setBaseUrl] = useState(initial.apiBaseUrl);
  const [apiKey, setApiKey] = useState('');

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

  const hasModelCatalog = (selected?.models.length ?? 0) > 0;
  const baseUrlEditable = selected?.baseUrlEditable ?? false;

  const onProviderChange = (id: string): void => {
    setProvider(id);
    const next = providers.find((p) => p.id === id);
    if (!next) return;
    if (next.models.length > 0) setModel(next.models[0].id);
    if (!next.baseUrlEditable) setBaseUrl(next.baseUrl);
  };

  const canSave = !enabled || (provider !== '' && model !== '');

  const handleSave = (e: React.FormEvent): void => {
    e.preventDefault();
    const patch: TextGenSettingsUpdate = { enabled };
    if (enabled) {
      patch.provider = provider;
      patch.model = model;
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
        <legend className="text-foreground text-sm font-medium">
          Text generation
        </legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
            className="mt-1"
            data-testid="text-gen-enabled-checkbox"
          />
          <span>
            <span className="text-foreground font-medium">
              Enable AI-drafted text
            </span>
            <span className="text-muted-foreground block">
              Point Loom at a self-hosted or custom chat-completions endpoint
              you run. Off by default; no feature currently sends anything to
              it.
            </span>
          </span>
        </label>
      </fieldset>

      {enabled && !initial.providerAvailable && (
        <p
          role="alert"
          data-testid="text-gen-provider-unavailable-banner"
          className={
            'rounded bg-red-100 px-3 py-2 text-xs text-red-900 ' +
            'dark:bg-red-900 dark:text-red-100'
          }
        >
          Your configured text-generation provider is no longer supported.
          Choose a new provider below.
        </p>
      )}
      {enabled && initial.providerAvailable && !initial.keyDecryptable && (
        <p
          role="alert"
          data-testid="text-gen-key-undecryptable-banner"
          className={
            'rounded bg-red-100 px-3 py-2 text-xs text-red-900 ' +
            'dark:bg-red-900 dark:text-red-100'
          }
        >
          The stored API key can&apos;t be read on this machine (it may have
          been set up on a different install). Re-enter it below.
        </p>
      )}

      {enabled && (
        <div className="border-border space-y-4 rounded border p-4">
          <label className="block text-sm">
            <span className="text-muted-foreground">Provider</span>
            <select
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
              data-testid="text-gen-provider-select"
              className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
            >
              <option value="">Select a provider…</option>
              {grouped.map((g) => (
                <optgroup key={g.group} label={g.label}>
                  {g.items.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          {selected?.note && (
            <p className="text-muted-foreground text-xs">{selected.note}</p>
          )}

          {selected && (
            <>
              <label className="block text-sm">
                <span className="text-muted-foreground">Model</span>
                {hasModelCatalog ? (
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    data-testid="text-gen-model-select"
                    className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
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
                    placeholder="my-model"
                    data-testid="text-gen-model-input"
                    className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
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
                  data-testid="text-gen-base-url-input"
                  className={
                    'border-border mt-1 w-full rounded border px-2 py-1 ' +
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
                  className="border-border bg-background mt-1 w-full rounded border px-2 py-1"
                />
              </label>
            </>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={update.isPending || !canSave}
        className="bg-primary text-primary-foreground hover:bg-primary/90 rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
      >
        {update.isPending ? 'Saving…' : 'Save text-generation settings'}
      </button>
    </form>
  );
}

export function AiSettingsPage(): React.ReactElement {
  const settings = useAiSettings();
  const providers = useAiProviders();
  const textGenSettings = useTextGenSettings();
  const textGenProviders = useTextGenProviders();
  const ready = settings.data != null && providers.data != null;
  const textGenReady =
    textGenSettings.data != null && textGenProviders.data != null;

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-foreground text-xl font-semibold">AI &amp; models</h1>
      <p className="text-muted-foreground mt-1 text-sm">
        Choose how transcription runs. OCR and scene detection run on-device
        only.
      </p>
      {!ready ? (
        <p className="text-muted-foreground mt-6 text-sm">Loading…</p>
      ) : (
        <AiSettingsForm initial={settings.data} providers={providers.data} />
      )}
      {!textGenReady ? (
        <p className="text-muted-foreground mt-6 text-sm">Loading…</p>
      ) : (
        <TextGenSettingsForm
          initial={textGenSettings.data}
          providers={textGenProviders.data}
        />
      )}
      <EnginesPanel />
    </div>
  );
}
