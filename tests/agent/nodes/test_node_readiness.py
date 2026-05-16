"""Unit tests for NodeService.ensure_node_ready()."""

import pytest

from agent.nodes.models import NodeConfig, NodeInfoCache
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService
from tests.agent.nodes.conftest import make_node_config


# ---------------------------------------------------------------------------
# Helpers specific to ensure_node_ready tests
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


# ---------------------------------------------------------------------------
# NodeService — ensure_node_ready() tests
# ---------------------------------------------------------------------------


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
