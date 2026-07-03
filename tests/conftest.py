"""Shared provider-test harness.

Every provider test exercises the same engine seam: plan a provider, optionally
apply the changes, then re-plan and assert empty. Centralizing these helpers here
keeps the per-provider tests focused on the provider's own current/desired/HTTP
shapes and stops the plan/apply glue from drifting from the runner as providers
multiply (rollout doc Phase A4).
"""

from __future__ import annotations

import pytest

from configarr.engine import diff


def _plan_provider(provider, prune=False):
    """Plan a provider exactly as runner.run_plan does, including the opt-in
    full_replace flag, so tests and production never diverge on diff semantics.
    ``prune`` mirrors the runner's opt-in deletion of unmanaged resources."""
    return diff(
        provider.kind,
        provider.fetch_current(),
        provider.build_desired(),
        match_key=provider.match_key,
        normalize=provider.normalize,
        full_replace=getattr(provider, "full_replace", False),
        prune=prune and getattr(provider, "prunable", False),
    )


def _apply_changes(provider, plan):
    """Drive provider.to_action/apply for every changed resource in a plan,
    threading the matched current (for update ids) and desired full objects."""
    current_by_key = {provider.match_key(c): c for c in provider.fetch_current()}
    desired_by_key = {provider.match_key(d): d for d in provider.build_desired()}
    for resource in plan.resources:
        if resource.changed:
            action = provider.to_action(
                resource,
                current_by_key.get(resource.key),
                desired_by_key.get(resource.key),
            )
            provider.apply(action)


@pytest.fixture
def plan_provider():
    """Return the runner-equivalent plan helper as a callable."""
    return _plan_provider


@pytest.fixture
def apply_changes():
    """Return the apply-the-plan helper as a callable."""
    return _apply_changes
