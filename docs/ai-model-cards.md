# AI Model Cards

Every AI-produced row in Loom — transcript segments, OCR
regions, and detected scenes — carries three fields:
`model_name`, `model_version`, and `model_params`. These are
written at inference time by `build_provenance()` in
`backend/src/loom/services/model_metadata.py` and stored in
the database alongside the result. The UI reads them to link
each row back to the relevant card below.

All AI components are **optional extras**. Install them with:

```
uv sync --extra ai
```

If a component is not installed, the pipeline degrades
gracefully: transcription returns a stub row, OCR and
diarization return empty lists, and scene detection returns a
single scene covering the full video.

---

## faster-whisper — Speech-to-Text

### Package

```
faster-whisper>=1.0.0
```

(`[project.optional-dependencies].ai` in `pyproject.toml`)

### Model variant

`WhisperModel("base", compute_type="int8")`

The `base` multilingual Whisper model running in INT8 mode
for CPU efficiency. Model size and compute type are recorded
in `model_params` per row.

### Where it is invoked

- Service: `backend/src/loom/services/transcription.py`,
  function `transcribe_audio`
- Activity: `backend/src/loom/workflows/
  transcription_activities.py`, activity `store_transcript`

### Intended use

Produces time-stamped text transcripts of spoken audio so
reviewers can search, annotate, and correlate statements
across evidence files without replaying recordings.

### Known limitations

- The `base` model has higher word error rates than `medium`
  or `large` variants, especially on accented English, heavy
  background noise, domain-specific terminology, and proper
  nouns (names of individuals, places, organizations).
- Outputs `avg_log_prob` as a confidence proxy. This is a
  log-probability, not a calibrated probability; treat low
  values as a flag for human review, not a precise score.
- Overlapping speakers degrade accuracy significantly.
  Diarization (pyannote below) is applied after transcription
  to assign speaker labels, but the underlying text may still
  merge voices in dense overlap.
- Language detection is best-effort. Short clips or clips with
  multiple languages may be mis-detected.
- No punctuation normalization is applied beyond what Whisper
  emits natively.

### Evaluation metrics

No Loom-specific benchmark has been run. Upstream word error
rate benchmarks are published by OpenAI (Whisper paper,
Radford et al. 2022) and the faster-whisper project. See:
- https://arxiv.org/abs/2212.04356 (Whisper paper)
- https://github.com/SYSTRAN/faster-whisper

### What it does NOT do

- Does not identify who is speaking. Speaker assignment is a
  separate step (pyannote, below).
- Does not perform sentiment analysis, risk scoring, or any
  behavioral inference.
- Does not perform identity resolution of any kind.

---

## Cloud transcription (opt-in, BYO key) — Speech-to-Text

An alternative to on-device faster-whisper. Off by default; an admin
enables it per install under **Settings → AI & models**. When enabled,
the original audio/video of each transcribed asset is sent to a
third-party provider you configure, and the egress is recorded in the
asset's chain of custody. No package install is required — only your API
key (and, for self-hosted, a server URL).

No frontier-provider option is offered: every cloud transport is
self-hosted or a custom endpoint you point at yourself (Ollama, vLLM,
TGI, LM Studio, whisper.cpp-server, or anything else speaking the
OpenAI-compatible `/audio/transcriptions` API). Loom never bundles or
auto-starts an inference server — you run it, Loom just calls it.

### Where it is invoked

- Service: `backend/src/loom/services/transcription.py`,
  `transcribe_via_cloud` (re-validates the endpoint immediately before
  every request, then calls `_transcribe_openai_audio`).
- Activity: `backend/src/loom/workflows/transcription_activities.py`,
  activity `store_transcript`, only when cloud is enabled.
- Catalog: `backend/src/loom/services/ai_providers.py` is the single
  source of truth for the provider/model dropdowns.

### Providers and models

| Group | Provider | Transport | Curated models |
|---|---|---|---|
| Open-source / self-hosted | your server | `/audio/transcriptions` | whisper-large-v3, whisper-large-v3-turbo, distil-whisper-large-v3 |
| Custom | your endpoint | `/audio/transcriptions` | free-form |

Model IDs are curated in the catalog and updated as providers ship new
ones; they are not discovered live. A free-form model id is always
accepted regardless of provider, so a self-hosted server exposing a
model that isn't in the curated list still works.

### Provenance

Each segment is stored with `model_name = "cloud:<model>"`,
`model_version = "api"`, and `model_params = {provider, endpoint,
model}`, so a cloud-produced transcript is distinguishable from an
on-device one and traceable to the exact provider and endpoint used.

### Known limitations

- **Egress.** Audio leaves the machine to whatever endpoint you
  configured. This is the only transcription path that does, it is
  opt-in, and every send is logged to chain of custody.
- **Segments vs. text.** OpenAI-compatible endpoints return timed
  segments (`verbose_json`) when the server supports it; otherwise the
  response is stored as a single full-file segment with no per-line
  timestamps.
- **No cloud diarization.** Speaker labels come from the on-device
  pyannote step, which does not run for cloud transcripts.
- Accuracy, language coverage, and rate limits are whatever server you
  pointed Loom at.
- **Endpoint safety.** The configured base URL is re-validated on every
  request (not just when saved): link-local, cloud-metadata, and other
  reserved address ranges are always rejected; loopback targets are only
  permitted on the single-machine desktop (`lite`) profile; any
  non-loopback target must use https. See
  `backend/src/loom/services/ai_config.py`.

### What it does NOT do

- Does not run unless an admin explicitly enables it and supplies a key.
- Does not send anything for on-device transcription, OCR, or scene
  detection — those never use the cloud.
- No face recognition, suspicion scoring, or automated identity
  resolution of any kind — the same project principles apply to cloud
  output.

---

## Text generation (opt-in, BYO endpoint) — Case Narrative

A second, independent AI capability alongside cloud transcription: an
opt-in, admin-configured self-hosted or custom OpenAI-compatible chat
endpoint, used to draft a plain-language narrative over **a case's own
structured metadata** — chain-of-custody entries for an asset, or a
case's audit log — never over evidentiary content. There is nothing for
the model to hallucinate *about* beyond phrasing, since every claim in
the draft is checkable against the very rows it summarized.

### Where it is invoked

- Settings: `backend/src/loom/services/ai_config.py`
  (`TextGenConfig`, key `"ai_text_generation"`) and
  `backend/src/loom/services/text_generation_providers.py` (catalog).
- Generation: `backend/src/loom/services/narrative_generation.py`,
  function `generate_narrative`.
- API: `POST /cases/{case_id}/narratives` (case editor+),
  `GET /cases/{case_id}/narratives`,
  `POST /cases/{case_id}/narratives/{id}/approve|reject` (editor+).

### What is sent, and what is not

Only structured rows already rendered in Loom's own UI: a
`ChainOfCustodyEntry` per asset, or `AuditLogEntry` rows scoped to a
case (the same feed shown as "Recent Activity" on the case Overview
tab). **Never** transcript text, OCR text, annotation content, or any
other evidentiary material — the generation service's input type only
accepts typed audit/custody rows, not an ORM object it could reach
further into.

### Human review gate

Every draft starts as `status="draft"` — inert, not exportable. Only a
dedicated approve/reject endpoint (never a generic update) can change
that, and doing so is itself audited. **Only `status == "approved"`
narratives are ever eligible for inclusion in a report, court bundle,
or export manifest** — enforced in
`backend/src/loom/services/report.py`,
`backend/src/loom/services/court_bundle.py`, and
`backend/src/loom/services/export.py`. The UI shows a persistent
"AI-drafted" badge on every narrative, before and after review — it
never disappears, so an AI-drafted narrative can never be mistaken for
verified evidence.

### Known limitations

- Generation is refused while a case is under litigation hold.
- Refused if text generation isn't configured, or if there are no
  custody/audit entries to summarize.
- Endpoint safety follows the same rules as cloud transcription
  (request-time re-validation, banned address ranges, loopback
  restricted to the `lite` profile, https required for non-loopback).
- Not yet extended to transcript, OCR, or annotation content — doing so
  would first require transcript-level redaction support, which does
  not exist today (redactions only ever apply to derivative media).

### What it does NOT do

- Does not run unless an admin explicitly enables text generation and
  a case editor+ triggers it.
- Does not send transcript, OCR, or annotation content — ever.
- Does not enter any export until a human explicitly approves it.

---

## pyannote.audio — Speaker Diarization

### Package

```
pyannote.audio>=3.1.0
```

### Model variant

`Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")`

The pretrained `pyannote/speaker-diarization-3.1` pipeline
loaded from Hugging Face. The pipeline name is stored as
`model_name` per row.

### Where it is invoked

- Service: `backend/src/loom/services/transcription.py`,
  function `diarize_audio`
- Activity: `backend/src/loom/workflows/
  transcription_activities.py`, activity `store_transcript`

Diarization runs after transcription. Results are merged with
transcript segments via `align_transcript_with_speakers`,
which assigns the speaker label with the greatest time overlap
to each segment. The merged `speaker_label` field is stored on
`transcript_segments` rows.

### Intended use

Assigns anonymous speaker turns to transcript segments so
reviewers can filter by speaker (`SPEAKER_0`, `SPEAKER_1`,
etc.) and follow a single voice through a recording.

### Known limitations

- Speaker labels are arbitrary sequential identifiers
  (`SPEAKER_0`, `SPEAKER_1`, …). They carry no identity
  information and are not consistent across separate files or
  runs.
- Accuracy drops with more than ~4 overlapping speakers,
  very short turns (<1 second), or low-quality audio.
- Cross-talk (simultaneous speech) may be assigned to a
  single speaker or split inconsistently.
- The model requires a Hugging Face token and network access
  to download the pretrained pipeline on first use. If the
  pipeline cannot be loaded, diarization is skipped silently
  and `speaker_label` is left null on all segments.

### Evaluation metrics

No Loom-specific benchmark has been run. Upstream diarization
error rate (DER) results are published on the pyannote.audio
model card:
- https://huggingface.co/pyannote/speaker-diarization-3.1

### What it does NOT do

- Does **not** identify or name any individual. Labels like
  `SPEAKER_0` are anonymous placeholders with no link to any
  person's identity.
- Does not perform voice-print matching across files.
- Does not perform any form of biometric identification.
- No face recognition, suspicion scoring, or automated
  identity resolution of any kind.

---

## pytesseract — Optical Character Recognition

### Package

```
pytesseract>=0.3.10
Pillow>=12.2.0
```

### Model variant

`pytesseract.image_to_data(img, lang="eng",
output_type=pytesseract.Output.DICT)`

Tesseract 4.x LSTM engine, English language pack by default.
The `language` parameter is stored in `model_params` per row.
Bounding boxes are normalized to the `[0, 1]` range relative
to image dimensions.

### Where it is invoked

- Service: `backend/src/loom/services/ocr.py`, functions
  `run_ocr_on_image` and `run_ocr_on_asset`
- Activity: `backend/src/loom/workflows/ocr_activities.py`,
  activity `store_ocr_results`

For video assets, frames are extracted by ffmpeg at 5-second
intervals before OCR is applied. For images, OCR runs
directly. Documents (`application/*`) are not yet supported
and return an empty result.

### Intended use

Surfaces visible text in evidence files — signs, captions,
documents, badge numbers, vehicle plates — so reviewers can
search and annotate without manual transcription.

### Known limitations

- Low-contrast text (light on light, dark on dark) yields
  poor results or is missed entirely.
- Rotated, skewed, or perspective-distorted text degrades
  accuracy significantly.
- Handwritten text is not reliably recognized by the LSTM
  engine.
- Small or low-resolution text (e.g., distant signage) is
  frequently missed.
- Multi-column layouts may produce jumbled word order in the
  output.
- Languages other than English require installing additional
  Tesseract language packs. The `lang` parameter can be
  overridden but the packs must be present on the host.
- OCR runs on key frames sampled every 5 seconds; text visible
  only in between sample points will be missed in video.
- The `confidence` field (normalized to 0–1) is Tesseract's
  internal heuristic score; it is not calibrated against a
  ground-truth dataset.

### Evaluation metrics

No Loom-specific benchmark has been run. Tesseract accuracy
data by script and engine mode is published by the upstream
project:
- https://github.com/tesseract-ocr/tesseract/blob/main/
  doc/tesseract_accuracy.md

### What it does NOT do

- Does not perform facial recognition or identify individuals
  in images.
- Does not interpret image content beyond character
  recognition.
- Does not perform any behavioral or risk inference.

---

## scenedetect — Shot-Boundary Detection

### Package

```
scenedetect[opencv]>=0.6.0
```

### Model variant

`ContentDetector(threshold=27.0)`

PySceneDetect's `ContentDetector` using the default threshold
of 27.0 (HSV content difference). The threshold value is
stored in `model_params` per row. Scene detection is
heuristic-based, not a learned neural model.

### Where it is invoked

- Service: `backend/src/loom/services/scene_detection.py`,
  function `detect_scenes`
- Activity: `backend/src/loom/workflows/scene_activities.py`,
  activities `detect_asset_scenes` and `store_scene_results`

If scenedetect is not installed, or if the video cannot be
opened, a single scene covering the full video is returned
with `model_version` set to `"unknown"`. The UI can use this
sentinel to flag rows that lack model-backed detection.

### Intended use

Segments video evidence into discrete shots so reviewers can
navigate large files by scene rather than frame-by-frame, and
can attach annotations to specific scenes.

### Known limitations

- `ContentDetector` detects hard cuts based on pixel-level
  content changes. It will miss slow cross-fades, dissolves,
  and gradual brightness shifts.
- High-motion footage (crowds, handheld cameras, flickering
  lights) may trigger false positives — cuts detected where
  none exist.
- The threshold of 27.0 is a project default tuned for
  typical footage. It is not adaptive; unusual lighting or
  codec artifacts may require manual adjustment.
- Very short scenes (<1 second) may be merged with adjacent
  scenes depending on codec frame-rate.
- Scene boundaries are approximated to the nearest frame;
  sub-frame precision is not available.

### Evaluation metrics

No Loom-specific benchmark has been run. PySceneDetect does
not publish a formal accuracy benchmark for `ContentDetector`.
The algorithm is documented at:
- https://www.scenedetect.com/docs/latest/

### What it does NOT do

- Does not identify individuals, objects, or activities in
  video frames.
- Does not classify scene content in any way.
- Does not perform facial recognition, object detection,
  action recognition, or any behavioral inference.
- No face recognition, suspicion scoring, or automated
  identity resolution of any kind.

---

## ffmpeg — Deterministic Clarity Assist

Not an AI model. Included here because enhanced derivatives
carry the same `model_name` / `model_version` / `model_params`
provenance fields as AI-produced rows, with
`model_name="ffmpeg-deterministic-filter"`.

### Package

`ffmpeg` (system binary), invoked by
`backend/src/loom/services/enhancement.py`.

### Where it is invoked

`enhance_video()` and `enhance_image()` produce an enhanced
derivative of a video or image asset. `analyze_video()` +
`suggest_params()` measure luma statistics (`signalstats`) and
interlacing (`idet`) on a leading sample and map them to
suggested starting parameters via fixed, documented thresholds.

### Intended use

Make dark, flat, noisy, interlaced, or low-resolution footage
easier for a human reviewer to see. Classical filters only:
deinterlace (yadif), denoise (hqdn3d), brightness/contrast/
saturation/gamma (eq), sharpen (unsharp), and Lanczos upscale.
The filter chain order is fixed and recorded; identical
parameters always produce the identical chain.

### Known limitations

- Enhancement brings out what the camera captured; it cannot
  recover detail that was never recorded.
- Upscaling interpolates existing pixels (Lanczos); it adds
  smoothness, not information.
- Auto-suggestions are heuristic starting points measured from
  the first seconds of footage; a human adjusts and confirms
  before any derivative is generated.

### What it does NOT do

- No AI super-resolution or generative enhancement of any
  kind, by policy: generative models hallucinate detail that
  was never captured, which is indefensible for evidence.
- Does not modify originals. Output is a separate derivative
  labeled as enhanced, with the full parameter set and rendered
  filter chain stored in `generation_params`.
- No face recognition, suspicion scoring, or automated
  identity resolution of any kind.

---

## Reproducibility

The `model_version` field on every AI-produced row is captured
from `importlib.metadata.version()` at inference time (see
`backend/src/loom/services/model_metadata.py`). This records
the exact installed package version, not just the range
declared in `pyproject.toml`. A row produced with
`faster-whisper==1.1.0` is distinguishable from one produced
with `faster-whisper==1.0.3` even if both satisfy
`>=1.0.0`.

When a component is not installed, `model_version` is set to
`"unknown"`. The UI should treat `"unknown"` as the canonical
marker for rows where provenance was not recorded, and surface
them for human review rather than treating them as equivalent
to model-backed rows.

Upgrading a package version will not retroactively change
existing rows. If reprocessing is needed after an upgrade,
existing rows must be cleared before re-running the relevant
workflow activity.
