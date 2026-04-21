# Icons

Tauri reads the icon paths declared in `tauri.conf.json` at bundle
time. Real assets must be dropped into this directory before any
release build. The placeholder state will fail `tauri build` if the
files below are missing.

## Expected filenames

| File | Purpose | Size |
| --- | --- | --- |
| `32x32.png` | Linux / generic small raster | 32x32 px |
| `128x128.png` | Linux / generic large raster | 128x128 px |
| `128x128@2x.png` | HiDPI raster | 256x256 px |
| `icon.icns` | macOS bundle icon | multi-resolution |
| `icon.ico` | Windows bundle icon | multi-resolution |

## Source of truth

The canonical SVG lives in `docs/brand/loom-mark.svg` (TBD). Generate
the raster variants with `tauri icon path/to/source.png` once a real
mark is approved by the NLG brand reviewers.
