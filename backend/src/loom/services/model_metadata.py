"""ai model provenance helpers.

every ai-produced row (transcript segment, ocr region, scene)
carries model_name, model_version, model_params so the ui can
answer "why did the model say this?" without re-running it.

the helpers here are pure (no i/o, no mutation) so services
can attach provenance to their result dicts in one line.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

# sentinel used when the model library is not installed or the
# version cannot be resolved. the alembic migration backfills
# pre-existing rows with the same value, so consumers can treat
# "unknown" as the single "provenance not recorded" marker.
UNKNOWN_VERSION: str = "unknown"


def package_version(package: str) -> str:
    """return installed version for a package, or 'unknown'.

    importlib.metadata raises PackageNotFoundError when the
    optional ai extras aren't installed; we return 'unknown' so
    services can degrade gracefully instead of crashing.
    """
    try:
        return version(package)
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def build_provenance(
    model_name: str,
    package: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """return the three-field provenance dict in canonical shape.

    services spread this into their result rows:
        {**row, **build_provenance("faster-whisper", "faster-whisper", {...})}
    """
    return {
        "model_name": model_name,
        "model_version": package_version(package),
        "model_params": params,
    }
