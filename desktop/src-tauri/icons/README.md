# Icons

Tauri reads the icon paths declared in `tauri.conf.json` at bundle
time. The five files in this directory ship as **placeholders** —
a procedural geometric "L" mark on a flat background — so
`tauri build` succeeds in CI. They MUST be replaced with real
brand assets before a public beta.

## Expected filenames

| File | Purpose | Size |
| --- | --- | --- |
| `32x32.png` | Linux / generic small raster | 32x32 px |
| `128x128.png` | Linux / generic large raster | 128x128 px |
| `128x128@2x.png` | HiDPI raster | 256x256 px |
| `icon.icns` | macOS bundle icon | multi-resolution |
| `icon.ico` | Windows bundle icon | multi-resolution |

## Regenerating the placeholder

The current placeholders are produced by `generate.py` in this
directory. From the repo root:

```bash
uv run --project backend python desktop/src-tauri/icons/generate.py
```

Requires Pillow, available via the backend's `ai` extra
(`uv sync --extra ai`).

## Replacing with real artwork

The canonical SVG should live at `docs/brand/loom-mark.svg`
(currently TBD). Once a real mark is approved by brand reviewers,
generate the raster variants with `cargo tauri icon path/to/source.png`
and commit the resulting files in place — the filenames in the
table above are what `tauri.conf.json` references and should not
change.
