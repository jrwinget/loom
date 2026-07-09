"""the openapi export must be valid json and deterministic —
`git diff --exit-code` in CI depends on byte-stable output."""

import json

from loom.scripts.export_openapi import render_schema


def test_export_is_valid_json_and_stable() -> None:
    first = render_schema()
    schema = json.loads(first)
    assert schema["info"]["title"] == "Loom"
    assert "/api/v1/capabilities" in schema["paths"]

    second = render_schema()
    assert first == second
