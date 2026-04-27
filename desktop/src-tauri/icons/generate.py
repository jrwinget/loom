"""Generate placeholder Loom desktop icons.

Renders a simple geometric "L" mark on a solid background into
every file Tauri's bundler expects (32x32.png, 128x128.png,
128x128@2x.png, icon.icns, icon.ico). Replace with real brand
assets when they exist; this just unblocks `tauri build`.

Run from the repo root:

    uv run --project backend python desktop/src-tauri/icons/generate.py

Requires Pillow (>=10), available via the backend's ``ai`` extra
(``uv sync --extra ai``).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent

BG = (31, 36, 54)  # #1F2436 — deep blue-grey, civil-liberties calm
FG = (245, 240, 229)  # #F5F0E5 — cream

# the "L" mark fits inside a square; both arms are 28% of the
# icon side, with a 16% margin on every edge.
MARGIN_PCT = 0.16
ARM_PCT = 0.28


def _render(size: int) -> Image.Image:
    """render a single square icon at the given pixel size."""
    img = Image.new("RGBA", (size, size), BG + (255,))
    draw = ImageDraw.Draw(img)

    margin = int(size * MARGIN_PCT)
    arm = int(size * ARM_PCT)
    inner = size - 2 * margin

    # vertical stem of the L (left edge)
    draw.rectangle(
        [margin, margin, margin + arm, margin + inner],
        fill=FG + (255,),
    )
    # horizontal foot of the L (bottom edge)
    draw.rectangle(
        [margin, margin + inner - arm, margin + inner, margin + inner],
        fill=FG + (255,),
    )
    return img


def main() -> None:
    # png siblings — sizes Tauri's `icon` array references directly
    _render(32).save(HERE / "32x32.png", format="PNG")
    _render(128).save(HERE / "128x128.png", format="PNG")
    _render(256).save(HERE / "128x128@2x.png", format="PNG")

    # multi-resolution ICO for windows. pillow auto-downscales
    # from the largest source.
    _render(256).save(
        HERE / "icon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    # multi-resolution ICNS for macOS. pillow expects the largest
    # frame first and auto-builds the cascade.
    _render(1024).save(HERE / "icon.icns", format="ICNS")

    print("wrote:")
    for name in ("32x32.png", "128x128.png", "128x128@2x.png", "icon.ico", "icon.icns"):
        path = HERE / name
        print(f"  {path.relative_to(HERE.parents[3])}  ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
