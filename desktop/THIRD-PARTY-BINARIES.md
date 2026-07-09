# Third-party binaries bundled with Loom Desktop

The desktop installers for Linux and Windows bundle prebuilt host
binaries so media processing and OCR work out of the box. Every
binary is pinned by URL and SHA-256 in
[`binaries.lock.json`](binaries.lock.json) and verified at build time
by `scripts/fetch-desktop-binaries.py`; a checksum mismatch fails the
build.

| Binary | Version | License | Source |
| --- | --- | --- | --- |
| ffmpeg / ffprobe (linux, windows) | n7.1.5 | GPL-3.0 | [BtbN/FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds) — the pinned autobuild release includes the corresponding source tarball |
| tesseract (linux) | 5.5.2 | Apache-2.0 | [AlexanderP/tesseract-appimage](https://github.com/AlexanderP/tesseract-appimage) |
| eng.traineddata | tessdata_fast 4.1.0 | Apache-2.0 | [tesseract-ocr/tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast) |

GPL compliance: ffmpeg is distributed under GPL-3.0; the pinned
BtbN release page linked above publishes the exact corresponding
sources alongside the binaries. Loom itself does not link against
ffmpeg — it is invoked as a separate process.

Not bundled (probed from the host with a fail-loud remedy instead):

- **macOS**: `ffmpeg` and `tesseract` via Homebrew — no vetted
  relocatable arm64 static builds yet.
- **Windows tesseract**: only installer-style distributions exist;
  the OCR remedy points at the standard installer.
