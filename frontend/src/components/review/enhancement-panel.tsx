import { useState } from 'react';
import { useCapabilities } from '@/hooks/use-capabilities';
import {
  type EnhancementParams,
  NEUTRAL_PARAMS,
  useCreateEnhancement,
  useEnhancements,
  useSuggestEnhancement,
} from '@/hooks/use-enhancements';
import { WhyPopover } from './why-popover';

interface EnhancementPanelProps {
  caseId: string;
  assetId: string;
  filename?: string;
}

// numeric sliders share the exact ranges the backend dataclass
// validates, so an out-of-range value can never be submitted
const SLIDERS: {
  key: keyof EnhancementParams;
  label: string;
  min: number;
  max: number;
  step: number;
}[] = [
  { key: 'brightness', label: 'Brightness', min: -1, max: 1, step: 0.05 },
  { key: 'contrast', label: 'Contrast', min: 0, max: 4, step: 0.05 },
  { key: 'saturation', label: 'Saturation', min: 0, max: 3, step: 0.05 },
  { key: 'gamma', label: 'Gamma', min: 0.1, max: 10, step: 0.1 },
  { key: 'denoise', label: 'Denoise', min: 0, max: 10, step: 1 },
  { key: 'sharpen', label: 'Sharpen', min: 0, max: 5, step: 0.1 },
];

export function EnhancementPanel(
  props: EnhancementPanelProps,
): React.ReactElement {
  const { caseId, assetId, filename } = props;

  const [params, setParams] = useState<EnhancementParams>(NEUTRAL_PARAMS);
  const [reasons, setReasons] = useState<string[]>([]);

  const { data: capabilities } = useCapabilities();
  const { data: enhancements } = useEnhancements(caseId, assetId);
  const suggest = useSuggestEnhancement(caseId, assetId);
  const create = useCreateEnhancement(caseId, assetId, filename);

  // gate only on a confirmed "missing"; while capabilities load the
  // backend stays the authority (mirrors the review page)
  const media = capabilities?.engines.mediaPipeline;
  const available = !media || media.status === 'available';
  const remedy = media?.remedy ?? undefined;

  const setParam = (key: keyof EnhancementParams, value: number): void =>
    setParams((prev) => ({ ...prev, [key]: value }));

  const onSuggest = (): void =>
    suggest.mutate(undefined, {
      onSuccess: (data) => {
        setParams(data.params);
        setReasons(data.reasons);
      },
    });

  return (
    <div
      data-testid="enhancement-panel"
      className="flex h-full flex-col overflow-y-auto p-3 text-sm"
    >
      <h2 className="mb-1 font-semibold">Clarity assist</h2>
      <p
        data-testid="enhancement-policy"
        className="text-muted-foreground mb-3 text-xs"
      >
        Deterministic filters only — no AI, no super-resolution.
      </p>

      {!available && (
        <p
          data-testid="enhancement-unavailable"
          role="alert"
          className="border-border text-muted-foreground mb-3 rounded border p-2 text-xs"
        >
          {remedy ?? 'Media pipeline (ffmpeg) is not available.'}
        </p>
      )}

      <fieldset disabled={!available} className="space-y-2">
        {SLIDERS.map((s) => (
          <label key={s.key} htmlFor={`enh-${s.key}`} className="block text-xs">
            <span className="flex justify-between">
              <span>{s.label}</span>
              <span className="font-mono">{String(params[s.key])}</span>
            </span>
            <input
              id={`enh-${s.key}`}
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={params[s.key] as number}
              onChange={(e) => setParam(s.key, Number(e.target.value))}
              className="w-full"
            />
          </label>
        ))}

        <label htmlFor="enh-scale" className="block text-xs">
          <span className="mb-1 block">Upscale</span>
          <select
            id="enh-scale"
            value={params.scaleFactor}
            onChange={(e) => setParam('scaleFactor', Number(e.target.value))}
            className="border-border w-full rounded border bg-transparent px-2 py-1"
          >
            <option value={1}>1x (none)</option>
            <option value={2}>2x</option>
            <option value={4}>4x</option>
          </select>
        </label>

        <label
          htmlFor="enh-deinterlace"
          className="flex items-center gap-2 text-xs"
        >
          <input
            id="enh-deinterlace"
            type="checkbox"
            checked={params.deinterlace}
            onChange={(e) =>
              setParams((prev) => ({
                ...prev,
                deinterlace: e.target.checked,
              }))
            }
          />
          <span>Deinterlace</span>
        </label>
      </fieldset>

      <div className="mt-3 flex gap-2">
        <button
          type="button"
          data-testid="enhancement-suggest"
          onClick={onSuggest}
          disabled={!available || suggest.isPending}
          className="border-border rounded border px-3 py-1 text-xs font-medium disabled:opacity-50"
        >
          {suggest.isPending ? 'Analyzing...' : 'Suggest'}
        </button>
        <button
          type="button"
          data-testid="enhancement-run"
          onClick={() => create.mutate(params)}
          disabled={!available || create.isPending}
          className="bg-primary text-primary-foreground rounded px-3 py-1 text-xs font-medium disabled:opacity-50"
        >
          {create.isPending ? 'Starting...' : 'Enhance'}
        </button>
      </div>

      {reasons.length > 0 && (
        <ul
          data-testid="enhancement-reasons"
          className="text-muted-foreground mt-3 list-disc space-y-1 pl-4 text-xs"
        >
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}

      <div className="mt-4">
        <h3 className="mb-1 text-xs font-semibold">Enhancements</h3>
        {enhancements && enhancements.length > 0 ? (
          <ul className="space-y-2">
            {enhancements.map((item) => (
              <li
                key={item.id}
                data-testid="enhancement-item"
                className="border-border flex items-center justify-between gap-2 rounded border p-2 text-xs"
              >
                <a
                  href={item.downloadUrl}
                  className="text-primary underline"
                  download
                >
                  Download
                </a>
                <WhyPopover
                  modelName={item.generationParams?.modelName ?? null}
                  modelVersion={item.generationParams?.modelVersion ?? null}
                  modelParams={item.generationParams?.modelParams ?? null}
                  confidence={null}
                  scope="Deterministic enhancement"
                  label="Provenance"
                />
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-xs">No enhancements yet.</p>
        )}
      </div>
    </div>
  );
}
