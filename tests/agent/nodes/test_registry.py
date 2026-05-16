"""Unit tests for NodeRegistry operations.

Registry stores (NodeConfig, NodeInfoCache) 2-tuples only.
NodeRuntimeState is a computed DTO and is never stored in NodeRegistry.
"""

import threading

import pytest

from agent.nodes.models import NodeConfig, NodeInfoCache, NodeRuntimeState
from agent.nodes.registry import NodeRegistry
from tests.agent.nodes.conftest import make_node_config


# ---------------------------------------------------------------------------
# Registry unit tests
# ---------------------------------------------------------------------------


def test_empty_registry_all_returns_empty():
    registry = NodeRegistry()
    assert registry.all() == []


def test_add_and_get_returns_two_tuple():
    registry = NodeRegistry()
    cfg = make_node_config("node-a")
    registry.add(cfg)

    result = registry.get("node-a")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_add_and_get_config_fields():
    registry = NodeRegistry()
    cfg = make_node_config("node-b", mode="tunnel", enabled=False)
    registry.add(cfg)

    result_cfg, result_cache = registry.get("node-b")
    assert result_cfg.name == "node-b"
    assert result_cfg.mode == "tunnel"
    assert result_cfg.enabled is False
    assert result_cfg.host == "192.168.1.1"
    assert result_cfg.port == 22
    assert result_cfg.user == "pi"
    assert result_cfg.id_file is None


def test_add_sets_empty_info_cache():
    registry = NodeRegistry()
    registry.add(make_node_config("node-c"))

    _, cache = registry.get("node-c")
    assert isinstance(cache, NodeInfoCache)
    assert cache.facts == {}
    assert cache.collected_at is None


def test_add_duplicate_name_raises_value_error():
    registry = NodeRegistry()
    registry.add(make_node_config("node-dup"))
    with pytest.raises(ValueError):
        registry.add(make_node_config("node-dup"))


def test_remove_node_removes_it():
    registry = NodeRegistry()
    registry.add(make_node_config("node-rm"))
    registry.remove("node-rm")

    assert not registry.exists("node-rm")
    with pytest.raises(KeyError):
        registry.get("node-rm")


def test_remove_unknown_raises_key_error():
    registry = NodeRegistry()
    with pytest.raises(KeyError):
        registry.remove("no-such-node")


def test_exists_returns_true_for_known():
    registry = NodeRegistry()
    registry.add(make_node_config("node-present"))
    assert registry.exists("node-present") is True


def test_exists_returns_false_for_unknown():
    registry = NodeRegistry()
    assert registry.exists("node-absent") is False


def test_update_config_replaces_config():
    registry = NodeRegistry()
    registry.add(make_node_config("node-upd"))
    new_cfg = NodeConfig(
        name="node-upd",
        mode="tunnel",
        enabled=False,
        host=None,
        port=2222,
        user="admin",
        id_file=None,
    )
    registry.update_config("node-upd", new_cfg)

    result_cfg, _ = registry.get("node-upd")
    assert result_cfg.mode == "tunnel"
    assert result_cfg.enabled is False
    assert result_cfg.port == 2222
    assert result_cfg.user == "admin"


def test_update_config_unknown_raises_key_error():
    registry = NodeRegistry()
    with pytest.raises(KeyError):
        registry.update_config("ghost", make_node_config("ghost"))


def test_update_cache_replaces_cache():
    registry = NodeRegistry()
    registry.add(make_node_config("node-cache"))
    new_cache = NodeInfoCache(
        facts={"hostname": {"value": "rpi-01", "source": "cache", "collected_at": None}},
        collected_at="2026-05-15T12:00:00Z",
    )
    registry.update_cache("node-cache", new_cache)

    _, result_cache = registry.get("node-cache")
    assert result_cache.facts["hostname"]["value"] == "rpi-01"
    assert result_cache.collected_at == "2026-05-15T12:00:00Z"


def test_update_cache_unknown_raises_key_error():
    registry = NodeRegistry()
    with pytest.raises(KeyError):
        registry.update_cache("ghost", NodeInfoCache())


def test_all_returns_all_added_nodes():
    registry = NodeRegistry()
    names = ["alpha", "beta", "gamma"]
    for name in names:
        registry.add(make_node_config(name))

    entries = registry.all()
    assert len(entries) == 3
    returned_names = {cfg.name for cfg, _ in entries}
    assert returned_names == set(names)


def test_node_runtime_state_is_not_stored():
    """get() returns a 2-tuple (NodeConfig, NodeInfoCache); NodeRuntimeState is not in the tuple."""
    registry = NodeRegistry()
    registry.add(make_node_config("node-rt-check"))

    result = registry.get("node-rt-check")
    assert len(result) == 2

    cfg, cache = result
    assert isinstance(cfg, NodeConfig)
    assert isinstance(cache, NodeInfoCache)
    assert not isinstance(cfg, NodeRuntimeState)
    assert not isinstance(cache, NodeRuntimeState)


def test_thread_safety_concurrent_adds():
    """Concurrent adds from 50 threads must not lose entries."""
    registry = NodeRegistry()
    names = [f"node-{i}" for i in range(50)]
    errors: list[Exception] = []

    def add_node(name: str) -> None:
        try:
            registry.add(make_node_config(name))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=add_node, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Unexpected errors during concurrent adds: {errors}"
    assert len(registry.all()) == len(names)
    for name in names:
        assert registry.exists(name), f"Node {name!r} missing after concurrent add"
