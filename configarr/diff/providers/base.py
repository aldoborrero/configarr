"""Provider interface: each service/resource implements this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Hashable, Protocol, runtime_checkable

from configarr.diff.model import Op, ResourcePlan


@dataclass
class Action:
    op: Op
    key: Hashable
    payload: dict[str, Any]  # full object to POST/PUT


@runtime_checkable
class ResourceProvider(Protocol):
    kind: str

    def match_key(self, resource: dict[str, Any]) -> Hashable: ...
    def fetch_current(self) -> list[dict[str, Any]]: ...
    def build_desired(self) -> list[dict[str, Any]]: ...
    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]: ...
    def to_action(
        self, plan: ResourcePlan, current: dict | None, desired: dict | None
    ) -> Action: ...
    def apply(self, action: Action) -> None: ...
