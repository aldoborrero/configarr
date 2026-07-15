"""The single ``--service`` / ``--instance`` scope predicate.

Both the provider registry (``providers_for``) and the trash resolver
(``resolve_trash``) filter instances by the same CLI flags. Keeping the rule here —
rather than reimplementing it in each — stops the two from silently drifting apart
(e.g. one gaining case-insensitive instance matching while the other doesn't, which
would let a trash guide be read for an instance the sync then skips).
"""

from __future__ import annotations


def in_scope(
    service_name: str,
    instance_name: str,
    service: str | None,
    instance: str | None,
) -> bool:
    """Whether an instance is selected by the optional filters. Service matches
    case-insensitively; instance matches exactly. Absent filters match everything."""
    if service and service_name != service.lower():
        return False
    return not (instance and instance_name != instance)
