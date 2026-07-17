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
