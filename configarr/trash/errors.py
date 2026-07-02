"""Error type for the TRaSH-Guides import."""

from __future__ import annotations


class TrashError(Exception):
    """A TRaSH-Guides import could not be resolved — a bad/missing source, an
    unknown ``trash_id``, or a malformed guide file."""
