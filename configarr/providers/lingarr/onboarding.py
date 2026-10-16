"""Lingarr onboarding provider. Client-free: talks HTTP via requests.

A fresh Lingarr answers every settings call with ``403 Onboarding required`` until
``POST /api/auth/onboarding`` has run once (it records ``auth_enabled`` and flips
``onboarding_completed``). That makes a brand-new instance unmanageable by the
settings providers, so this provider completes it declaratively:

    lingarr:
      instances:
        tv:
          onboarding:
            enable_user_auth: false   # what Lingarr's first-run wizard asks

It is a singleton reported as an UPDATE (``onboarded: False -> True``) by a plan
and only POSTed on apply, so a plan stays read-only. Once onboarded it is a no-op:
Lingarr refuses a second onboarding (409), and the auth mode is then changed in
Lingarr itself. The state is read from the anonymous ``GET /api/auth/authenticated``.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from configarr.plan import Op, ResourcePlan
from configarr.providers.base import Action, CurrentStateCache
from configarr.providers.lingarr.settings import lingarr_session

_SINGLETON = "onboarding"


class LingarrOnboardingProvider(CurrentStateCache):
    """Completes Lingarr's first-run onboarding when ``onboarding:`` is set."""

    def __init__(self, base_url: str, api_key: str, config: Any, kind: str) -> None:
        self.kind = kind
        self.base_url = base_url.rstrip("/")
        self.config: dict[str, Any] | None = config
        self._session = lingarr_session(api_key)

    def match_key(self, resource: dict[str, Any]) -> Hashable:
        return _SINGLETON

    def _load_current(self) -> list[dict[str, Any]]:
        if self.config is None:
            return []
        resp = self._session.get(f"{self.base_url}/api/auth/authenticated")
        resp.raise_for_status()
        requires = bool((resp.json() or {}).get("requiresOnboarding"))
        return [{"onboarded": not requires}]

    def build_desired(self) -> list[dict[str, Any]]:
        if self.config is None:
            return []
        return [{"onboarded": True}]

    def normalize(self, resource: dict[str, Any]) -> dict[str, Any]:
        return {"onboarded": bool(resource.get("onboarded"))}

    def to_action(
        self,
        plan: ResourcePlan,
        current: dict[str, Any] | None,
        desired: dict[str, Any] | None,
    ) -> Action:
        assert plan.op is Op.UPDATE, f"to_action: unexpected op {plan.op!r}"
        return Action(op=plan.op, key=plan.key, payload={"onboarded": True})

    def apply(self, action: Action) -> None:
        if action.op is not Op.UPDATE:
            raise NotImplementedError(f"apply: unsupported op {action.op!r}")
        enable_auth = bool((self.config or {}).get("enable_user_auth", False))
        resp = self._session.post(
            f"{self.base_url}/api/auth/onboarding",
            json={"enableUserAuth": "true" if enable_auth else "false"},
        )
        # 409 = already onboarded (a race with the UI): the goal state holds.
        if resp.status_code != 409:
            resp.raise_for_status()
        self.invalidate_current()
