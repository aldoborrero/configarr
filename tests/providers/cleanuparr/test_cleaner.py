import json

import pytest
import responses

from configarr.plan import Op
from configarr.providers.cleanuparr.cleaner import (
    CleanuparrClientSettingsProvider,
    CleanuparrSeedingRuleProvider,
)

CU = "http://cleanuparr.test"
DC = f"{CU}/api/configuration/download_cleaner"
CLIENTS = f"{CU}/api/configuration/download_client"

RULE = {
    "id": "rule-1",
    "name": "cleanup-imported-public",
    "categories": ["sonarr", "radarr"],
    "trackerPatterns": [],
    "tagsAny": [],
    "tagsAll": [],
    "priority": 1,
    "privacyType": "Both",
    "maxRatio": 1,
    "minSeedTime": 0,
    "maxSeedTime": 48,
    "minSeeders": 0,
    "maxInactiveDays": None,
    "deleteSourceFiles": True,
    "action": "Delete",
}


def _cleaner(clients):
    responses.get(DC, json={"clients": clients})


def _client(name, ctype, **cfg):
    return {
        "downloadClientId": f"id-{name}",
        "downloadClientName": name,
        "downloadClientTypeName": ctype,
        "seedingRules": cfg.get("rules", []),
        "unlinkedConfig": None,
        "deadTorrentConfig": None,
        "orphanedFilesConfig": cfg.get("orphaned"),
    }


def _settings(clients):
    return CleanuparrClientSettingsProvider(
        CU, "k", clients, "cleanuparr.client_settings"
    )


def _rules(clients):
    return CleanuparrSeedingRuleProvider(CU, "k", clients, "cleanuparr.seeding_rule")


# -- per-client settings ------------------------------------------------------


@responses.activate
def test_unset_orphaned_files_is_created_with_put(plan_provider, apply_changes):
    _cleaner([_client("SABnzbd", "Sabnzbd")])
    responses.get(CLIENTS, json={"clients": [{"id": "id-SABnzbd", "name": "SABnzbd"}]})
    responses.put(f"{CU}/api/orphaned-files-config/id-SABnzbd", json={})
    provider = _settings(
        {
            "SABnzbd": {
                "type": "sabnzbd",
                "orphaned_files": {
                    "enabled": True,
                    "scan_directories": ["/media/downloads/complete"],
                    "min_file_age_hours": 48,
                },
            }
        }
    )
    plan = plan_provider(provider)
    assert [(r.op, r.key) for r in plan.resources] == [
        (Op.CREATE, ("SABnzbd", "orphaned_files"))
    ]
    apply_changes(provider, plan)
    put = next(c for c in responses.calls if c.request.method == "PUT")
    assert json.loads(put.request.body) == {
        "enabled": True,
        "scanDirectories": ["/media/downloads/complete"],
        "minFileAgeHours": 48,
    }


@responses.activate
def test_existing_orphaned_files_merge_and_noop(plan_provider):
    current = {
        "id": "o1",
        "enabled": True,
        "scanDirectories": ["/media/downloads/complete"],
        "orphanedDirectory": "/media/downloads/orphaned",
        "excludePatterns": [],
        "minFileAgeHours": 48,
        "purgeAfterHours": 168,
    }
    _cleaner([_client("SABnzbd", "Sabnzbd", orphaned=current)])
    plan = plan_provider(
        _settings({"SABnzbd": {"orphaned_files": {"min_file_age_hours": 48}}})
    )
    assert not plan.has_changes


def test_unsupported_setting_for_client_type_is_rejected():
    provider = _settings(
        {"SABnzbd": {"type": "sabnzbd", "unlinked": {"enabled": True}}}
    )
    with pytest.raises(ValueError, match="does not support 'unlinked'"):
        provider.build_desired()


# -- seeding rules ------------------------------------------------------------


@responses.activate
def test_matching_seeding_rule_is_noop(plan_provider):
    _cleaner([_client("Transmission", "Transmission", rules=[RULE])])
    plan = plan_provider(
        _rules(
            {
                "Transmission": {
                    "seeding_rules": {
                        "cleanup-imported-public": {
                            "categories": ["sonarr", "radarr"],
                            "privacy_type": "both",
                            "max_ratio": 1,
                            "max_seed_time": 48,
                            "max_inactive_days": -1,
                        }
                    }
                }
            }
        )
    )
    assert not plan.has_changes


@responses.activate
def test_seeding_rule_crud(plan_provider, apply_changes):
    old = {**RULE, "id": "rule-old", "name": "old", "priority": 2}
    _cleaner([_client("Transmission", "Transmission", rules=[RULE, old])])
    responses.get(
        CLIENTS, json={"clients": [{"id": "id-Transmission", "name": "Transmission"}]}
    )
    responses.put(f"{CU}/api/seeding-rules/rule-1", json={})
    responses.post(f"{CU}/api/seeding-rules/id-Transmission", json={}, status=201)
    responses.delete(f"{CU}/api/seeding-rules/rule-old", status=204)
    provider = _rules(
        {
            "Transmission": {
                "type": "transmission",
                "seeding_rules": {
                    "cleanup-imported-public": {"max_ratio": 2},
                    "new": {"categories": ["prowlarr"], "priority": 3},
                },
            }
        }
    )
    plan = plan_provider(provider, prune=True)
    ops = {r.key: r.op for r in plan.resources if r.changed}
    assert ops == {
        ("Transmission", "cleanup-imported-public"): Op.UPDATE,
        ("Transmission", "new"): Op.CREATE,
        ("Transmission", "old"): Op.DELETE,
    }
    apply_changes(provider, plan)
    put = next(c for c in responses.calls if c.request.method == "PUT")
    body = json.loads(put.request.body)
    assert body["maxRatio"] == 2 and "id" not in body and body["name"] == RULE["name"]
    post = next(c for c in responses.calls if c.request.method == "POST")
    assert json.loads(post.request.body) == {
        "categories": ["prowlarr"],
        "priority": 3,
        "name": "new",
    }


@responses.activate
def test_client_without_seeding_rules_key_is_left_alone(plan_provider):
    plan = plan_provider(_rules({"Transmission": {"type": "transmission"}}), prune=True)
    assert plan.resources == []
    assert len(responses.calls) == 0


def test_seeding_rules_rejected_on_usenet_client():
    provider = _rules({"SABnzbd": {"type": "sabnzbd", "seeding_rules": {"r": {}}}})
    with pytest.raises(ValueError, match="does not support 'seeding_rules'"):
        provider.build_desired()
