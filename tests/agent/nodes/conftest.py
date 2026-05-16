"""Shared helpers for agent/nodes unit tests.

These are used across test_registry.py, test_node_status_info.py,
test_node_lifecycle.py, test_node_readiness.py, and test_node_execution_service.py.
"""

from agent.nodes.models import NodeConfig, NodeInfoCache
from agent.nodes.registry import NodeRegistry
from agent.nodes.service import NodeService


# ---------------------------------------------------------------------------
# Factory helpers
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


def make_service(nodes=None, pool_connections=None, identity_service=None):
    """Build a NodeService with pre-populated registry and mock pool.

    nodes: list of (name, mode, enabled) tuples; defaults to one direct/enabled node.
    pool_connections: list of mock connection objects; defaults to empty list.
    identity_service: optional mock AgentIdentityService (defaults to a MagicMock).
    """
    from unittest.mock import MagicMock
    from agent.nodes.handshake import NodeHandshakeService

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
    # Always provide a non-None identity service — NodeService requires both services.
    effective_identity = identity_service if identity_service is not None else MagicMock()
    handshake = NodeHandshakeService()
    return NodeService(registry=registry, pool=pool, handshake_service=handshake, agent_identity_service=effective_identity)


def make_mock_identity_service(public_key="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5 agent@test"):
    """Build a mock AgentIdentityService whose get_identity() returns a mock identity."""
    from unittest.mock import MagicMock
    identity = MagicMock()
    identity.public_key = public_key
    svc = MagicMock()
    svc.get_identity.return_value = identity
    return svc
