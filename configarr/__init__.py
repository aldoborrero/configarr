"""Configarr - Configuration manager for *arr applications."""

from importlib.metadata import PackageNotFoundError, version

try:
    # The version lives only in pyproject.toml; read it from the installed
    # distribution metadata so it is never duplicated in source.
    __version__ = version("configarr")
except PackageNotFoundError:  # running from a source tree with no installed dist
    __version__ = "0.0.0+source"
