from unittest.mock import patch

import pytest

from loom.services.model_metadata import (
    UNKNOWN_VERSION,
    build_provenance,
    package_version,
)


class TestPackageVersion:
    def test_returns_version_when_installed(self) -> None:
        with patch(
            "loom.services.model_metadata.version",
            return_value="1.2.3",
        ):
            assert package_version("anything") == "1.2.3"

    def test_returns_unknown_when_missing(self) -> None:
        from importlib.metadata import PackageNotFoundError

        with patch(
            "loom.services.model_metadata.version",
            side_effect=PackageNotFoundError("not installed"),
        ):
            assert package_version("missing-pkg") == UNKNOWN_VERSION


class TestBuildProvenance:
    def test_returns_canonical_shape(self) -> None:
        with patch(
            "loom.services.model_metadata.version",
            return_value="9.9.9",
        ):
            provenance = build_provenance(
                "my-model",
                "my-package",
                {"foo": "bar"},
            )
        assert provenance == {
            "model_name": "my-model",
            "model_version": "9.9.9",
            "model_params": {"foo": "bar"},
        }

    def test_params_default_to_none(self) -> None:
        with patch(
            "loom.services.model_metadata.version",
            return_value="1.0",
        ):
            provenance = build_provenance("m", "p")
        assert provenance["model_params"] is None

    @pytest.mark.parametrize("params", [None, {}, {"k": 1}])
    def test_preserves_params_shape(
        self, params: dict[str, object] | None
    ) -> None:
        with patch(
            "loom.services.model_metadata.version",
            return_value="1.0",
        ):
            provenance = build_provenance("m", "p", params)
        assert provenance["model_params"] == params
