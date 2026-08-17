from configarr.engine import reconcile_renames


def _names(resources):
    return {r["name"]: r["id"] for r in resources}


def test_no_managed_ids_is_noop():
    current = [{"id": 1, "name": "A"}]
    out, renamed = reconcile_renames(current, [{"name": "A"}], {})
    assert out is current
    assert renamed == set()


def test_relabels_server_renamed_managed_resource():
    # configarr created "A" (id 42); a user renamed it to "A2" on the server; config
    # still says "A". Reconcile relabels id 42 back to "A" and reports the rename.
    current = [{"id": 42, "name": "A2", "extra": 1}]
    out, renamed = reconcile_renames(current, [{"name": "A"}], {"A": 42})
    assert _names(out) == {"A": 42}
    assert out[0]["extra"] == 1  # other fields preserved
    assert current[0]["name"] == "A2"  # original not mutated
    assert renamed == {"A"}


def test_no_remap_when_stored_id_absent_on_server():
    current = [{"id": 7, "name": "other"}]
    out, renamed = reconcile_renames(current, [{"name": "A"}], {"A": 42})
    assert out is current
    assert renamed == set()


def test_name_present_by_name_is_noop():
    current = [{"id": 42, "name": "A"}]
    out, renamed = reconcile_renames(current, [{"name": "A"}], {"A": 42})
    assert out is current
    assert renamed == set()


def test_does_not_steal_a_resource_matching_another_desired_name():
    # id 42 is currently named "B", and "B" is also desired — it must not be
    # relabeled to "A" just because state maps "A" -> 42.
    current = [{"id": 42, "name": "B"}]
    out, renamed = reconcile_renames(current, [{"name": "A"}, {"name": "B"}], {"A": 42})
    assert out is current
    assert renamed == set()


def _lower_key(r):
    name = r.get("name")
    return name.lower() if isinstance(name, str) else name


def test_case_insensitive_key_reconciles_via_match_key():
    # Regression: a provider whose match_key lower-cases the name (Prowlarr download
    # clients) records managed_ids under the lower-cased key. Looking the id up by the
    # raw config name missed, so a server rename produced a duplicate. With key=
    # match_key the lookup hits and the resource is relabeled; renamed carries the
    # *match key* so diff(force_update=...) recognizes it.
    current = [{"id": 42, "name": "qBit-renamed"}]
    out, renamed = reconcile_renames(
        current,
        [{"name": "qBittorrent"}],
        {"qbittorrent": 42},
        key=_lower_key,
    )
    assert _names(out) == {"qBittorrent": 42}
    assert renamed == {"qbittorrent"}


def test_case_insensitive_key_treats_case_only_rename_as_present():
    # config "qBittorrent" vs server "qbittorrent" (case-only) is the same resource
    # under a case-insensitive match_key — no rename, no phantom update.
    current = [{"id": 42, "name": "qbittorrent"}]
    out, renamed = reconcile_renames(
        current, [{"name": "qBittorrent"}], {"qbittorrent": 42}, key=_lower_key
    )
    assert out is current
    assert renamed == set()
