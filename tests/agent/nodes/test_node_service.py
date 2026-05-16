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


# ---------------------------------------------------------------------------
# NodeService — ensure_node_ready() tests
# ---------------------------------------------------------------------------


def _make_mock_handshake_service():
    """Return a MagicMock handshake service with a plausible run() return value."""
    from unittest.mock import MagicMock
    hs = MagicMock()
    hs.run.return_value = {
        "hostname": {"value": "test-host", "source": "handshake", "collected_at": ""}
    }
    return hs


def _make_service_for_ready(nodes=None, pool_get_connection=None, pool_ensure_open=None, handshake_service=None):
    """Build a NodeService with an injectable mock pool supporting get_connection / ensure_connection_open."""
    from unittest.mock import MagicMock
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

    pool = MagicMock()

    # get_connection_state is used by existing helper methods — provide a default
    pool.get_connection_state.return_value = "open"

    # Configurable get_connection behaviour
    if pool_get_connection is not None:
        pool.get_connection.side_effect = pool_get_connection
    else:
        pool.get_connection.return_value = MagicMock(name="default-conn")

    # Configurable ensure_connection_open behaviour
    if pool_ensure_open is not None:
        pool.ensure_connection_open.side_effect = pool_ensure_open
    else:
        # Default: return the same object that get_connection would return
        _default_conn = MagicMock()
        _default_conn.name = "lab-pi-01"
        pool.get_connection.return_value = _default_conn
        pool.ensure_connection_open.return_value = _default_conn

    hs = handshake_service or _make_mock_handshake_service()
    return NodeService(registry=registry, pool=pool, handshake_service=hs), registry, pool, hs


def test_ensure_node_ready_unknown_node_returns_error():
    """Returns {"error": "node not found", ...} when node is not in registry."""
    svc, *_ = _make_service_for_ready(nodes=[("lab-pi-01", "direct", True)])
    result = svc.ensure_node_ready("no-such-node")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_ensure_node_ready_disabled_node_returns_error():
    """Returns {"error": "node_disabled", ...} for a disabled node."""
    svc, *_ = _make_service_for_ready(nodes=[("lab-pi-01", "direct", False)])
    result = svc.ensure_node_ready("lab-pi-01")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}


def test_ensure_node_ready_not_in_pool_returns_error():
    """Returns {"error": "not_in_pool", ...} when pool.get_connection returns None."""
    svc, *_ = _make_service_for_ready(
        pool_get_connection=lambda name: None,
    )
    result = svc.ensure_node_ready("lab-pi-01")
    assert result == {"error": "not_in_pool", "name": "lab-pi-01"}


def test_ensure_node_ready_connection_not_open_returns_error():
    """Returns {"error": "connection_not_open", ...} when ensure_connection_open returns None."""
    from unittest.mock import MagicMock
    fake_conn = MagicMock()
    svc, *_ = _make_service_for_ready(
        pool_get_connection=lambda name: fake_conn,
        pool_ensure_open=lambda name: None,
    )
    result = svc.ensure_node_ready("lab-pi-01")
    assert result == {"error": "connection_not_open", "name": "lab-pi-01"}


def test_ensure_node_ready_runs_handshake_when_cache_empty():
    """handshake_service.run() is called when NodeInfoCache.facts is empty."""
    from unittest.mock import MagicMock
    hs = _make_mock_handshake_service()
    fake_conn = MagicMock()
    svc, registry, pool, _ = _make_service_for_ready(
        pool_get_connection=lambda name: fake_conn,
        pool_ensure_open=lambda name: fake_conn,
        handshake_service=hs,
    )
    svc.ensure_node_ready("lab-pi-01")
    hs.run.assert_called_once_with(fake_conn)


def test_ensure_node_ready_skips_handshake_when_cache_populated():
    """handshake_service.run() is NOT called when NodeInfoCache.facts is already populated."""
    from unittest.mock import MagicMock
    hs = _make_mock_handshake_service()
    fake_conn = MagicMock()
    svc, registry, pool, _ = _make_service_for_ready(
        pool_get_connection=lambda name: fake_conn,
        pool_ensure_open=lambda name: fake_conn,
        handshake_service=hs,
    )
    # Pre-populate the cache so handshake should be skipped
    registry.update_cache(
        "lab-pi-01",
        NodeInfoCache(
            facts={"hostname": {"value": "existing-host", "source": "cache", "collected_at": ""}},
            collected_at="2026-01-01T00:00:00Z",
        ),
    )
    svc.ensure_node_ready("lab-pi-01")
    hs.run.assert_not_called()


def test_ensure_node_ready_returns_node_ready_instance():
    """Successful ensure_node_ready returns a _NodeReady with a .connection attribute (not a dict)."""
    from unittest.mock import MagicMock
    from agent.nodes.service import _NodeReady
    fake_conn = MagicMock()
    svc, *_ = _make_service_for_ready(
        pool_get_connection=lambda name: fake_conn,
        pool_ensure_open=lambda name: fake_conn,
    )
    result = svc.ensure_node_ready("lab-pi-01")
    assert not isinstance(result, dict), "Expected _NodeReady, got dict"
    assert isinstance(result, _NodeReady)
    assert result.connection is fake_conn


# ---------------------------------------------------------------------------
# NodeService — run_command_on_node() tests
# ---------------------------------------------------------------------------


def _make_noop_handshake():
    """Return a MagicMock handshake service that does nothing (returns {})."""
    from unittest.mock import MagicMock
    hs = MagicMock()
    hs.run.return_value = {}
    return hs


def _make_service_with_open_connection(name="lab-pi-01"):
    """Build a NodeService where the named node is enabled and has an open mock connection."""
    from unittest.mock import MagicMock
    from agent.connectionpool.connection import ConnectionState

    registry = NodeRegistry()
    cfg = NodeConfig(
        name=name,
        mode="direct",
        enabled=True,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    mock_conn = MagicMock()
    mock_conn.name = name

    pool = MagicMock()
    pool.get_connection_state.return_value = "open"
    pool.get_connection.return_value = mock_conn
    pool.ensure_connection_open.return_value = mock_conn

    hs = _make_noop_handshake()
    svc = NodeService(registry=registry, pool=pool, handshake_service=hs)
    return svc, mock_conn


def test_run_command_on_node_delegates_to_connection():
    """run_command_on_node() calls connection.execute() and returns to_dict() result."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone
    from agent.connection_result import CommandResult

    svc, mock_conn = _make_service_with_open_connection()

    fake_result = CommandResult(
        command="echo hi",
        exit_code=0,
        stdout="hi\n",
        stderr="",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
    )
    mock_conn.execute.return_value = fake_result

    result = svc.run_command_on_node("lab-pi-01", "echo hi")

    assert "exit_code" in result
    assert "stdout" in result
    assert "stderr" in result
    assert result["exit_code"] == 0
    assert result["stdout"] == "hi\n"


def test_run_command_on_node_unknown_node_returns_error():
    """run_command_on_node() returns node not found error for unknown node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake())

    result = svc.run_command_on_node("no-such-node", "echo hi")
    assert result == {"error": "node not found", "name": "no-such-node"}


def test_run_command_on_node_disabled_node_returns_error():
    """run_command_on_node() returns node_disabled error for a disabled node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake())

    result = svc.run_command_on_node("lab-pi-01", "echo hi")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}


def test_run_command_on_node_not_in_pool_returns_error():
    """run_command_on_node() returns not_in_pool error when pool.get_connection returns None."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=True,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    pool.get_connection_state.return_value = "not_in_pool"
    pool.get_connection.return_value = None

    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake())

    result = svc.run_command_on_node("lab-pi-01", "echo hi")
    assert result == {"error": "not_in_pool", "name": "lab-pi-01"}


def test_run_command_on_node_timeout_returns_error():
    """run_command_on_node() returns timeout error when connection.execute raises TimeoutError."""
    svc, mock_conn = _make_service_with_open_connection()
    mock_conn.execute.side_effect = TimeoutError("timed out")

    result = svc.run_command_on_node("lab-pi-01", "sleep 100", timeout=1)

    assert result["error"] == "timeout"
    assert result["name"] == "lab-pi-01"
    assert result["command"] == "sleep 100"


# ---------------------------------------------------------------------------
# NodeService — upload_file_to_node() / download_file_from_node() tests
# ---------------------------------------------------------------------------


def test_upload_file_to_node_delegates_to_connection():
    """upload_file_to_node() calls connection.upload_file() with correct args and returns result."""
    import base64

    svc, mock_conn = _make_service_with_open_connection()
    mock_conn.upload_file.return_value = {"status": "written", "path": "/tmp/test"}

    valid_b64 = base64.b64encode(b"hello").decode()
    result = svc.upload_file_to_node("lab-pi-01", "/tmp/test", valid_b64, "0644")

    assert result == {"status": "written", "path": "/tmp/test"}
    mock_conn.upload_file.assert_called_once_with("/tmp/test", valid_b64, "0644")


def test_upload_file_to_node_disabled_node_returns_error():
    """upload_file_to_node() returns node_disabled error for a disabled node."""
    import base64
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake())

    valid_b64 = base64.b64encode(b"hello").decode()
    result = svc.upload_file_to_node("lab-pi-01", "/tmp/test", valid_b64, "0644")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}


def test_download_file_from_node_delegates_to_connection():
    """download_file_from_node() calls connection.download_file() and returns result."""
    import base64

    svc, mock_conn = _make_service_with_open_connection()
    expected = {"status": "ok", "path": "/tmp/test", "data_b64": "abc"}
    mock_conn.download_file.return_value = expected

    result = svc.download_file_from_node("lab-pi-01", "/tmp/test")

    assert result == expected
    mock_conn.download_file.assert_called_once_with("/tmp/test")


def test_download_file_from_node_disabled_node_returns_error():
    """download_file_from_node() returns node_disabled error for a disabled node."""
    from unittest.mock import MagicMock

    registry = NodeRegistry()
    cfg = NodeConfig(
        name="lab-pi-01",
        mode="direct",
        enabled=False,
        host="192.168.1.10",
        port=22,
        user="pi",
        id_file=None,
    )
    registry.add(cfg)

    pool = MagicMock()
    svc = NodeService(registry=registry, pool=pool, handshake_service=_make_noop_handshake())

    result = svc.download_file_from_node("lab-pi-01", "/tmp/test")
    assert result == {"error": "node_disabled", "name": "lab-pi-01"}
