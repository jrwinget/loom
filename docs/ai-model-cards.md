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
