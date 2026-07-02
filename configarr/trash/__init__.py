"""TRaSH-Guides import.

Resolves per-instance ``trash:`` config blocks into the instance's own custom
formats and quality definitions. Runs as a separate pass after ``parse_config`` so
parsing stays pure. See ``docs/design/trash-guides-loader.md``.
"""

from configarr.trash.errors import TrashError
from configarr.trash.resolve import resolve_trash

__all__ = ["TrashError", "resolve_trash"]
