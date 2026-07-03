"""Service-agnostic diff data model."""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Op(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    DELETE = "delete"


@dataclass(frozen=True)
class FieldDiff:
    path: str
    before: Any
    after: Any


@dataclass
class ResourcePlan:
    kind: str
    key: Hashable
    op: Op
    field_diffs: list[FieldDiff] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.op is not Op.UNCHANGED


@dataclass
class Plan:
    resources: list[ResourcePlan] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(r.changed for r in self.resources)

    def summary(self) -> dict[Op, int]:
        counts: dict[Op, int] = {}
        for r in self.resources:
            counts[r.op] = counts.get(r.op, 0) + 1
        return counts
