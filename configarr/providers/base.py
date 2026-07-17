"""Provider interface: each service/resource implements this."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import requests

from configarr.model import Op, ResourcePlan
from configarr.normalize import (
    coerce_scalar,
    drop_secret_fields,
    secret_field_names,
)
from configarr.transport import build_session


@dataclass
class Action:
    """A write the engine emits: an op plus the full object to POST/PUT/DELETE."""

    op: Op
    key: Hashable
    payload: dict[str, Any]  # full object to POST/PUT


@runtime_checkable
class ResourceProvider(Protocol):
    """Structural interface every provider satisfies: resource identity
    (``match_key``), current/desired state, ``normalize`` for comparison, and the
    ``to_action``/``apply`` write path."""

    kind: str
    # Providers that expose a per-resource DELETE endpoint set this True so the
    # engine may prune unmanaged resources under --prune. Singletons and
    # set-only/config providers (naming, sabnzbd.*, bazarr settings sections)
    # leave it False, since deletion is meaningless or unsafe for them.
    prunable: bool = False

    def match_key(self, resource: dict[str, Any]) -> Hashable: ...
    def fetch_current(self) -> list[dict[str, Any]]: ...
    def build_desired(self) -> list[dict[str, Any]]: ...
    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]: ...
    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action: ...
    # Returns the resource's service id when a create/update knows it (the CF
    # provider does, to record ownership for rename-tolerant matching); None
    # otherwise.
    def apply(self, action: Action) -> int | None: ...


class CurrentStateCache:
    """Mixin memoizing the current-state fetch per provider instance.

    A plan reads current state twice — the runner diffs against it, and most
    providers also read it inside ``build_desired()`` to merge over current.
    Without memoization that is two GETs per plan (up to four through the
    apply-then-replan harness), and the two reads can observe different server
    state (TOCTOU). Providers implement ``_load_current()`` for the raw HTTP
    read; ``fetch_current()`` caches it. ``apply()`` MUST call
    ``invalidate_current()`` after a successful write so a re-plan observes
    post-write state.
    """

    _current_cache: list[dict[str, Any]] | None = None
    # Additive by default; providers that expose a DELETE endpoint set this True
    # to participate in --prune (see ResourceProvider.prunable).
    prunable: bool = False

    def fetch_current(self) -> list[dict[str, Any]]:
        if self._current_cache is None:
            self._current_cache = self._load_current()
        return self._current_cache

    def invalidate_current(self) -> None:
        self._current_cache = None

    def _load_current(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class HttpProvider(CurrentStateCache):
    """Base for the *arr providers: an ``X-Api-Key`` session plus HTTP helpers.

    Holds the shared transport boilerplate every Radarr/Sonarr/Prowlarr provider
    repeated: a ``requests.Session`` carrying the API key, ``_url()`` for joining
    paths to ``base_url``, and ``_get/_post/_put/_delete`` wrappers that call
    ``raise_for_status()`` so each call site does not. Subclasses set their own
    ``kind``/``config`` after calling ``super().__init__()``.
    """

    # Set by every subclass; declared here so shared helpers (e.g. tag resolution)
    # can reference it.
    kind: str
    # Tag endpoint for label->id resolution; Prowlarr providers override to v1.
    _tag_path = "/api/v3/tag"

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._session = build_session()
        self._session.headers["X-Api-Key"] = api_key
        self._tag_cache: dict[str, int] | None = None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _tag_map(self) -> dict[str, int]:
        """The instance's ``label -> id`` tag map (fetched once, cached)."""
        if self._tag_cache is None:
            self._tag_cache = {
                t["label"]: t["id"] for t in self._get(self._tag_path).json()
            }
        return self._tag_cache

    def _resolve_tags(self, tags: Any) -> list[int]:
        """Resolve a config ``tags`` list to numeric ids. Integers pass through;
        string labels are looked up in the instance's existing tags. An unknown
        label is a clear error (configarr does not create tags — yet)."""
        out: list[int] = []
        for tag in tags or []:
            if isinstance(tag, bool):  # bool is an int subclass; reject it explicitly
                raise ValueError(f"invalid tag {tag!r}: expected a label or id")
            if isinstance(tag, int):
                out.append(tag)
            elif isinstance(tag, str):
                tag_map = self._tag_map()
                if tag not in tag_map:
                    service = self.kind.split(".")[0]
                    raise ValueError(
                        f"unknown tag label {tag!r} on {service}: create it there "
                        "first, or use its numeric id"
                    )
                out.append(tag_map[tag])
            else:
                raise ValueError(f"invalid tag {tag!r}: expected a label (str) or id")
        return out

    def _get(self, path: str) -> requests.Response:
        resp = self._session.get(self._url(path))
        resp.raise_for_status()
        return resp

    def _post(self, path: str, json: Any) -> requests.Response:
        resp = self._session.post(self._url(path), json=json)
        resp.raise_for_status()
        return resp

    def _put(self, path: str, json: Any) -> requests.Response:
        resp = self._session.put(self._url(path), json=json)
        resp.raise_for_status()
        return resp

    def _delete(self, path: str) -> requests.Response:
        resp = self._session.delete(self._url(path))
        resp.raise_for_status()
        return resp


class FieldProvider(HttpProvider):
    """Base for the provider-Field *arr resources (rollout work-list #7-#11):
    download clients, notifications, indexers, and applications.

    These resources carry a schema-driven ``fields`` list and share the same
    machinery, which lives here so each provider is a thin specialization:

    - masked-secret tracking — schema ``privacy`` marks apiKey/password/token-style
      fields whose values the server echoes masked, so they are dropped from both
      sides of the diff by name (``_overlay_fields`` records them, and
      ``_normalized_fields`` drops them; ``_secret_names_ready`` keeps that
      self-enforcing regardless of call order — see finding I2);
    - ``coerce_scalar`` + secret-drop field normalization;
    - the ``to_action`` boilerplate (CREATE strips ``id``, UPDATE carries the matched
      ``current`` id, DELETE carries just the id; full-replace). DELETE is only
      reachable when a subclass opts into ``prunable``; the base handles it so the
      flag and its write path stay coupled;
    - ``forceSave=true`` writes that skip the *arr live-connectivity test.

    Subclasses supply the resource-specific schema fetch+cache, the override map in
    ``build_desired()``, ``normalize()`` field selection, and the endpoint path passed
    to ``_apply_force_save``.
    """

    full_replace = True

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        super().__init__(base_url, api_key)
        self.kind = kind
        self.config = config or {}
        self._secret_names: set[str] = set()
        self._secret_names_ready = False

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return resource.get("name")

    def _overlay_fields(
        self, base_fields: list[dict[str, Any]], settings: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Overlay configured settings onto a field list, keeping each field's
        existing value (current on update, schema default on create) when unset."""
        self._secret_names |= secret_field_names(base_fields)
        out: list[dict[str, Any]] = []
        for f in base_fields:
            name = f["name"]
            value = settings.get(name, f.get("value"))
            out.append({"name": name, "value": value})
        return out

    def _normalized_fields(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Coerce the resource's ``fields`` to a name->value dict and drop secrets.

        Triggers ``build_desired()`` first when the secret-name set has not been
        populated yet, so ``normalize()`` is correct even if called before
        ``build_desired()`` (finding I2). No extra HTTP: schema/current are cached.
        """
        if not self._secret_names_ready:
            self.build_desired()
        fields = {
            f["name"]: coerce_scalar(f.get("value")) for f in resource.get("fields", [])
        }
        return drop_secret_fields(fields, self._secret_names)

    def build_desired(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op in (Op.CREATE, Op.UPDATE, Op.DELETE), (
            f"to_action: unexpected op {plan.op!r}"
        )
        if plan.op is Op.CREATE:
            payload = {k: v for k, v in (desired or {}).items() if k != "id"}
            return Action(op=plan.op, key=plan.key, payload=payload)
        if plan.op is Op.DELETE:
            # Prune only carries the current object; we just need its id to delete.
            assert current is not None, (
                f"to_action: DELETE for {plan.key!r} requires the current resource"
            )
            return Action(op=plan.op, key=plan.key, payload={"id": current["id"]})
        payload = {**(desired or {}), "id": (current or {})["id"]}
        return Action(op=plan.op, key=plan.key, payload=payload)

    def _apply_force_save(self, endpoint: str, action: Action) -> None:
        """POST (create) / PUT (update) / DELETE the payload with ``forceSave=true``
        and invalidate the current-state cache. ``endpoint`` is the collection path,
        e.g. ``/api/v3/downloadclient``. DELETE is reached only under ``--prune`` for
        a ``prunable`` subclass."""
        if action.op is Op.CREATE:
            self._post(f"{endpoint}?forceSave=true", json=action.payload)
        elif action.op is Op.UPDATE:
            rid = action.payload["id"]
            self._put(f"{endpoint}/{rid}?forceSave=true", json=action.payload)
        elif action.op is Op.DELETE:
            self._delete(f"{endpoint}/{action.payload['id']}")
        else:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        self.invalidate_current()
