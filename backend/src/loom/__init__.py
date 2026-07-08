"""Loom: evidence operating system for civil-rights legal teams."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("loom")
except PackageNotFoundError:
    # source tree without an installed dist (e.g. bare checkout)
    __version__ = "0.0.0+dev"
