# Desktop Lite capability matrix

What works on the Desktop (Lite) profile versus the Server profile, and
how Lite achieves it. Lite is single-user, network-isolated, and ships no
external services — so anything that assumed Minio, Temporal, or a public
HTTP origin had to be re-homed onto the in-process sidecar.

This file is enforced in spirit by two tests: `test_route_contract.py`
(every frontend API path resolves to a real route) and
`test_lite_asset_serving_sql.py` (an uploaded asset is actually servable
over HTTP on Lite). Keep it current when adding a profile-divergent
feature.

| Capability | Server | Lite | How / notes |
|---|---|---|---|
| Auth, cases, first-run | ✓ | ✓ | identical |
| File upload | ✓ | ✓ | local filesystem (WORM) on Lite |
| URL ingest (yt-dlp/archive) | ✓ | ✓ | in-process worker; deps bundled |
| Asset preview/download (pdf/img/doc) | ✓ | ✓ | signed http stream from the sidecar (`/api/v1/storage/object/...`) |
| Video/audio playback + seeking | ✓ | ✓ | same endpoint, HTTP Range → 206 |
| Court-bundle export + download | ✓ | ✓ | weasyprint bundled; signed http download |
| Workflow status / health | ✓ | ✓ | Lite reports in-process state |
| Transcription | ✓ | ✓² | on-device (needs local model) **or** opt-in cloud BYO-key (Settings → AI) |
| OCR / scene detection | ✓ | ✓¹ | local on-device only (no cloud option yet) |
| Video proxies / thumbnails / waveforms | ✓ | ✓¹ | needs the bundled ffmpeg binary |
| Organizations / members / plugins | ✓ | — | server-only; hidden on Lite |
| Presigned multipart upload completion | ✓ | — | Minio-only; Lite uploads via `POST /upload` |

¹ AI/media features run on-device by default. If the on-device engine or
ffmpeg is not installed, the step degrades to an empty result rather than
failing.

² Cloud transcription (Settings → AI) is opt-in and off by default. It
sends the asset's audio to a user-configured OpenAI-compatible provider —
no local ffmpeg needed, since the api accepts audio and video directly —
and records the egress as a `cloud_transcription` chain-of-custody entry
(provider, model, endpoint). On-device transcription/OCR/scene-detection
still require the local models + ffmpeg, which the desktop build does not
yet bundle (a future "AI pack").

## Why Lite assets are served over HTTP

The webview document origin is `tauri://localhost`, and `<video>/<img>/
<object>` elements can't send an `Authorization` header. So asset bytes
are served by the sidecar at an absolute `http://127.0.0.1:8000/...` URL
whose **query-string HMAC signature is the credential** (see
`LocalStorageBackend`), with the Tauri CSP widened to allow that origin
for `media-src`/`img-src`/`object-src`/`frame-src`. A non-http loopback
scheme (the previous `loom://`) cannot be loaded by those elements, which
is why preview/download/playback were broken before v0.1.15.
