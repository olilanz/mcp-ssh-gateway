"""Unit tests for NodeService.get_node_status() and NodeService.get_node_info()."""

import pytest

from agent.nodes.models import NodeConfig, NodeInfoCache
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService
from tests.agent.nodes.conftest import (
    make_node_config,
    make_mock_connection,
    make_mock_pool,
    make_service,
)


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
