"""
Unit tests for NodeRegistry (Phase 1) and NodeService read APIs (Phase 3).

Registry stores (NodeConfig, NodeInfoCache) 2-tuples only.
NodeRuntimeState is a computed DTO and is never stored in NodeRegistry.

Phase 3 adds NodeService.get_node_status() and NodeService.get_node_info() tests.
All NodeService tests use a real NodeRegistry and a mocked ConnectionPool.
No live SSH is performed in any of these tests.
"""

import threading

import pytest

from agent.nodes.models import NodeConfig, NodeInfoCache, NodeRuntimeState
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def make_node_config(name="test-node", mode="direct", enabled=True):
    return NodeConfig(
        name=name,
        mode=mode,
        enabled=enabled,
        host="192.168.1.1",
        port=22,
        user="pi",
        id_file=None,
    )


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


# ---------------------------------------------------------------------------
# Mock helpers for NodeService tests
# ---------------------------------------------------------------------------


def make_mock_connection(name, state):
    from unittest.mock import MagicMock
    conn = MagicMock()
    conn.name = name
    conn.get_state.return_value = state
    return conn


def make_mock_pool(connections=None):
    """Build a mock pool whose get_connection_state() delegates to mock connections.

    NodeService calls pool.get_connection_state(name) — never pool.connections directly.
    """
    from unittest.mock import MagicMock
    from agent.connectionpool.connection import ConnectionState

    pool = MagicMock()
    conns = connections or []

    _STATE_MAP = {
        ConnectionState.OPEN: "open",
        ConnectionState.CLOSED: "closed",
        ConnectionState.OPENING: "opening",
        ConnectionState.BROKEN: "broken",
    }

    def get_connection_state(name):
        for conn in conns:
            if conn.name == name:
                state = conn.get_state()
                return _STATE_MAP.get(state, "closed")
        return "not_in_pool"

    pool.get_connection_state.side_effect = get_connection_state
    return pool


def make_service(nodes=None, pool_connections=None):
    """Build a NodeService with pre-populated registry and mock pool.

    nodes: list of (name, mode, enabled) tuples; defaults to one direct/enabled node.
    pool_connections: list of mock connection objects; defaults to empty list.
    """
    from agent.connectionpool.connection import ConnectionState

    registry = NodeRegistry()
    if nodes is None:
        nodes = [("lab-pi-01", "direct", True)]
    for name, mode, enabled in nodes:
        cfg = NodeConfig(
            name=name,
            mode=mode,
            enabled=enabled,
            host="192.168.1.10",
            port=22,
            user="pi",
            id_file=None,
        )
        registry.add(cfg)

    pool = make_mock_pool(pool_connections if pool_connections is not None else [])
    return NodeService(registry=registry, pool=pool)


# ---------------------------------------------------------------------------
# NodeService — get_node_status() tests
# ---------------------------------------------------------------------------


def test_get_node_status_empty_registry():
    """Empty registry returns {"status": "ok", "nodes": []}."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.get_node_status()
    assert result == {"status": "ok", "nodes": []}


def test_get_node_status_includes_required_fields():
    """Each node entry must have all required fields."""
    from agent.connectionpool.connection import ConnectionState

    required = {"name", "mode", "enabled", "configured", "pool_state", "reachable",
                "last_seen_at", "last_error", "cached_info_available"}
    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    svc = make_service(pool_connections=[conn])
    result = svc.get_node_status()

    assert len(result["nodes"]) == 1
    assert required.issubset(set(result["nodes"][0].keys()))


def test_get_node_status_pool_state_open():
    """Node with matching open pool connection shows pool_state='open', reachable=True."""
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    svc = make_service(pool_connections=[conn])
    result = svc.get_node_status()

    node = result["nodes"][0]
    assert node["pool_state"] == "open"
    assert node["reachable"] is True


def test_get_node_status_pool_state_not_in_pool():
    """Node with no matching pool connection shows pool_state='not_in_pool', reachable=False."""
    svc = make_service(pool_connections=[])
    result = svc.get_node_status()

    node = result["nodes"][0]
    assert node["pool_state"] == "not_in_pool"
    assert node["reachable"] is False


def test_get_node_status_pool_state_derived_at_call_time():
    """Pool state is read from mock connection at call time, not from any registry value."""
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.CLOSED)
    svc = make_service(pool_connections=[conn])

    # First call — closed
    result1 = svc.get_node_status()
    assert result1["nodes"][0]["pool_state"] == "closed"

    # Mutate mock state to OPEN — next call must reflect the new value
    conn.get_state.return_value = ConnectionState.OPEN
    result2 = svc.get_node_status()
    assert result2["nodes"][0]["pool_state"] == "open"
    assert result2["nodes"][0]["reachable"] is True


def test_get_node_status_cached_info_available_false():
    """Node with empty cache shows cached_info_available=False."""
    svc = make_service()
    result = svc.get_node_status()
    assert result["nodes"][0]["cached_info_available"] is False


def test_get_node_status_cached_info_available_true():
    """Node with non-empty cache shows cached_info_available=True."""
    registry = NodeRegistry()
    cfg = NodeConfig(name="lab-pi-01", mode="direct", enabled=True,
                     host="192.168.1.10", port=22, user="pi", id_file=None)
    registry.add(cfg)
    registry.update_cache("lab-pi-01", NodeInfoCache(
        facts={"hostname": {"value": "rpi01", "source": "cache", "collected_at": None}},
        collected_at=None,
    ))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.get_node_status()
    assert result["nodes"][0]["cached_info_available"] is True

def test_get_node_status_uses_pool_get_connection_state():
    """NodeService calls pool.get_connection_state(name) — never pool.connections directly."""
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    pool = make_mock_pool(connections=[conn])
    registry = NodeRegistry()
    cfg = NodeConfig(name="lab-pi-01", mode="direct", enabled=True,
                     host="192.168.1.10", port=22, user="pi", id_file=None)
    registry.add(cfg)
    svc = NodeService(registry=registry, pool=pool)
    svc.get_node_status()
    pool.get_connection_state.assert_called_with("lab-pi-01")


# ---------------------------------------------------------------------------
# NodeService — get_node_info() tests
# ---------------------------------------------------------------------------


def test_get_node_info_all_nodes():
    """Without name argument, returns all configured nodes."""
    from agent.connectionpool.connection import ConnectionState

    nodes = [("node-a", "direct", True), ("node-b", "tunnel", True)]
    svc = make_service(nodes=nodes, pool_connections=[])
    result = svc.get_node_info()

    assert "nodes" in result
    assert len(result["nodes"]) == 2
    returned_names = {n["name"] for n in result["nodes"]}
    assert returned_names == {"node-a", "node-b"}


def test_get_node_info_single_node():
    """With name, returns only that node."""
    nodes = [("node-a", "direct", True), ("node-b", "tunnel", True)]
    svc = make_service(nodes=nodes, pool_connections=[])
    result = svc.get_node_info(name="node-a")

    assert "nodes" in result
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["name"] == "node-a"


def test_get_node_info_unknown_node():
    """Unknown name returns {"error": "node not found", "name": <name>}."""
    svc = make_service()
    result = svc.get_node_info(name="no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_get_node_info_response_shape():
    """Each node entry has name, enabled, pool_state, info."""
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    svc = make_service(pool_connections=[conn])
    result = svc.get_node_info()

    assert len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert "name" in node
    assert "enabled" in node
    assert "pool_state" in node
    assert "info" in node


def test_get_node_info_refresh_false_no_ssh():
    """refresh=False produces no SSH interaction (pool mock SSH methods not invoked)."""
    from unittest.mock import MagicMock
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    svc = make_service(pool_connections=[conn])

    # Call with refresh=False (the default)
    svc.get_node_info(refresh=False)

    # Connection's execute / open methods must NOT have been called
    conn.execute.assert_not_called()
    conn.open.assert_not_called()


def test_get_node_info_refresh_true_stubbed():
    """refresh=True returns same node data plus refresh_note field."""
    from agent.connectionpool.connection import ConnectionState

    conn = make_mock_connection("lab-pi-01", ConnectionState.OPEN)
    svc = make_service(pool_connections=[conn])

    result_no_refresh = svc.get_node_info(refresh=False)
    result_with_refresh = svc.get_node_info(refresh=True)

    # Both must have nodes
    assert "nodes" in result_with_refresh
    assert result_with_refresh["nodes"] == result_no_refresh["nodes"]

    # Stub note must be present
    assert "refresh_note" in result_with_refresh
    assert result_with_refresh["refresh_note"] == "live refresh not yet implemented"

    # No refresh_note in the non-refresh result
    assert "refresh_note" not in result_no_refresh


def test_get_node_info_info_contains_cache_facts():
    """info field reflects what is in NodeInfoCache.facts."""
    registry = NodeRegistry()
    cfg = NodeConfig(name="lab-pi-01", mode="direct", enabled=True,
                     host="192.168.1.10", port=22, user="pi", id_file=None)
    registry.add(cfg)
    facts = {"hostname": {"value": "rpi01", "source": "cache", "collected_at": None}}
    registry.update_cache("lab-pi-01", NodeInfoCache(facts=facts, collected_at=None))

    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.get_node_info(name="lab-pi-01")

    assert result["nodes"][0]["info"] == facts


# ---------------------------------------------------------------------------
# NodeService — disable_node() tests
# ---------------------------------------------------------------------------


def test_disable_node_sets_enabled_false():
    """After disable_node, get_node_status shows enabled=False for that node."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.disable_node("lab-pi-01")
    result = svc.get_node_status()
    node = result["nodes"][0]
    assert node["name"] == "lab-pi-01"
    assert node["enabled"] is False


def test_disable_node_calls_pool_disable():
    """pool.disable_connection(name) is called when disable_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01"))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.disable_node("lab-pi-01")
    pool.disable_connection.assert_called_once_with("lab-pi-01")


def test_disable_node_node_still_visible_in_status():
    """Disabled node still appears in get_node_status result."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.disable_node("lab-pi-01")
    result = svc.get_node_status()
    names = [n["name"] for n in result["nodes"]]
    assert "lab-pi-01" in names


def test_disable_node_unknown_returns_error():
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.disable_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


# ---------------------------------------------------------------------------
# NodeService — enable_node() tests
# ---------------------------------------------------------------------------


def test_enable_node_sets_enabled_true():
    """After enable_node, get_node_status shows enabled=True for that node."""
    svc = make_service(nodes=[("lab-pi-01", "direct", False)])
    svc.enable_node("lab-pi-01")
    result = svc.get_node_status()
    node = result["nodes"][0]
    assert node["name"] == "lab-pi-01"
    assert node["enabled"] is True


def test_enable_node_calls_pool_enable():
    """pool.enable_connection(name) is called when enable_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01", enabled=False))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.enable_node("lab-pi-01")
    pool.enable_connection.assert_called_once_with("lab-pi-01")


def test_enable_node_unknown_returns_error():
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.enable_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_enable_node_validate_true_stubbed():
    """Returns validate_note field when validate=True."""
    svc = make_service(nodes=[("lab-pi-01", "direct", False)])
    result = svc.enable_node("lab-pi-01", validate=True)
    assert result["status"] == "enabled"
    assert result["name"] == "lab-pi-01"
    assert "validate_note" in result
    assert result["validate_note"] == "validation not yet implemented"


# ---------------------------------------------------------------------------
# NodeService — remove_node() tests
# ---------------------------------------------------------------------------


def test_remove_node_removes_from_status():
    """After remove_node, node is absent from get_node_status."""
    svc = make_service(nodes=[("lab-pi-01", "direct", True)])
    svc.remove_node("lab-pi-01")
    result = svc.get_node_status()
    names = [n["name"] for n in result["nodes"]]
    assert "lab-pi-01" not in names


def test_remove_node_calls_pool_remove():
    """pool.remove_connection(name) is called when remove_node is invoked."""
    registry = NodeRegistry()
    registry.add(make_node_config("lab-pi-01"))
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.remove_node("lab-pi-01")
    pool.remove_connection.assert_called_once_with("lab-pi-01")


def test_remove_node_unknown_returns_error():
    """Returns {"error": "node not found", "name": ...} for unknown node."""
    svc = make_service()
    result = svc.remove_node("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


# ---------------------------------------------------------------------------
# NodeService — add_node() tests
# ---------------------------------------------------------------------------


def test_add_node_returns_bootstrap_not_implemented():
    """status == "bootstrap_not_implemented" and reason field is present."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert result["status"] == "bootstrap_not_implemented"
    assert "reason" in result
    assert result["name"] == "new-node"


def test_add_node_does_not_add_to_registry():
    """After add_node, node is NOT present in registry (registry.exists returns False)."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert registry.exists("new-node") is False


def test_add_node_result_has_no_password_field():
    """Return dict has no key 'password'."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    result = svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password="some-password",
        mode="direct",
    )
    assert "password" not in result


def test_add_node_password_not_in_registry():
    """No password value appears in registry state after add_node call."""
    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    secret = "registry-safety-test-pw-99999"
    svc.add_node(
        name="new-node",
        host="192.168.1.50",
        port=22,
        user="pi",
        password=secret,
        mode="direct",
    )
    # Registry should have no entries (node was not added)
    assert registry.exists("new-node") is False
    # Double check: serialise all registry entries and confirm no secret
    for cfg, cache in registry.all():
        assert secret not in str(cfg)
        assert secret not in str(cache)


def test_add_node_password_not_in_logs(caplog):
    """Password string must not appear in any captured log record message."""
    import logging

    registry = NodeRegistry()
    pool = make_mock_pool()
    svc = NodeService(registry=registry, pool=pool)
    secret_password = "super-secret-bootstrap-pw-12345"
    with caplog.at_level(logging.DEBUG):
        result = svc.add_node(
            name="test-node",
            host="192.168.1.50",
            port=22,
            user="pi",
            password=secret_password,
            mode="direct",
        )
    # Password must not appear in any log record
    for record in caplog.records:
        assert secret_password not in record.getMessage(), (
            f"Password found in log record: {record.getMessage()}"
        )
    # Also verify not in return value
    assert secret_password not in str(result)
