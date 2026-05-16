"""Phase 6 — Functional tests for NodeService against a live sshd fixture.

NodeService is backed by a NodeRegistry and a ConnectionPool. Every test
calls pool.stop() in a try/finally block to prevent leaked timers.
"""

import time
import pytest
from agent.connectionpool.config_loader import ConnectionConfig
from agent.connectionpool.pool import ConnectionPool
from agent.nodes.models import NodeConfig
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService


def _make_connection_config(spawn_sshd) -> ConnectionConfig:
    return ConnectionConfig(
        name="test-node",
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
        mode="direct",
        port=spawn_sshd.port,
        host=spawn_sshd.host,
    )


def _make_node_config(spawn_sshd) -> NodeConfig:
    return NodeConfig(
        name="test-node",
        mode="direct",
        enabled=True,
        host=spawn_sshd.host,
        port=spawn_sshd.port,
        user=spawn_sshd.user,
        id_file=spawn_sshd.client_key_path,
    )


def _wait_for_open(pool: ConnectionPool, name: str, timeout: float = 5.0) -> None:
    """Poll pool.get_connection_state(name) until it returns 'open' or assert on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pool.get_connection_state(name) == "open":
            return
        time.sleep(0.1)
    final_state = pool.get_connection_state(name)
    assert final_state == "open", (
        f"Expected connection '{name}' to become open within {timeout}s, "
        f"got state '{final_state}'"
    )


@pytest.fixture
def node_service_and_name(spawn_sshd):
    conn_config = _make_connection_config(spawn_sshd)
    node_config = _make_node_config(spawn_sshd)
    name = conn_config.name

    pool = ConnectionPool([conn_config], reconnection_delay=30)
    pool.start()

    registry = NodeRegistry()
    registry.add(node_config)

    service = NodeService(registry, pool)
    try:
        yield service, pool, name
    finally:
        pool.stop()


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_get_node_status_reports_pool_state_open(node_service_and_name):
    """get_node_status() result contains pool_state == 'open' for the fixture-backed node."""
    service, pool, name = node_service_and_name
    _wait_for_open(pool, name)

    result = service.get_node_status()
    assert result["status"] == "ok"
    nodes = result["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["name"] == name
    assert nodes[0]["pool_state"] == "open"


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_get_node_info_returns_node_entry(node_service_and_name):
    """get_node_info(name) returns a result with name, enabled, and pool_state fields."""
    service, pool, name = node_service_and_name
    _wait_for_open(pool, name)

    result = service.get_node_info(name)
    assert "nodes" in result
    nodes = result["nodes"]
    assert len(nodes) == 1
    entry = nodes[0]
    assert entry["name"] == name
    assert "enabled" in entry
    assert "pool_state" in entry
    assert entry["enabled"] is True


@pytest.mark.functional
@pytest.mark.requires_sshd
def test_disable_node_closes_connection(node_service_and_name):
    """disable_node(name) causes get_node_status(name) to show pool_state != 'open'."""
    service, pool, name = node_service_and_name
    _wait_for_open(pool, name)

    result = service.disable_node(name)
    assert result["status"] == "disabled"
    assert result["name"] == name

    status = service.get_node_status()
    nodes = {n["name"]: n for n in status["nodes"]}
    assert name in nodes
    assert nodes[name]["pool_state"] != "open", (
        f"Expected pool_state != 'open' after disable_node, got '{nodes[name]['pool_state']}'"
    )
    assert nodes[name]["enabled"] is False
