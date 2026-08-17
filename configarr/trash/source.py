"""Resolve a TRaSH-Guides checkout to its root directory.

Two sources are supported:

- ``local`` — an existing Guides checkout at ``path`` (relative paths resolve
  against the config file's directory), matching how recyclarr resolves a
  ``LocalProviderLocation``.
- ``git`` — clone/update a Guides repo into a local cache and use that. ``url``
  defaults to the official TRaSH-Guides repo; ``ref`` pins a branch/tag (default
  branch when unset). The clone is shallow and cached per (url, ref); later runs
  fetch and hard-reset to the ref. If the network is unavailable but a cache
  exists, the cached checkout is used with a warning (offline-tolerant), mirroring
  recyclarr's self-healing repo behavior.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from configarr.models import TrashConfig
from configarr.trash.errors import TrashError

log = logging.getLogger("configarr.trash")

DEFAULT_GUIDES_URL = "https://github.com/TRaSH-Guides/Guides.git"


def resolve_source(trash: TrashConfig, base_dir: Path) -> Path:
    """Return the guide root directory for a ``trash:`` block."""
    if trash.source == "local":
        return _resolve_local(trash, base_dir)
    if trash.source == "git":
        return _resolve_git(trash)
    raise TrashError(
        f"unsupported trash source {trash.source!r}; expected 'local' or 'git'"
    )


def _resolve_local(trash: TrashConfig, base_dir: Path) -> Path:
    if not trash.path:
        raise TrashError("trash source 'local' requires a 'path' to a Guides checkout")
    root = Path(trash.path).expanduser()
    if not root.is_absolute():
        root = base_dir / root
    if not root.is_dir():
        raise TrashError(f"TRaSH guide path not found: {root}")
    return root


def _cache_root() -> Path:
    """Base cache directory for git-sourced guides (honors ``XDG_CACHE_HOME``)."""
    base = os.environ.get("XDG_CACHE_HOME") or "~/.cache"
    return Path(base).expanduser() / "configarr" / "guides"


def _slug(value: str) -> str:
    """A filesystem-safe, collision-resistant directory name for a (url, ref)."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")[:40]
    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
    return f"{safe}-{digest}" if safe else digest


def _git(*args: str, cwd: Path | None = None) -> None:
    """Run a git command, raising TrashError with captured stderr on failure."""
    try:
        subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise TrashError(f"git {' '.join(args)} failed: {e.stderr.strip() or e}") from e


def _resolve_git(trash: TrashConfig) -> Path:
    if shutil.which("git") is None:
        raise TrashError(
            "trash source 'git' requires the 'git' executable on PATH "
            "(use source 'local' with a checkout if git is unavailable)"
        )
    url = trash.url or DEFAULT_GUIDES_URL
    ref = trash.ref
    dest = _cache_root() / _slug(f"{url}@{ref or 'default'}")

    if (dest / ".git").is_dir():
        _update_clone(dest, ref)
    else:
        _fresh_clone(dest, url, ref)
    return dest


_SHA_RE = re.compile(r"[0-9a-fA-F]{7,40}")


def _looks_like_sha(ref: str | None) -> bool:
    """True when ``ref`` is a hex string git would treat as a commit SHA rather than
    a branch/tag name — ``git clone --branch`` rejects those."""
    return ref is not None and _SHA_RE.fullmatch(ref) is not None


def _fresh_clone(dest: Path, url: str, ref: str | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A partial/corrupt dir (e.g. an interrupted earlier clone) would fail the
    # clone; start clean.
    if dest.exists():
        shutil.rmtree(dest)
    if _looks_like_sha(ref):
        # `git clone --branch` only accepts branch/tag names, so a commit-SHA pin
        # (documented as a valid `ref`) must be fetched explicitly. Servers that
        # advertise the commit's branch — GitHub included — allow this shallow fetch.
        _git("init", "--quiet", str(dest))
        _git("remote", "add", "origin", url, cwd=dest)
        _git("fetch", "--depth", "1", "origin", ref, cwd=dest)
        _git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=dest)
        log.info("cloning TRaSH guides %s (commit %s) -> %s", url, ref, dest)
        return
    args = ["clone", "--depth", "1"]
    if ref:
        args += ["--branch", ref]
    args += [url, str(dest)]
    log.info("cloning TRaSH guides %s (%s) -> %s", url, ref or "default branch", dest)
    _git(*args)


def _update_clone(dest: Path, ref: str | None) -> None:
    """Fetch and hard-reset the cached clone to ``ref`` (or its default branch).

    If the fetch fails (offline), keep using the existing checkout with a warning
    rather than aborting the whole run.
    """
    fetch = ["fetch", "--depth", "1", "origin", *([ref] if ref else [])]
    try:
        _git(*fetch, cwd=dest)
        _git("reset", "--hard", "FETCH_HEAD", cwd=dest)
    except TrashError as e:
        log.warning(
            "could not update cached TRaSH guides at %s (%s); using the cached copy",
            dest,
            e,
        )
