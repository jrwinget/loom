import { useState } from 'react';

import {
  useAiSettings,
  useUpdateAiSettings,
  type AiSettings,
  type AiSettingsUpdate,
} from '@/hooks/use-ai-settings';

function AiSettingsForm(props: { initial: AiSettings }): React.ReactElement {
  const { initial } = props;
  const update = useUpdateAiSettings();

  const [engine, setEngine] = useState(initial.transcriptionEngine);
  const [baseUrl, setBaseUrl] = useState(initial.apiBaseUrl);
  const [model, setModel] = useState(initial.transcriptionModel);
  const [apiKey, setApiKey] = useState('');

  const cloud = engine === 'cloud';

  const handleSave = (e: React.FormEvent): void => {
    e.preventDefault();
    const patch: AiSettingsUpdate = {
      transcription_engine: engine,
      api_base_url: baseUrl,
      transcription_model: model,
    };
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
              Sends audio to an OpenAI-compatible provider you configure.
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
            <span className="text-muted-foreground">API base URL</span>
            <input
              type="url"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
            />
          </label>
          <label className="block text-sm">
            <span className="text-muted-foreground">Model</span>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="whisper-1"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
            />
          </label>
          <label className="block text-sm">
            <span className="text-muted-foreground">
              API key{' '}
              {initial.apiKeySet && (
                <span className="text-green-700">(a key is configured)</span>
              )}
            </span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={initial.apiKeySet ? '•••••••• (unchanged)' : 'sk-…'}
              autoComplete="off"
              className="mt-1 w-full rounded border border-border bg-background px-2 py-1"
            />
          </label>
        </div>
      )}

      <button
        type="submit"
        disabled={update.isPending}
        className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {update.isPending ? 'Saving…' : 'Save'}
      </button>
    </form>
  );
}

export function AiSettingsPage(): React.ReactElement {
  const { data, isLoading } = useAiSettings();

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold text-foreground">AI &amp; models</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Choose how transcription runs. OCR and scene detection run on-device
        only.
      </p>
      {isLoading || !data ? (
        <p className="mt-6 text-sm text-muted-foreground">Loading…</p>
      ) : (
        <AiSettingsForm initial={data} />
      )}
    </div>
  );
}
