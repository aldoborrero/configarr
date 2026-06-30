from configarr.build import merge_full_replace


def test_overlays_desired_over_current_over_defaults():
    defaults = {"a": 0, "b": 0, "c": 0}
    current = {"a": 1, "b": 1, "server_managed": 9}
    desired = {"b": 2}
    merged = merge_full_replace(defaults, current, desired)
    # desired > current > defaults, and the server-managed current key survives so a
    # full-replace PUT won't reset it.
    assert merged == {"a": 1, "b": 2, "c": 0, "server_managed": 9}


def test_current_optional_falls_back_to_defaults():
    # On CREATE there is no current object, so desired overlays defaults only.
    merged = merge_full_replace({"a": 0, "b": 0}, None, {"a": 5})
    assert merged == {"a": 5, "b": 0}


def test_does_not_mutate_inputs():
    defaults = {"a": 0}
    current = {"a": 1}
    desired = {"a": 2}
    merge_full_replace(defaults, current, desired)
    assert defaults == {"a": 0}
    assert current == {"a": 1}
    assert desired == {"a": 2}
